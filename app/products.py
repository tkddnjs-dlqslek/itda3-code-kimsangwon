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
