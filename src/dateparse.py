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

# 벤치용 플래그: OFF 로 두면 사전 교정 없이 예전 규칙 그대로 동작 (rescore 스크립트의 OLD 기준)
USE_KEYWORD_DICT = True
# 09-12 추가: 토큰 경계 밖 숫자(단어 뒤에 붙은 자릿수)를 날짜 후보에서 제거, 구분자 불일치/쉼표 감점
USE_JUNK_GUARD = True
# 09-12 추가: 접두형 키워드가 붙은 부분 날짜가, 키워드 없는 완전 날짜(정크)보다 우선
USE_KEYWORD_PARTIAL = True

# 키워드 오독 교정 사전. 출처: 'ITDA 공모전/키워드 변형 표.xlsx' 시트 '변형', 채택 == 'O' 행 (22개, 2026-09-12).
# 고친 키워드가 채워진 행은 그 값을, 비어 있으면 추정 키워드를 정답으로 쓴다.
# 재생성: tools/export_keyword_dict.py
KEYWORD_DICT = {
    "파지": "까지", "PRD": "PROD", "마지": "까지", "까자": "까지", "EP": "EXP",
    "소기한": "소비기한", "비기한": "소비기한", "EHP": "EXP", "소비기만": "소비기한",
    "까제": "까지", "스비기한": "소비기한", "스피기한": "소비기한", "보비기한": "소비기한",
    "소색기한": "소비기한", "모비기한": "소비기한", "EAP": "EXP", "EEFORE": "BEST BEFORE",
    "BESTBEFORE": "BEST BEFORE", "EXF": "EXP", "소비가한": "소비기한", "유동기한": "유통기한",
    "신비기한": "소비기한",
}
_HANGUL = r"가-힣"
_LATIN = r"A-Za-z"


def _kw_pattern(variant: str) -> str:
    """변형 토큰 경계 규칙: 라틴 변형은 라틴 글자와, 한글 변형은 한글 음절과 붙어 있으면 매칭하지 않는다
    (SEP 의 EP, 소비기한 의 비기한 오탐 방지). 숫자/공백/문장부호는 경계로 안 친다."""
    boundary = _LATIN if variant.isascii() else _HANGUL
    return rf"(?<![{boundary}]){re.escape(variant)}(?![{boundary}])"


_KEYWORD_RX = re.compile("|".join(_kw_pattern(v) for v in sorted(KEYWORD_DICT, key=len, reverse=True)))


def _correct_line(text: str) -> tuple[str, list[str]]:
    """한 줄에 사전 교정을 적용. (교정된 문자열, '사전 교정: 파지->까지' 식 why 리스트)."""
    hits: list[str] = []

    def _sub(m: re.Match) -> str:
        v = m.group(0)
        target = KEYWORD_DICT[v]
        hits.append(f"사전 교정: {v}->{target}")
        return target

    return _KEYWORD_RX.sub(_sub, text), hits


def _correct_lines(texts: list[str], geo: list | None = None) -> tuple[list[str], list[list[str]]]:
    """줄 리스트 전체에 범위 규칙을 적용해 사전 교정. 대상 줄: (a) 날짜 후보가 있는 줄,
    (b) 그 줄의 바로 위/아래 줄 중 숫자가 없고(geo 있으면 세로 거리가 줄 높이의 2배 이내인) 줄."""
    if not USE_KEYWORD_DICT or not texts:
        return list(texts), [[] for _ in texts]
    n = len(texts)
    has_date = [bool(find_candidates(t)) for t in texts]
    eligible = {i for i in range(n) if has_date[i]}
    for i in range(n):
        if not has_date[i]:
            continue
        for j in (i - 1, i + 1):
            if not (0 <= j < n) or has_date[j] or any(ch.isdigit() for ch in texts[j]):
                continue
            if geo is not None:
                cy_i, h_i = geo[i]
                cy_j, h_j = geo[j]
                if abs(cy_i - cy_j) > 2 * ((h_i + h_j) / 2):
                    continue
            eligible.add(j)
    out, whys = list(texts), [[] for _ in texts]
    for i in eligible:
        out[i], whys[i] = _correct_line(texts[i])
    return out, whys


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
    kind: str = ""                              # 원래 매칭된 패턴 종류 (c6 등, 범위 규칙에서 형태 판별용)


# --- 정규화 ------------------------------------------------------------------
# 숫자가 하나라도 섞인 글자 덩어리 안에서만 O->0, I/l/|->1 (OCT, Lotto 같은 단어는 보존)
_TR = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "|": "1"})
_NUMISH = re.compile(r"[0-9OoIl|]{2,}")


def _norm(text: str) -> str:
    return _NUMISH.sub(lambda m: m.group(0).translate(_TR) if any(c.isdigit() for c in m.group(0)) else m.group(0), text)


# --- 키워드 ------------------------------------------------------------------
_EXP_WORDS = (r"소비기한|유통기한|사용기한|유효기한|\bexp\b|best before|best by|\bbbe\b|use by"
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
    # 09-12 Rule 3: 월 이름+일+년 이 구분자 없이 붙음 (DEC012021)
    (re.compile(MON + r"(\d{2})(\d{4})(?!\d)", re.I), "mon_d_y", False),
    # 09-12 Rule 3: 월 이름 / 또는 - 로 일, 년과 이어짐 (FEB/21/21, DEC-01-2021). 2자리 연도 허용
    (re.compile(MON + r"[a-z]*\.?\s*[/\-]\s*(\d{1,2})\s*[/\-]\s*(\d{2,4})(?!\d)", re.I), "mon_d_y", False),
    # 09-12 Rule 4: 월+년만 (일 없음). 구분자는 점/대시/슬래시(붙여 쓴 경우) 또는 공백.
    # 앞에 day 로 보이는 숫자가 바로 붙어 있으면(일-월-년 완전 날짜의 꼬리, 31/12/2023 의
    # 12/2023 오탐) 제외한다 -- 실제 가드는 아래 루프의 _DAY_PREFIX_TIGHT/LOOSE 로 처리
    # (공백까지 낀 '27 .04.2026' 같은 가변 길이 구분자는 lookbehind 로 못 잡는다).
    (re.compile(r"(?<!\d)(\d{1,2})[./\-](\d{4})(?!\d)"), "m_y", False),
    (re.compile(r"(?<!\d)(\d{1,2})\s+(\d{4})(?!\d)"), "m_y", False),
    # 11:11:21 은 만료 키워드가 있을 때만 날짜, 없으면 시각
    (re.compile(r"(?<!\d)(\d{2}):(\d{2}):(\d{2})(?!\d)"), "dmy", True),
    # 29052026 / 25/032025 수입품 일월년 8자리 압축 (LOT 접합 허용)
    (re.compile(r"(?<!\d)(\d{2})/?(\d{2})(20\d{2})(?!\d)"), "dmy", False),
    # 31/12/2023 수입품 일-월-연
    (re.compile(r"(?<!\d)(\d{1,2})(?:" + SEP_D + r")(\d{1,2})(?:" + SEP_DY + r")(\d{3,5})(?!\d)"), "dmy", False),
    # 2026.0109 / 2026 0622 연도 뒤 월일이 붙은 형태
    (re.compile(r"(?<!\d)(20\d{2})[.\-/\s](\d{2})(\d{2})(?!\d)"), "ymd", False),
    # 09-13 Rule 2: 위와 같은 형태인데 뒤에 글자/숫자가 더 붙어도 앞 4자리(월일)만 취한다
    # (2026.01217A -> 2026-01-21, 뒷자리 '7A' 는 소비하지 않음). 위 경계 있는 패턴이 실패했을 때만 도달.
    (re.compile(r"(?<!\d)(20\d{2})[.\-](\d{2})(\d{2})"), "ymd", False),
    # 25.12.10 국내 두 자리 연도 먼저 (연도로 성립할 때만 통과)
    (re.compile(r"(?<!\d)(\d{2})" + SEP_K2 + r"(\d{1,2})" + SEP_K2 + r"(\d{1,2})(?!\d)"), "ymd2k", False),
    # 10.10.21 두 자리 연도가 뒤 (위 규칙이 실패했을 때만 도달). 뒤에 :MM 이 오면 시각이라 제외
    (re.compile(r"(?<!\d)(\d{1,2})(?:" + SEP_D + r")(\d{1,2})(?:" + SEP_D + r")(\d{2})(?!\d)(?!\s*:\s*\d{2})"), "dmy", False),
    # 정확히 8자리일 때만 YYYYMMDD (13/14자리 바코드, 품목보고번호 배제)
    (re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)"), "ymd", False),
    # 09-13: 연도+월이 붙고 그 사이 점이 콜론으로 오독된 경우 (2025.11.21 -> 202511:21)
    (re.compile(r"(?<!\d)(20\d{2})(\d{2}):(\d{2})(?!\d)"), "ymd", False),
    # 09-13 Rule 3: 6자리 압축 YYYYMM (일 없음). LOT 번호 오탐 방지로 만료 키워드가 같은 줄에 있을 때만.
    (re.compile(r"(?<!\d)(20\d{2})(\d{2})(?!\d)"), "y_m", True),
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
    # 09-13 Rule 1: 월.일 뒤에 시각/잡음 숫자가 구분자 없이 곧장 붙어(10.1513:56) 위 패턴이
    # 실패하는 경우. 일은 정확히 2자리로 고정해 자릿수 모호성을 줄인다.
    (re.compile(r"(?<!\d)(\d{1,2})[.\-](\d{2})(?=\d)"), "m_d", False),
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
            # 09-13: 위가 실패했는데 일=월 값이 같으면(예: "02 02.180") 일-월-3자리연도 뒤집기가
            # 아니라 같은 값이 반복 인쇄된 잡음일 가능성이 크다. 억지로 만들어내지 않는다.
            if g[0] == g[1]:
                return None
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
# 09-13 Rule 1: 월-일 앞에 글자/숫자(한글 포함)가 전혀 없어야 "줄 맨 앞" 으로 본다.
# 문장부호/공백만 있는 건 허용 (인쇄 얼룩, 말줄임표 등) -- "내용량 10.15 g" 같은 진짜 본문은 걸러진다.
_LEADING_JUNK = re.compile(r"^[^0-9A-Za-z가-힣]*$")
# 뒤에 소문자/퍼센트가 곧장 붙으면(단위 표기 "1.5g", "12.19%") 날짜가 아니라 수량이다.
_UNIT_GLUE = re.compile(r"^[a-z%]")

# 09-12 정크 후보 방지: 매치 시작 바로 앞에 letter+digit 이 섞인 토큰("9808KA1")이 파묻혀 있으면 후보를 버린다.
# "EXP2026.04.18", "L2025.10.09" 처럼 키워드/문자 하나가 순수하게 붙은 경우는 정상 표기라 그대로 둔다.
# 끝 쪽은 LOT/시각이 구분자 없이 붙는 정상 패턴이 많아 검사하지 않는다 ("26.06.227K", "2023.12.0610:13" 등).
_BOUNDARY_WORD = re.compile(r"[A-Za-z0-9]+$")


def _boundary_is_junk(prefix: str) -> bool:
    m = _BOUNDARY_WORD.search(prefix)
    if not m:
        return False
    word = m.group(0)
    return any(c.isdigit() for c in word) and any(c.isalpha() for c in word)
# 09-12 Rule 4: 월+년(m_y) 앞에 day 로 보이는 숫자가 붙어 있으면 일-월-년 완전 날짜의 꼬리라 제외.
# 공백까지 낀 가변 길이 구분자('27 .04.2026')는 lookbehind로 못 잡아 여기서 문자열 끝 검사로 처리.
# TIGHT: 구두점 구분자가 있어야 day 로 본다 ('1 05.2023' 의 홑자리 정크는 구두점이 없어 통과시킨다).
# LOOSE: 공백만 있어도 day 로 본다 (공백 구분 3부분 날짜 '05 04 2021' 보호, 구분자 요구가 느슨해 더 엄격).
_DAY_PREFIX_TIGHT = re.compile(r"\d{1,2}\s*[.\-/,:·년월]\s*$")
_DAY_PREFIX_LOOSE = re.compile(r"\d{1,2}\s*[.\-/,:·년월]?\s*$")
# 매치 안, 숫자와 숫자 사이의 구분자만 추출 (월 이름 옆 글자는 제외)
_INNER_SEPS = re.compile(r"(?<=\d)[^\dA-Za-z]+(?=\d)")


def _sep_kind(sep: str) -> str:
    core = sep.strip()
    if not core:
        return "space"
    # 도트 인쇄에서 점이 콜론으로 읽히는 일이 잦다. 점과 콜론은 같은 종류로 본다 (09-12)
    return "." if core[0] in ".:" else core[0]


def find_candidates(text: str, neighbor_kw: bool = False) -> list[Candidate]:
    """한 조각에서 날짜 후보를 뽑는다. 앞선 패턴이 잡은 구간은 뒤 패턴이 재사용하지 않는다.
    neighbor_kw: (09-13 Rule 1c) 바로 위/아래 줄에 만료 키워드가 있으면 True. 연도 없는 월-일이
    같은 줄에 다른 근거가 없어도 통과하도록 해 준다 (호출자인 _rank 가 이웃 줄을 보고 넘겨준다)."""
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
            # "dmy" 만 검사: 일-월-년을 느슨한 구분자(공백 포함)로 묶는 패턴이라 문자+숫자 코드에서
            # 낱자리 하나를 잘못 뜯어오기 쉽다. "EXP2026.04.18", "2Q27.04.13"(OCR 0->Q) 같은 다른
            # kind 는 키워드/오독 글자 하나가 그대로 붙은 정상 표기라 걸러지면 안 된다.
            if USE_JUNK_GUARD and kind == "dmy" and _boundary_is_junk(norm[:s]):
                continue   # 단어에 파묻힌 숫자 (9808KA1 의 1 이 날짜 첫 자리가 되는 경우)
            if USE_JUNK_GUARD and kind == "m_y":
                # "EXP05/2022", "...BB12/2020" 처럼 글자+숫자 뒤섞인 코드에 곧장 이어진 월/년은
                # 정상 표기이므로 _boundary_is_junk 는 적용하지 않는다 (dmy 전용 가드).
                # 대신 day 로 보이는 숫자가 바로 앞에 붙은 경우(완전 날짜의 꼬리)만 배제한다.
                has_punct_sep = re.search(r"[./\-]", m.group(0)) is not None
                day_guard = _DAY_PREFIX_TIGHT if has_punct_sep else _DAY_PREFIX_LOOSE
                if day_guard.search(norm[:s]):
                    continue   # 앞에 day 로 보이는 숫자가 붙은 일-월-년 완전 날짜의 꼬리
            parsed = _parse(kind, m.groups())
            repaired = False
            if parsed is None and has_expiry:
                parsed = _repair(kind, m.groups())
                repaired = parsed is not None
            if parsed is None:
                continue
            y, mo, d = parsed
            head, tail = norm[:s], norm[e:]
            # 연도 없는 월-일: 뒤에 '까지'나 시각(HH:MM)이 붙거나, 날짜만 있는 짧은 줄이거나,
            # (09-13 Rule 1) 같은 줄 어디든 '까지'가 있거나, 줄 맨 앞(글자/숫자 없이)에서 시작하고
            # 뒤에 잡음이 남아 있을 때만 (시각/잡음 글자가 날짜 뒤에 곧장 붙어 거부되던 경우 구제)
            m_d_line_kw = kind == "m_d" and POST_EXPIRY.search(norm) is not None
            m_d_leads = (kind == "m_d" and _LEADING_JUNK.match(head) is not None
                         and tail.strip() != "" and not _UNIT_GLUE.match(tail))
            if kind == "m_d" and not (POST_EXPIRY.search(tail) or _TIME_AFTER.match(tail)
                                       or _DATE_ONLY_LINE.match(norm) or m_d_line_kw or m_d_leads
                                       or neighbor_kw):
                continue
            why = []
            score = 0.0
            # 접두형 키워드(소비기한:, Best before)는 줄 어디든, 조사형(까지/부터)은 날짜 뒤에 올 때만
            minor = 0.0
            if m_d_line_kw:
                score += 1.5; why.append("같은 줄 까지 (부분 날짜 근거 +1.5)")
            if kind == "m_d" and neighbor_kw and not m_d_line_kw:
                score += 1.5; why.append("이웃 줄 만료 키워드 (부분 날짜 근거 +1.5)")
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
            if USE_JUNK_GUARD:
                seps = _INNER_SEPS.findall(m.group(0))
                if len(seps) >= 2 and len({_sep_kind(s) for s in seps[:2]}) > 1:
                    score -= 1.0; why.append("구분자 불일치 -1")
                if re.search(r"\d,\d", m.group(0)):
                    score -= 1.0; why.append("숫자 안 쉼표 -1")
            if repaired:
                why.append("무효 칸 제거 (부분 날짜)")
            taken.append((s, e))
            out.append(Candidate(y, mo, d, m.group(0), score, why, head, minor, kind))
    return out


def _fmt(v: int | None, width: int) -> str:
    return "NONE" if v is None else str(v).zfill(width)


_SOBI_YUTONG = re.compile(r"소비기한|유통기한")
# 포장일자만 붙은 날짜는 소비기한이 아니다. 만료 키워드가 같은 줄에 없으면 후보에서 뺀다 (09-12 운영진: 알 수 없으면 NONE)
_PACK_ONLY = re.compile(r"포장일자|포장일|포장년월일")


def _rank(texts: list[str], geo: list | None = None) -> list[Candidate]:
    """조각 리스트 -> 점수 반영된 후보 전체 (선택 순 정렬)."""
    texts, kw_why = _correct_lines(texts, geo)
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
        pack_only = _PACK_ONLY.search(own) is not None and not EXPIRY.search(own)
        # 09-13 Rule 1c: 연도 없는 월-일이 같은 줄엔 근거가 없어도 바로 위/아래 줄에
        # 만료 키워드가 있으면(숫자 없는 줄일 때만, 위 ctx/post 와 같은 이웃 규칙) 통과시킨다.
        neighbor_kw = bool(
            (not any(ch.isdigit() for ch in prev) and PRE_EXPIRY.search(prev))
            or (not any(ch.isdigit() for ch in nxt) and PRE_EXPIRY.search(nxt))
        )
        for c in find_candidates(t, neighbor_kw):
            if pack_only:
                continue          # 포장일자 줄의 날짜는 후보에서 제외
            if kw_why[i]:
                c.why = kw_why[i] + c.why
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
            if c.kind == "c6":   # 바코드 등 6자리 압축 오탐은 감점을 유지해 진짜 날짜에 밀리게 한다
                c.score = -1.0
                c.why = ["부터~까지 범위: 늦은 날짜 (6자리 압축 -1 유지)"]
            else:
                c.score = 0.0
                c.why = ["부터~까지 범위: 늦은 날짜"]
    # 소비기한과 유통기한이 함께 있으면 소비기한 우선 (09-11 운영진 판정). 날짜 앞 가장 가까운 만료 키워드가 소비기한인 후보에 +1
    if "소비기한" in joined and "유통기한" in joined:
        for c in cands:
            kws = _SOBI_YUTONG.findall(c.head)
            if kws and kws[-1] == "소비기한":
                c.score += 1.0
                c.why = c.why + ["소비기한 우선 +1 (유통기한과 함께 있음)"]
    # 완전한 날짜가 있으면 부분 날짜는 뺀다. 단 완전 날짜가 전부 제조 쪽(음수)이고 부분 날짜가 만료 쪽(양수)이면 부분 우선
    best_complete = max((c.score for c in complete), default=None)
    best_partial = max((c.score for c in partial), default=None)
    use_partial = False
    if best_complete is not None and best_partial is not None:
        if best_complete < 0 < best_partial:
            use_partial = True
        # 09-12: 접두형 만료 키워드가 붙은 부분 날짜(점수>=2.0)는 키워드 없는 완전 날짜(정크)보다 우선
        elif USE_KEYWORD_PARTIAL and best_partial >= 2.0 and best_complete < 2.0:
            use_partial = True
    pool = partial if use_partial else (complete or partial)
    # 접두형 키워드 점수 > 늦은 날짜 (소비기한은 제조일보다 뒤) > 조사형 키워드
    pool.sort(key=lambda c: (c.score, c.y or 0, c.m or 0, c.d or 0, c.minor), reverse=True)
    return pool


def extract_date(texts: list[str], geo: list | None = None) -> tuple[str, str, str] | None:
    """조각 리스트에서 소비기한 하나를 고른다. 없으면 None.
    geo: 줄마다 (cy, h). 사전 교정의 이웃 줄 범위를 세로 거리로 제한할 때만 쓰인다."""
    pool = _rank(texts, geo)
    if not pool:
        return None
    best = pool[0]
    return (_fmt(best.y, 4), _fmt(best.m, 2), _fmt(best.d, 2))


def explain(texts: list[str], geo: list | None = None) -> tuple[str | None, list[str]]:
    """trace 용: (선택 결과 문자열, 후보별 설명 리스트). 후보는 선택 순."""
    pool = _rank(texts, geo)
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
