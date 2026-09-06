# -*- coding: utf-8 -*-
"""OCR 텍스트 조각에서 소비기한 날짜를 뽑는 순수 파이썬 규칙 엔진.

파이프라인: 정규화 -> 패턴 순차 매칭(먼저 잡은 구간 우선) -> 달력 검증 -> 점수 -> 선택.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

__all__ = ["Candidate", "find_candidates", "extract_date"]


@dataclass
class Candidate:
    y: int | None
    m: int | None
    d: int | None
    text: str
    score: float


# --- 정규화 ------------------------------------------------------------------
# 숫자가 하나라도 섞인 글자 덩어리 안에서만 O->0, I/l/|->1 (OCT, Lotto 같은 단어는 보존)
_TR = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "|": "1"})
_NUMISH = re.compile(r"[0-9OoIl|]{2,}")


def _norm(text: str) -> str:
    return _NUMISH.sub(lambda m: m.group(0).translate(_TR) if any(c.isdigit() for c in m.group(0)) else m.group(0), text)


# --- 키워드 ------------------------------------------------------------------
EXPIRY = re.compile(r"소비기한|유통기한|까지|\bexp\b|best before|best by|\bbbe\b|use by", re.I)
MFG = re.compile(r"제조|생산|부터|\bmfg\b|\bmfd\b|\bprod\b|\blot\b", re.I)

# --- 패턴 --------------------------------------------------------------------
SEP_K = r"\s*[.\-/,:·년월]\s*"   # 국내 라벨 구분자 (쉼표, 콜론 OCR 오인식 포함)
SEP_D = r"[.\-/·\s]"             # 수입품 구분자 (콜론 제외: 시각과 충돌)
MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
MONTHS = {n: i + 1 for i, n in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}

# (정규식, 그룹 해석, 만료키워드 필요 여부)
_PATTERNS = [
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
    # 31/12/2023 수입품 일-월-연
    (re.compile(r"(?<!\d)(\d{1,2})" + SEP_D + r"(\d{1,2})" + SEP_D + r"(\d{3,5})(?!\d)"), "dmy", False),
    # 25.12.10 국내 두 자리 연도 먼저 (연도로 성립할 때만 통과)
    (re.compile(r"(?<!\d)(\d{2})" + SEP_K + r"(\d{1,2})" + SEP_K + r"(\d{1,2})(?!\d)"), "ymd", False),
    # 10.10.21 두 자리 연도가 뒤 (위 규칙이 실패했을 때만 도달)
    (re.compile(r"(?<!\d)(\d{1,2})" + SEP_D + r"(\d{1,2})" + SEP_D + r"(\d{2})(?!\d)"), "dmy", False),
    # Exp:091122 압축 DDMMYY 는 만료 키워드 바로 뒤에서만
    (re.compile(r"\b(?:exp|bbe|use by|best before|best by)\b\s*[:.]?\s*(\d{2})(\d{2})(\d{2})(?!\d)", re.I), "dmy", False),
    # 정확히 8자리일 때만 YYYYMMDD (13/14자리 바코드, 품목보고번호 배제)
    (re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)"), "ymd", False),
    # 부분: OCT.2021 (OCT.o2021 처럼 앞에 o 가 붙어 5자리가 되는 경우도 _year 가 흡수)
    (re.compile(MON + r"[a-z]*\.?\s*(\d{3,5})(?!\d)", re.I), "mon_y", False),
    # 부분: 11/2023
    (re.compile(r"(?<!\d)(\d{1,2})\s*/\s*(\d{4})(?!\d)"), "m_y", False),
    # 부분: 10.22 (extract_date 에서 만료 키워드가 있을 때만 채택)
    (re.compile(r"(?<!\d)(\d{1,2})[.\-](\d{1,2})(?!\d)"), "m_d", False),
]


def _year(tok: str) -> int | None:
    """연도 토큰 정규화. 5자리는 앞 자리 붙음, 0으로 시작하는 3자리는 앞 자리 유실."""
    if len(tok) == 5:
        tok = tok[1:]
    if len(tok) == 3 and tok[0] == "0":
        tok = "2" + tok
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
    if kind == "ymd":
        return _complete(_year(g[0]), int(g[1]), int(g[2]))
    if kind == "dmy":
        d, m, y = int(g[0]), int(g[1]), _year(g[2])
        # 일-월 기본, 그 순서가 달력에 없으면 월-일로 뒤집어 본다
        return _complete(y, m, d) or _complete(y, d, m)
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
    if kind == "m_d":
        m, d = int(g[0]), int(g[1])
        return (None, m, d) if 1 <= m <= 12 and 1 <= d <= 31 else None
    raise ValueError(kind)


def find_candidates(text: str) -> list[Candidate]:
    """한 조각에서 날짜 후보를 뽑는다. 앞선 패턴이 잡은 구간은 뒤 패턴이 재사용하지 않는다."""
    norm = _norm(text)
    has_expiry = EXPIRY.search(norm) is not None
    base = (2.0 if has_expiry else 0.0) - (2.0 if MFG.search(norm) else 0.0)
    taken: list[tuple[int, int]] = []
    out: list[Candidate] = []
    for rx, kind, needs_kw in _PATTERNS:
        if needs_kw and not has_expiry:
            continue
        for m in rx.finditer(norm):
            s, e = m.span()
            if any(s < te and ts < e for ts, te in taken):
                continue
            parsed = _parse(kind, m.groups())
            if parsed is None:
                continue
            y, mo, d = parsed
            # 네 자리 연도로 적힌 형태를 두 자리 연도보다 살짝 신뢰한다
            score = base + (0.5 if y is not None and len(_year_token(kind, m.groups())) >= 3 else 0.0)
            taken.append((s, e))
            out.append(Candidate(y, mo, d, m.group(0), score))
    return out


_YEAR_GROUP = {"ymd": 0, "dmy": 2, "mon_d_y": 2, "d_mon_y": 2, "mon_y": 1, "m_y": 1}


def _year_token(kind: str, g: tuple) -> str:
    i = _YEAR_GROUP.get(kind)
    return "" if i is None else g[i]


def _fmt(v: int | None, width: int) -> str:
    return "NONE" if v is None else str(v).zfill(width)


def extract_date(texts: list[str]) -> tuple[str, str, str] | None:
    """조각 리스트에서 소비기한 하나를 고른다. 없으면 None."""
    anywhere_expiry = any(EXPIRY.search(_norm(t)) for t in texts)
    cands: list[Candidate] = []
    for i, t in enumerate(texts):
        prev = _norm(texts[i - 1]) if i else ""
        # 키워드가 앞 조각에만 있고 날짜는 다음 조각에 찍히는 라벨이 흔하다
        ctx = (2.0 if EXPIRY.search(prev) else 0.0) - (2.0 if MFG.search(prev) else 0.0)
        for c in find_candidates(t):
            # 연도 없는 월-일 조각은 만료 키워드가 어딘가 있어야 날짜로 인정
            if c.y is None and not anywhere_expiry:
                continue
            c.score += ctx
            cands.append(c)
    if not cands:
        return None
    # 완전한 날짜가 하나라도 있으면 부분 날짜는 후보에서 뺀다
    pool = [c for c in cands if None not in (c.y, c.m, c.d)] or cands
    # 점수 우선, 동점이면 늦은 날짜 (소비기한은 제조일보다 뒤)
    best = max(pool, key=lambda c: (c.score, c.y or 0, c.m or 0, c.d or 0))
    return (_fmt(best.y, 4), _fmt(best.m, 2), _fmt(best.d, 2))
