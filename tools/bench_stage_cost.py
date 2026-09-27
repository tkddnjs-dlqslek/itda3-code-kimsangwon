# -*- coding: utf-8 -*-
"""재시도 단계별 비용과 회복률 실측 (09-27).

골드 1,000장 중 채택 구성(labels/auto_gold_v5_mixed_v2.csv)에서 s1/s2 로 끝나지 않은 사진을 대상으로,
조기 종료 없이 모든 단계를 다 돌려 단계마다 (소요 초, 날짜 후보 여부, 골드 정답 여부) 를 기록한다.
단계 순서 재배치와 장당 시간 상한 설계의 근거 자료.

    python tools/bench_stage_cost.py                # 전체 (재시도 209 + fail 25)
    ITDA_LIMIT=20 python tools/bench_stage_cost.py  # 앞 20장만

출력: labels/stage_cost.csv (image_id, stage, seconds, has_date, correct, y, m, d)
이어하기 지원: 이미 기록된 image_id 는 건너뛴다.
"""
import csv
import os
import sys
import time

import cv2
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
import dateparse  # noqa: E402
import ocr  # noqa: E402
from ocr import _clahe, _crops, _load, _ok, _split_rec, group_lines, hybrid_rec  # noqa: E402

IMAGES = os.path.join(REPO, os.pardir, "images")
OUT = os.path.join(REPO, "labels", "stage_cost.csv")
COLS = ["image_id", "stage", "seconds", "has_date", "correct", "y", "m", "d"]


def _read(name):
    with open(os.path.join(REPO, "labels", name), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _find(image_id):
    for ext in (".jpg", ".jpeg", ".png"):
        p = os.path.join(IMAGES, image_id + ext)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(image_id)


def _date(items):
    got = dateparse.extract_date(group_lines(items))
    if got is None:
        return None
    return got


def stages(path):
    """(stage, items) 를 순서대로 낸다. read_raw 와 같은 전처리, 조기 종료 없음."""
    img = _load(path)
    items = _crops(img)
    keep = lambda c: c.shape[0] >= 20 and c.shape[1] / c.shape[0] <= 12
    big = [it for it in items if keep(it[0])]
    small = [it for it in items if not keep(it[0])]
    s1 = hybrid_rec(big)
    yield "s1", s1
    yield "s2", s1 + hybrid_rec(small)
    yield "det5", hybrid_rec(_crops(img, v5=True), retry=True)
    for code, stage in ((cv2.ROTATE_90_CLOCKWISE, "rot90"), (cv2.ROTATE_90_COUNTERCLOCKWISE, "rot270"),
                        (cv2.ROTATE_180, "rot180")):
        yield stage, hybrid_rec(_crops(cv2.rotate(img, code)), retry=True)
    yield "clahe", hybrid_rec(_crops(_clahe(img), loose=True), retry=True)
    yield "hires", hybrid_rec(_crops(_clahe(_load(path, 1920)), loose=True), retry=True)
    up = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    yield "up2x", hybrid_rec(_crops(up, loose=True), retry=True)
    for k in (5, 3):
        yield f"erode{k}", _split_rec(_crops(cv2.erode(img, np.ones((k, k), np.uint8)), loose=True), retry=True)


def main():
    gold = {r["image_id"]: r for r in _read("gold.csv")}
    adopted = _read("auto_gold_v5_mixed_v2.csv")
    targets = [r["image_id"] for r in adopted if r["stage"] not in ("s1", "s2")]
    limit = int(os.environ.get("ITDA_LIMIT", "0") or 0)
    if limit:
        targets = targets[:limit]
    done = set()
    if os.path.exists(OUT):
        done = {r["image_id"] for r in csv.DictReader(open(OUT, encoding="utf-8"))}
    new = os.path.getsize(OUT) == 0 if os.path.exists(OUT) else True
    print(f"targets {len(targets)} | done {len(done)}", flush=True)
    with open(OUT, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
        t_all = time.time()
        for i, iid in enumerate(targets, 1):
            if iid in done:
                continue
            g = gold[iid]
            path = _find(iid)
            t_prev = time.time()
            for stage, items in stages(path):
                now = time.time()
                sec = now - t_prev
                t_prev = now
                got = _date(items)
                if got is None:
                    w.writerow([iid, stage, f"{sec:.3f}", 0, 0, "", "", ""])
                else:
                    y, m, d = got
                    ok = (str(y), str(m), str(d)) == (g["year"], g["month"], g["day"])
                    w.writerow([iid, stage, f"{sec:.3f}", 1, int(ok), y, m, d])
            f.flush()
            if i % 10 == 0:
                print(f"{i}/{len(targets)} {time.time() - t_all:.0f}s", flush=True)
    print("done", OUT)


if __name__ == "__main__":
    main()
