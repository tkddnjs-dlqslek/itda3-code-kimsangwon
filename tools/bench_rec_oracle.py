# -*- coding: utf-8 -*-
"""인식기 오독 오답에 대해, 어떤 인식기/전처리 조합이라도 정답 숫자열을 읽어내는지 본다 (09-28).

errors.csv 의 miss 가 아닌 오답 사진마다: v4 det + v5 det 조각을 모으고, 조각 하나하나를
(ko, ch, ft_v2) x (패딩 0, 가로 12%, 가로 12% + 세로 12%) x (원본, 침식3) 로 읽어
정답 연월일을 담은 문자열이 어디서든 나오는지 기록한다. 투표/패딩 설계의 상한(oracle)을 잰다.

    python tools/bench_rec_oracle.py            # -> labels/rec_oracle.csv
"""
import csv
import os
import re
import sys

import cv2
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
import dateparse  # noqa: E402
import ocr  # noqa: E402

IMAGES = os.path.join(REPO, os.pardir, "images")
OUT = os.path.join(REPO, "labels", "rec_oracle.csv")


def _find(iid):
    for ext in (".jpg", ".jpeg", ".png"):
        p = os.path.join(IMAGES, iid + ext)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(iid)


def _pad_crop(img, box, fx, fy):
    """box(4점)를 가로 fx, 세로 fy 비율만큼 키워 축 정렬로 잘라낸다 (기울기 무시, 오라클용)."""
    b = np.asarray(box, dtype=float)
    x0, y0, x1, y1 = b[:, 0].min(), b[:, 1].min(), b[:, 0].max(), b[:, 1].max()
    w, h = x1 - x0, y1 - y0
    x0, x1 = max(0, x0 - w * fx), min(img.shape[1], x1 + w * fx)
    y0, y1 = max(0, y0 - h * fy), min(img.shape[0], y1 + h * fy)
    return img[int(y0):int(y1), int(x0):int(x1)]


def _matches(text, y, m, d):
    """읽은 문자열의 후보 중 골드와 연월일이 맞는 것이 있나 (NONE 은 무시)."""
    for c in dateparse.find_candidates(text):
        ok = True
        for got, want in ((c.y, y), (c.m, m), (c.d, d)):
            if want != "NONE" and str(got).zfill(len(want)) != want:
                ok = False
        if ok and (c.y is not None or c.m is not None):
            return True
    return False


def main():
    errs = [r for r in csv.DictReader(open(os.path.join(REPO, "labels", "errors.csv"), encoding="utf-8-sig"))
            if r["kind"] != "miss" and r["year_g"] != "NONE"]
    recs = {"ko": ocr._rec("ko"), "ch": ocr._rec("ch"), "ft": ocr._rec(ocr._retry_key())}
    pads = {"p0": (0, 0), "px": (0.12, 0), "pxy": (0.12, 0.12)}
    rows = []
    for n, r in enumerate(errs, 1):
        iid = r["image_id"]
        y, m, d = r["year_g"], r["month_g"], r["day_g"]
        img = ocr._load(_find(iid))
        boxes = [b for _, b in ocr._crops(img)] + [b for _, b in ocr._crops(img, v5=True)]
        digit_boxes = []
        # 숫자가 있을 법한 조각만: 기본 ko 로 한 번 읽어 숫자 2개 이상인 것
        base = ocr._crops(img) + ocr._crops(img, v5=True)
        texts = list(recs["ko"]([c for c, _ in base])[0])
        for (crop, box), (t, conf) in zip(base, texts):
            if sum(ch.isdigit() for ch in t) >= 2:
                digit_boxes.append(box)
        found = {}
        for pname, (fx, fy) in pads.items():
            crops = [_pad_crop(img, b, fx, fy) for b in digit_boxes]
            crops = [c for c in crops if c.size and c.shape[0] >= 8 and c.shape[1] >= 8]
            if not crops:
                continue
            variants = {"raw": crops, "er3": [cv2.erode(c, np.ones((3, 3), np.uint8)) for c in crops]}
            for vname, cs in variants.items():
                for rname, rec in recs.items():
                    out = rec(cs)[0]
                    hit = [t for t, _ in out if _matches(t, y, m, d)]
                    if hit:
                        found[f"{rname}/{pname}/{vname}"] = hit[0]
        rows.append([iid, r["kind"], r["stage"], f"{y}-{m}-{d}", len(found),
                     "; ".join(f"{k}={v}" for k, v in found.items())[:300]])
        print(f"{n}/{len(errs)} {iid} hits={len(found)} {list(found)[:3]}", flush=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["image_id", "kind", "stage", "gold", "n_hits", "hits"])
        w.writerows(rows)
    print("done", OUT, "recoverable", sum(1 for r in rows if r[4] > 0), "/", len(rows))


if __name__ == "__main__":
    main()
