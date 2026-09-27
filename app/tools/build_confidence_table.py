# -*- coding: utf-8 -*-
"""골드 1,000장으로 신뢰도 표를 만들고, 2폴드 교차 검증으로 기준값의 효과를 출력한다.

    python app/tools/build_confidence_table.py

OCR 을 다시 돌리지 않는다. labels/auto_gold_reorder.csv (채택 구성의 골드 예측)에 저장된
texts 와 stage 로 조건을 다시 계산한다.
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "app"))
import confidence  # noqa: E402


def _read(name):
    with open(os.path.join(REPO, "labels", name), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_rows():
    """[(image_id, bucket_key, 정답여부)] 1,000건."""
    gold = {r["image_id"]: r for r in _read("gold.csv")}
    out = []
    for r in _read("auto_gold_reorder.csv"):
        g = gold.get(r["image_id"])
        if g is None:
            continue
        texts = [t.strip() for t in r["texts"].split(" | ")] if r["texts"] else []
        key = confidence.bucket_key(texts, r["stage"], r["year"], r["month"], r["day"])
        ok = (g["year"], g["month"], g["day"]) == (r["year"], r["month"], r["day"])
        out.append((r["image_id"], key, ok))
    return out


def _ids(name):
    with open(os.path.join(REPO, "labels", name), encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def cross_validate(rows):
    """폴드마다 train 으로 표를 만들고 eval 에서 자동 통과 비율과 그 안의 정답률을 잰다."""
    lines = []
    for fold in ("A", "B"):
        train, evl = _ids(f"fold_{fold}_train_ids.txt"), _ids(f"fold_{fold}_eval_ids.txt")
        table = confidence.build_table((k, ok) for i, k, ok in rows if i in train)
        auto = [ok for i, k, ok in rows if i in evl and not confidence.needs_review(k, confidence.lookup(k, table))]
        review = [ok for i, k, ok in rows if i in evl and confidence.needs_review(k, confidence.lookup(k, table))]
        lines.append(
            f"fold {fold}: 자동 통과 {len(auto)}/{len(auto) + len(review)} "
            f"({len(auto) / (len(auto) + len(review)):.1%}), 자동 통과 정답률 {sum(auto) / max(len(auto), 1):.1%}, "
            f"확인 대상 정답률 {sum(review) / max(len(review), 1):.1%}")
    return lines


def main():
    rows = load_rows()
    print(f"rows {len(rows)} | 정답 {sum(ok for _, _, ok in rows)}")
    for line in cross_validate(rows):
        print(line)
    table = confidence.build_table((k, ok) for _, k, ok in rows)
    with open(confidence.TABLE_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(table, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"기준값 {confidence.REVIEW_THRESHOLD} | global {table['global']} | groups {table['groups']}")
    for k, v in table["buckets"].items():
        print(f"  {k:32s} {v}")
    print("written", confidence.TABLE_PATH)


if __name__ == "__main__":
    main()
