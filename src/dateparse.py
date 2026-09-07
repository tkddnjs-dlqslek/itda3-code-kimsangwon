# -*- coding: utf-8 -*-
"""OCR 텍스트 조각에서 소비기한 날짜를 뽑는 순수 파이썬 규칙 엔진.

파이프라인: 정규화 -> 패턴 순차 매칭(먼저 잡은 구간 우선) -> 달력 검증 -> 점수 -> 선택.
입력 조각은 ocr.group_lines 가 같은 줄끼리 묶어 준 문자열이라, 키워드와 날짜가
대개 한 조각 안에 있다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

__all__ = ["Candidate", "find_candidates", "extract_date", "explain"]


@dataclass
class Candidate:
    y: int | None
    m: int | None
    d: int | None
    text: str
    score: float
    why: list = field(default_factory=list)   # 점수 근거 (trace 용)
    head: str = ""                             # 같은 줄에서 날짜 앞에 있던 글자
    minor: float = 0.0                         # 조사형(부터/까지) 점수: 늦은 날짜 규칙 다음 순위


# --- 정규화 ------------------------------------------------------------------
# 숫자가 하나라도 섞인 글자 덩어리 안에서만 O->0, I/l/|->1 (OCT, Lotto 같은 단어는 보존)
_TR = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "|": "1"})
_NUMISH = re.compile(r"[0-9OoIl|]{2,}")


def _norm(text: str) -> str:
    return _NUMISH.sub(lambda m: m.group(0).translate(_TR) if any(c.isdigit() for c in m.group(0)) else m.group(0), text)


# --- 키워드 ------------------------------------------------------------------
_EXP_WORDS = (r"소비기한|유통기한|\bexp\b|best before|best by|\bbbe\b|use by"
              r"|expiraci[oó]n|caducidad|limite|scadenza|haltbar|consumir|\bmhd\b|v[aá]lido")
_MFG_WORDS = (r"제조|생산|\bmfg\b|\bmfd\b|\bprod\b|emballage|fabricaci[oó]n|packed|production|\bpkd\b")
EXPIRY = re.compile(_EXP_WORDS + r"|까지", re.I)
MFG = re.compile(_MFG_WORDS + r"|부터|\blot\b", re.I)
# 조사형 키워드: 한국어는 "날짜 부터 / 날짜 까지"처럼 키워드가 날짜 뒤에 온다 (줄 묶기 후엔 대개 같은 조각)
POST_EXPIRY = re.compile(r"까지")
POST_MFG = re.compile(r"부터")
# 접두형 키워드: "소비기한: / Best before:" 뒤에 날짜
PRE_EXPIRY = re.compile(_EXP_WORDS, re.I)
PRE_MFG = re.compile(_MFG_WORDS, re.I)
_TIME_AFTER = re.compile(r"^\s*[.,/>]?\s*\d{1,2}\s*:\s*\d{2}")   # 날짜 바로 뒤 HH:MM

# --- 패턴 --------------------------------------------------------------------
SEP_K = r"\s*[.\-/,:·년월]{1,2}\s*"   # 국내 구분자 (쉼표, 콜론 오인식, ':.' 같은 2연속 포함)
SEP_S = r"\s+"                          # 공백만
SEP_D = r"\s?[.\-/·,]\s?|\s"                # 수입품 구분자: 구두점(공백 허용) 또는 공백 한 칸
SEP_DY = r"\s?[.\-/·,]\s?|\s+:?\s*"         # 연도 직전 구분자: '01 10 :2026' 의 곁다리 콜론 허용
SEP_K2 = r"(?:" + SEP_K + r"|\s+)"           # 국내 2자리 연도: 공백만 있는 구분자도 허용 (26· 08  31)
MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
MONTHS = {n: i + 1 for i, n in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}

# (정규식, 그룹 해석, 만료키워드 필요 여부)
_PATTERNS = [
    # 4자리 연도 + 공백만 (2026 10 02). '2026. 03. 1 6' 처럼 일 안에 공백 하나도 허용
    (re.compile(r"(?<!\d)(20\d ?\d)[.\s]+(\d(?: ?\d)?)[.\s]+(\d(?: ?\d)?)(?!\d)"), "ymd_sp", False),
    # 연도 먼저 + 구분자. 뒤쪽 경계를 두지 않아 시각/LOT이 붙어도 통과 (2023.12.0610:13)
    (re.compile(r"(?<!\d)(\d{3,5})" + SEP_K + r"(\d{1,2})" + SEP_K + r"(\d{1,2})"), "ymd", False),
    # 202006/01 처럼 연월이 붙고 일만 떨어진 형태
    (re.compile(r"(?<!\d)(\d{4})(\d{2})[/.\-](\d{1,2})(?!\d)"), "ymd", False),
    # AUG 11 2021
    (re.compile(MON + r"[a-z]*\.?[\s,]*(\d{1,2})[\s,.]+(\d{4})(?!\d)", re.I), "mon_d_y", False),
    # 07 SEP 21 / 01 SEP 2023
    (re.compile(r"(?<!\d)(\d{1,2})[\s.\-]*" + MON + r"[a-z]*\.?[\s,]*(\d{2,4})(?!\d)", re.I), "d_mon_y", False),
    # 11:11:21 은 만료 키워드가 있을 때만 날짜, 없으면 시각
    (re.compile(r"(?<!\d)(\d{2}):(\d{2}):(\d{2})(?!\d)"), "dmy", True),
    # 29052026 / 25/032025 수입품 일월년 8자리 압축 (LOT 접합 허용)
    (re.compile(r"(?<!\d)(\d{2})/?(\d{2})(20\d{2})(?!\d)"), "dmy", False),
    # 31/12/2023 수입품 일-월-연
    (re.compile(r"(?<!\d)(\d{1,2})(?:" + SEP_D + r")(\d{1,2})(?:" + SEP_DY + r")(\d{3,5})(?!\d)"), "dmy", False),
    # 2026.0109 / 2026 0622 연도 뒤 월일이 붙은 형태
    (re.compile(r"(?<!\d)(20\d{2})[.\-/\s](\d{2})(\d{2})(?!\d)"), "ymd", False),
    # 25.12.10 국내 두 자리 연도 먼저 (연도로 성립할 때만 통과)
    (re.compile(r"(?<!\d)(\d{2})" + SEP_K2 + r"(\d{1,2})" + SEP_K2 + r"(\d{1,2})(?!\d)"), "ymd2k", False),
    # 10.10.21 두 자리 연도가 뒤 (위 규칙이 실패했을 때만 도달). 뒤에 :MM 이 오면 시각이라 제외
    (re.compile(r"(?<!\d)(\d{1,2})(?:" + SEP_D + r")(\d{1,2})(?:" + SEP_D + r")(\d{2})(?!\d)(?!\s*:\s*\d{2})"), "dmy", False),
    # 정확히 8자리일 때만 YYYYMMDD (13/14자리 바코드, 품목보고번호 배제)
    (re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)"), "ymd", False),
    # 6자리 압축 261027 / 091122: 년월일 먼저, 연도 범위 밖이면 일월년. 다른 날짜 없을 때만 쓰이도록 감점
    (re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?![\d:])"), "c6", False),
    # 부분: OCT.2021 (OCT.o2021 처럼 앞에 o 가 붙어 5자리가 되는 경우도 _year 가 흡수)
    (re.compile(MON + r"[a-z]*\.?\s*(\d{3,5})(?!\d)", re.I), "mon_y", False),
    # 부분: 11/2023
    (re.compile(r"(?<!\d)(\d{1,2})\s*/\s*(\d{4})(?!\d)"), "m_y", False),
    # 부분: 2026.06 (연월만)
    (re.compile(r"(?<!\d)(20\d{2})[.\-/년 ]\s?(\d{1,2})(?![\d.\-/])"), "y_m", False),
    # 부분: 10.22 (같은 조각에 까지가 있거나 바로 뒤에 시각이 올 때만 채택)
    (re.compile(r"(?<!\d)(\d{1,2})[.\-](\d{1,2})(?!\d)"), "m_d", False),
]


def _year(tok: str, last: bool = False) -> int | None:
    """연도 토큰 정규화. 5자리는 앞 자리 붙음. 3자리는 연도가 앞이면 앞 자리 유실(20+끝 두 자리),
    연도가 뒤(last)면 LOT 접합(20+앞 두 자리). 2자리는 20YY."""
    if len(tok) == 5:
        tok = tok[1:]
    if len(tok) == 3:
        tok = "20" + (tok[:2] if last else tok[-2:])
    if len(tok) == 2:
        tok = "20" + tok
    if len(tok) != 4:
        return None
    y = int(tok)
    return y if 2015 <= y <= 2040 else None


def _complete(y, m, d):
    """달력상 실재하는 날짜만 통과."""
    if y is None or m is None or d is None:
        return None
    try:
        date(y, m, d)
    except ValueError:
        return None
    return (y, m, d)


def _parse(kind: str, g: tuple) -> tuple | None:
    if kind in ("ymd", "ymd2k"):
        return _complete(_year(g[0]), int(g[1]), int(g[2]))
    if kind == "ymd_sp":
        return _complete(_year(g[0].replace(" ", "")), int(g[1].replace(" ", "")), int(g[2].replace(" ", "")))
    if kind == "dmy":
        if len(g[2]) == 3:
            # 26.06.227K: 국내 YY.MM.DD 뒤에 LOT 숫자가 붙은 형태를 먼저 본다 (국내 라벨이 다수)
            k = _complete(_year(g[0]), int(g[1]), int(g[2][:2]))
            if k:
                return k
        d, m, y = int(g[0]), int(g[1]), _year(g[2], last=True)
        # 일-월 기본, 그 순서가 달력에 없으면 월-일로 뒤집어 본다
        return _complete(y, m, d) or _complete(y, d, m)
    if kind == "c6":
        a, b, c = g
        return _complete(_year(a), int(b), int(c)) or _complete(_year(c), int(b), int(a))
    if kind == "c6d":   # (일/월/년) 힌트: 일월년 먼저
        a, b, c = g
        return _complete(_year(c), int(b), int(a)) or _complete(_year(a), int(b), int(c))
    if kind == "mon_d_y":
        return _complete(_year(g[2]), MONTHS[g[0].lower()], int(g[1]))
    if kind == "d_mon_y":
        return _complete(_year(g[2]), MONTHS[g[1].lower()], int(g[0]))
    if kind == "mon_y":
        y = _year(g[1])
        return (y, MONTHS[g[0].lower()], None) if y else None
    if kind == "m_y":
        y, m = _year(g[1]), int(g[0])
        return (y, m, None) if y and 1 <= m <= 12 else None
    if kind == "y_m":
        y, m = _year(g[0]), int(g[1])
        return (y, m, None) if y and 1 <= m <= 12 else None
    if kind == "m_d":
        m, d = int(g[0]), int(g[1])
        return (None, m, d) if 1 <= m <= 12 and 1 <= d <= 31 else None
    raise ValueError(kind)


def _repair(kind: str, g: tuple) -> tuple | None:
    """완전 날짜 패턴인데 월이나 일이 무효: 유효한 칸만 남긴 부분 날짜 (2021.67.03 -> 2021-NONE-03)."""
    if kind not in ("ymd", "ymd2k", "ymd_sp"):
        return None
    y = _year(g[0].replace(" ", ""))
    if y is None:
        return None
    m, d = int(g[1].replace(" ", "")), int(g[2].replace(" ", ""))
    m_ok, d_ok = 1 <= m <= 12, 1 <= d <= 31
    if m_ok == d_ok:      # 둘 다 무효거나 둘 다 유효(달력만 안 맞는 경우)면 포기
        return None
    return (y, m if m_ok else None, d if d_ok else None)


_YEAR_GROUP = {"ymd": 0, "ymd2k": 0, "ymd_sp": 0, "dmy": 2, "mon_d_y": 2, "d_mon_y": 2, "mon_y": 1, "m_y": 1, "y_m": 0}


def _year_token(kind: str, g: tuple) -> str:
    i = _YEAR_GROUP.get(kind)
    return "" if i is None else g[i]


_DATE_ONLY_LINE = re.compile(r"^\s*\d{1,2}[.\-]\d{1,2}\s+[A-Za-z0-9\-]{2,8}\s*$")   # "12.19 D1758" 날짜 + LOT 만 있는 줄


def find_candidates(text: str) -> list[Candidate]:
    """한 조각에서 날짜 후보를 뽑는다. 앞선 패턴이 잡은 구간은 뒤 패턴이 재사용하지 않는다."""
    norm = _norm(text)
    has_expiry = EXPIRY.search(norm) is not None
    # 수입품 힌트: 영어 만료 키워드나 (일/월/년) 표기가 있으면 국내식 YY.MM.DD 해석을 건너뛴다
    dmy_hint = re.search(r"best before|best by|exp|bbe|use by|일\s*/?\s*월\s*/?\s*년", norm, re.I) is not None
    taken: list[tuple[int, int]] = []
    out: list[Candidate] = []
    for rx, kind, needs_kw in _PATTERNS:
        if needs_kw and not has_expiry:
            continue
        if dmy_hint and kind == "ymd2k":
            continue
        if dmy_hint and kind == "c6":
            kind = "c6d"
        for m in rx.finditer(norm):
            s, e = m.span()
            if any(s < te and ts < e for ts, te in taken):
                continue
            parsed = _parse(kind, m.groups())
            repaired = False
            if parsed is None and has_expiry:
                parsed = _repair(kind, m.groups())
                repaired = parsed is not None
            if parsed is None:
                continue
            y, mo, d = parsed
            head, tail = norm[:s], norm[e:]
            # 연도 없는 월-일: 뒤에 '까지'나 시각(HH:MM)이 붙거나, 날짜만 있는 짧은 줄일 때만
            if kind == "m_d" and not (POST_EXPIRY.search(tail) or _TIME_AFTER.match(tail) or _DATE_ONLY_LINE.match(norm)):
                continue
            why = []
            score = 0.0
            # 접두형 키워드(소비기한:, Best before)는 줄 어디든, 조사형(까지/부터)은 날짜 뒤에 올 때만
            minor = 0.0
            if PRE_EXPIRY.search(norm):
                score += 2.0; why.append("만료 키워드 +2")
            if PRE_MFG.search(norm) or re.search(r"lot", norm, re.I):
                score -= 2.0; why.append("제조 키워드 -2")
            # 조사형(까지/부터)은 줄 묶기가 흔들리면 옆 날짜에 붙는다. 늦은 날짜 규칙 다음 순위로만 쓴다
            if POST_EXPIRY.search(tail):
                minor += 1.0; why.append("뒤에 까지 (보조 +1)")
            if POST_MFG.search(tail):
                minor -= 1.0; why.append("뒤에 부터 (보조 -1)")
            if _TIME_AFTER.match(tail):
                minor -= 1.0; why.append("뒤에 시각 (보조 -1, 제조 시각일 가능성)")
            if y is not None and len(_year_token(kind, m.groups())) >= 3:
                score += 0.5; why.append("4자리 연도 +0.5")
            if kind == "c6":
                score -= 1.0; why.append("6자리 압축 -1")
            if repaired:
                why.append("무효 칸 제거 (부분 날짜)")
            taken.append((s, e))
            out.append(Candidate(y, mo, d, m.group(0), score, why, head, minor))
    return out


def _fmt(v: int | None, width: int) -> str:
    return "NONE" if v is None else str(v).zfill(width)


def _rank(texts: list[str]) -> list[Candidate]:
    """조각 리스트 -> 점수 반영된 후보 전체 (선택 순 정렬)."""
    cands: list[Candidate] = []
    for i, t in enumerate(texts):
        prev = _norm(texts[i - 1]) if i else ""
        nxt = _norm(texts[i + 1]) if i + 1 < len(texts) else ""
        own = _norm(t)
        # 접두형 키워드는 앞 조각, 조사형(부터/까지)은 뒤 조각. 단 그 조각이 키워드만 있는 짧은 조각일 때
        # 이웃 조각의 키워드는 줄 묶기가 흔들리면 엉뚱한 날짜에 붙는다. 전부 보조 점수로만 쓴다
        ctx, post, cwhy = 0.0, 0.0, []
        if not any(ch.isdigit() for ch in prev):
            if PRE_EXPIRY.search(prev): post += 1.0; cwhy.append("앞 조각 만료 키워드 (보조 +1)")
            if PRE_MFG.search(prev): post -= 1.0; cwhy.append("앞 조각 제조 키워드 (보조 -1)")
        if not any(ch.isdigit() for ch in nxt) and not (POST_EXPIRY.search(own) or POST_MFG.search(own)):
            if POST_EXPIRY.search(nxt): post += 1.0; cwhy.append("뒤 조각 까지 (보조 +1)")
            if POST_MFG.search(nxt): post -= 1.0; cwhy.append("뒤 조각 부터 (보조 -1)")
        for c in find_candidates(t):
            # 앞 조각 키워드는 날짜가 줄 맨 앞에 올 때만 붙인다 ("후면표기일 까지 20.08.25" 는 다른 문장)
            blocked = re.search(r"[A-Za-z가-힣]", c.head) is not None
            if not blocked:
                c.score += ctx; c.minor += post; c.why = c.why + cwhy
            cands.append(c)
    complete = [c for c in cands if None not in (c.y, c.m, c.d)]
    partial = [c for c in cands if c not in complete]
    # 범위 표기 "A 부터 B 까지": 조사형 키워드 위치가 흔들려도 끝 날짜(늦은 쪽)가 소비기한
    joined = " ".join(_norm(t) for t in texts)
    if len(complete) >= 2 and POST_MFG.search(joined) and POST_EXPIRY.search(joined):
        for c in complete:
            c.score = 0.0
            c.why = ["부터~까지 범위: 늦은 날짜"]
    # 완전한 날짜가 있으면 부분 날짜는 뺀다. 단 완전 날짜가 전부 제조 쪽(음수)이고 부분 날짜가 만료 쪽(양수)이면 부분 우선
    if complete and partial and max(c.score for c in complete) < 0 < max(c.score for c in partial):
        pool = partial
    else:
        pool = complete or partial
    # 접두형 키워드 점수 > 늦은 날짜 (소비기한은 제조일보다 뒤) > 조사형 키워드
    pool.sort(key=lambda c: (c.score, c.y or 0, c.m or 0, c.d or 0, c.minor), reverse=True)
    return pool


def extract_date(texts: list[str]) -> tuple[str, str, str] | None:
    """조각 리스트에서 소비기한 하나를 고른다. 없으면 None."""
    pool = _rank(texts)
    if not pool:
        return None
    best = pool[0]
    return (_fmt(best.y, 4), _fmt(best.m, 2), _fmt(best.d, 2))


def explain(texts: list[str]) -> tuple[str | None, list[str]]:
    """trace 용: (선택 결과 문자열, 후보별 설명 리스트). 후보는 선택 순."""
    pool = _rank(texts)
    lines = []
    for i, c in enumerate(pool):
        ds = f"{_fmt(c.y, 4)}-{_fmt(c.m, 2)}-{_fmt(c.d, 2)}"
        tag = "선택" if i == 0 else f"{i + 1}순위"
        why = ", ".join(c.why) if c.why else "키워드 없음"
        if i == 0 and len(pool) > 1 and pool[1].score == c.score:
            why += ", 동점이라 늦은 날짜"
        lines.append(f"[{tag}] {ds} (점수 {c.score:+.1f}) <- '{c.text}' | {why}")
    chosen = lines[0].split(" ")[1] if lines else None
    return chosen, lines
