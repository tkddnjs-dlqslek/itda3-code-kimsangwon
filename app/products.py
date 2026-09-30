# -*- coding: utf-8 -*-
"""바코드 -> 상품명. 시연용 더미 표를 읽는다. 실제 매장에서는 POS 상품 마스터가 이 자리를 대신한다."""
from __future__ import annotations

import csv
import os

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "products.csv")


def load(path: str = DEFAULT_PATH) -> dict[str, dict]:
    with open(path, encoding="utf-8-sig") as f:
        return {r["barcode"]: dict(r) for r in csv.DictReader(f)}


def lookup(barcode: str, table: dict) -> dict | None:
    return table.get((barcode or "").strip())


# 할인 대상 기준: 소비기한까지 남은 일수가 이 값 이하이면 할인 대상 목록에 올린다 (09-30).
# 유통기한이 수일인 신선식품과 수개월인 가공식품을 같은 기준으로 볼 수 없어 분류별로 둔다.
# 의약품과 화장품은 판매가 아니라 반품 준비 시점이라 길게 잡는다. 매장 운영 정책에 맞춰 조정하는 값이다.
DISCOUNT_DAYS = {"즉석식품": 1, "신선식품": 3, "유제품": 5, "육가공": 7, "음료": 21, "가공식품": 21,
                 "의약품": 90, "의약외품": 90, "화장품": 90}
DEFAULT_DISCOUNT_DAYS = 21


def discount_days(barcode: str, table: dict) -> int:
    found = lookup(barcode, table)
    return DISCOUNT_DAYS.get(found["category"], DEFAULT_DISCOUNT_DAYS) if found else DEFAULT_DISCOUNT_DAYS
