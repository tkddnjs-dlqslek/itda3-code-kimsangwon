# -*- coding: utf-8 -*-
"""중고거래 기한 검증 판정. 읽은 소비기한과 오늘, 기준 개월 수로 등록 가능(allow), 불가(block), 운영자 확인(review) 을 정한다.

규칙 (첫 번째 해당 규칙 적용):
  1. 연도 또는 월을 못 읽음 -> review
  2. 판독 신뢰도가 낮음(needs_review) -> review (남은 개월은 참고용으로 같이 돌려준다)
  3. 일을 못 읽었으면 그 달 1일로 보수적으로 계산
  4. 오늘 이전 -> block
  5. 남은 개월 < 기준 -> block
  6. 그 외 -> allow
"""
from __future__ import annotations

import datetime


def months_between(a: datetime.date, b: datetime.date) -> int:
    """a 에서 b 까지 만 개월. b 의 일이 a 의 일보다 앞서면 한 달을 채우지 못한 것으로 본다."""
    months = (b.year - a.year) * 12 + (b.month - a.month)
    if b.day < a.day:
        months -= 1
    return months


def verdict(year: str, month: str, day: str, today: datetime.date, min_months: int, needs_review: bool) -> dict:
    if year == "NONE" or month == "NONE":
        return {"verdict": "review", "months_left": None, "deadline": None,
                "reason": "소비기한을 읽지 못했습니다. 표시 부분을 다시 찍어 올려 주십시오"}
    try:
        deadline = datetime.date(int(year), int(month), 1 if day == "NONE" else int(day))
    except ValueError:
        return {"verdict": "review", "months_left": None, "deadline": None,
                "reason": "읽은 날짜가 달력에 없는 값입니다. 운영자 확인이 필요합니다"}
    left = months_between(today, deadline)
    out = {"months_left": left, "deadline": deadline.isoformat()}
    if needs_review:
        return {**out, "verdict": "review", "reason": "판독 신뢰도가 낮아 운영자 확인이 필요합니다"}
    if deadline < today:
        return {**out, "verdict": "block", "reason": "소비기한이 지났습니다"}
    if left < min_months:
        return {**out, "verdict": "block", "reason": f"소비기한이 {left}개월 남아 기준 {min_months}개월에 미달합니다"}
    return {**out, "verdict": "allow", "reason": f"소비기한이 {left}개월 남았습니다. 등록 가능합니다"}


def listing_verdict(results: list[dict], today: datetime.date, min_months: int) -> dict:
    """게시글 사진 여러 장(최대 5장)을 한 번에 판정한다.

    날짜를 읽은 사진들 중 가장 빠른(가장 보수적인) 소비기한을 기준으로 삼는다.
    그 사진의 verdict() 결과를 그대로 쓰되, block 사유만 "N개월 이상 남을 때만" 문구로 통일한다.
    """
    dated = []
    for r in results:
        if r["year"] == "NONE" or r["month"] == "NONE":
            continue
        v = verdict(r["year"], r["month"], r["day"], today, min_months, r["needs_review"])
        if v["deadline"] is None:          # 달력에 없는 값(예: 13월): 날짜 있는 사진으로 치지 않는다
            continue
        dated.append((r["index"], v))
    if not dated:
        return {"verdict": "review", "months_left": None, "deadline": None, "min_photo": None,
                "reason": "소비기한 표시 부분이 보이는 사진을 추가해 주십시오"}
    dated.sort(key=lambda iv: iv[1]["deadline"])
    index, v = dated[0]
    if v["verdict"] == "block":
        v = {**v, "reason": ("소비기한이 지난 상품은 업로드할 수 없습니다" if min_months == 0
                             else f"소비기한(유통기한)이 {min_months}개월 이상 남을 때만 업로드 가능합니다")}
    return {**v, "min_photo": index,
            "dates": [{"index": i, "deadline": vv["deadline"], "months_left": vv["months_left"]} for i, vv in dated]}
