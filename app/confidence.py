# -*- coding: utf-8 -*-
"""예측 한 건의 신뢰도.

골드 1,000장에서 같은 조건(어느 시도에서 풀렸나, 날짜가 완전한가, 만료 키워드 근거가 있나,
경쟁 후보가 있나)이었던 예측의 실제 정답률을 그대로 점수로 쓴다. 학습 모델이 아니라 조회표라
추가 의존성이 없고, 점수의 뜻이 "이런 경우 골드에서 몇 %가 맞았다"로 바로 설명된다.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import dateparse  # noqa: E402

TABLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "confidence_table.json")
REVIEW_THRESHOLD = 0.90   # 이 값 미만이면 사람이 확인한다
MIN_N = 15                # 표본이 이보다 적은 조건은 표에 넣지 않고 상위 묶음 값으로 대신한다
_FIRST = {"s1", "s2"}
_NONE3 = ("NONE", "NONE", "NONE")


def bucket_key(texts, stage: str, year: str, month: str, day: str) -> str:
    if (year, month, day) == _NONE3:
        return "none"
    group = "first" if stage in _FIRST else ("fail" if stage == "fail" else "retry")
    full = "full" if "NONE" not in (year, month, day) else "part"
    kw = contested = False
    pool = dateparse._rank(list(texts))
    if pool:
        top = pool[0]
        kw = any("만료 키워드" in w or "까지" in w for w in top.why)
        contested = any((c.y, c.m, c.d) != (top.y, top.m, top.d) and c.score >= top.score - 0.5
                        for c in pool[1:])
    return f"{group}|{full}|{'kw' if kw else 'nokw'}|{'contested' if contested else 'clear'}"


def _acc(correct: int, n: int) -> float:
    return round((correct + 1) / (n + 2), 4)   # 라플라스 보정: 표본이 적을 때 0%나 100%로 튀지 않게


def build_table(rows) -> dict:
    total = [0, 0]
    groups: dict[str, list[int]] = {}
    buckets: dict[str, list[int]] = {}
    for key, ok in rows:
        for counter in (total, groups.setdefault(key.split("|")[0], [0, 0]), buckets.setdefault(key, [0, 0])):
            counter[0] += int(ok)
            counter[1] += 1
    return {
        "global": _acc(*total),
        "groups": {g: _acc(*c) for g, c in sorted(groups.items())},
        "buckets": {k: _acc(*c) for k, c in sorted(buckets.items()) if c[1] >= MIN_N},
    }


def lookup(key: str, table: dict) -> float:
    if key in table["buckets"]:
        return table["buckets"][key]
    return table["groups"].get(key.split("|")[0], table["global"])


def load_table(path: str = TABLE_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def needs_review(key: str, conf: float, threshold: float = REVIEW_THRESHOLD) -> bool:
    if key == "none":
        return True
    return conf < threshold or key.split("|")[1] == "part"   # 부분 날짜는 표 점수와 무관하게 항상 확인


def assess(texts, stage: str, year: str, month: str, day: str, table: dict, threshold: float = REVIEW_THRESHOLD) -> dict:
    key = bucket_key(texts, stage, year, month, day)
    conf = lookup(key, table)
    return {"confidence": conf, "needs_review": needs_review(key, conf, threshold), "bucket": key}
