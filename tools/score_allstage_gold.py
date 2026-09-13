"""속도 여유(현재 한도의 34%)를 써서, 첫 성공에서 멈추지 않고 단계를 더 진행하는 실험.
각 단계마다 그 단계 글자만으로 후보를 뽑아 점수를 매기고, '확실한' 후보가 나오면 멈춘다.
확실하지 않으면 다음 단계를 계속 밟고, 마지막에 전체 단계 중 가장 점수 높은 후보를 고른다."""
import os, sys, csv, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import cv2, numpy as np
import dateparse as D, ocr
from pipeline import list_images

STRONG = 2.0        # 접두 만료 키워드(+2)를 받은 완전 날짜면 즉시 채택

def best_of(lines):
    pool = D._rank(lines)
    if not pool:
        return None, -99.0
    c = pool[0]
    complete = None not in (c.y, c.m, c.d)
    return c, (c.score + (0.5 if complete else 0.0))

def read_best(path):
    img = ocr._load(path)
    keep = lambda c: c.shape[0] >= 20 and c.shape[1] / c.shape[0] <= 12
    items = ocr._crops(img)
    big = [it for it in items if keep(it[0])]
    small = [it for it in items if not keep(it[0])]
    stages = [("s1", lambda: ocr.hybrid_rec(big)),
              ("s2", lambda: ocr.hybrid_rec(small)),
              ("det5", lambda: ocr.hybrid_rec(ocr._crops(img, v5=True))),
              ("rot90", lambda: ocr.hybrid_rec(ocr._crops(cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)))),
              ("rot270", lambda: ocr.hybrid_rec(ocr._crops(cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)))),
              ("rot180", lambda: ocr.hybrid_rec(ocr._crops(cv2.rotate(img, cv2.ROTATE_180)))),
              ("clahe", lambda: ocr.hybrid_rec(ocr._crops(ocr._clahe(img), loose=True))),
              ("hires", lambda: ocr.hybrid_rec(ocr._crops(ocr._clahe(ocr._load(path, 1920)), loose=True))),
              ("up2x", lambda: ocr.hybrid_rec(ocr._crops(cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC), loose=True))),
              ("erode5", lambda: ocr._split_rec(ocr._crops(cv2.erode(img, np.ones((5, 5), np.uint8)), loose=True))),
              ("erode3", lambda: ocr._split_rec(ocr._crops(cv2.erode(img, np.ones((3, 3), np.uint8)), loose=True)))]
    acc, best, bscore, bstage = [], None, -99.0, "fail"
    for name, fn in stages:
        got = fn()
        acc += got
        lines = ocr.group_lines(got if name != "s2" else acc)
        c, sc = best_of(lines)
        if c is not None and sc > bscore:
            best, bscore, bstage = c, sc, name
        if best is not None and bscore >= STRONG:
            break
    if best is None:
        c, sc = best_of(ocr.group_lines(acc))
        if c is not None:
            best, bstage = c, "merged"
    if best is None:
        return ("NONE", "NONE", "NONE"), "fail"
    f = lambda v, w: "NONE" if v is None else str(v).zfill(w)
    return (f(best.y, 4), f(best.m, 2), f(best.d, 2)), bstage

ids = {l.strip() for l in open("labels/gold_ids.txt", encoding="utf-8") if l.strip()}
out = "labels/auto_gold_v5_allstage.csv"
done = set()
if os.path.exists(out):
    done = {r["image_id"] for r in csv.DictReader(open(out, encoding="utf-8"))}
paths = [p for p in list_images("../images") if os.path.splitext(os.path.basename(p))[0] in ids
         and os.path.splitext(os.path.basename(p))[0] not in done]
t0 = time.time()
with open(out, "a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    if not done:
        w.writerow(["image_id", "year", "month", "day", "final_date", "stage", "sec"])
    for i, p in enumerate(paths, 1):
        s = time.time()
        try:
            (y, m, d), st = read_best(p)
        except Exception as e:
            y = m = d = "NONE"; st = f"error:{type(e).__name__}"
        final = "NONE" if (y, m, d) == ("NONE", "NONE", "NONE") else f"{y}-{m}-{d}"
        w.writerow([os.path.splitext(os.path.basename(p))[0], y, m, d, final, st, round(time.time() - s, 2)])
        f.flush()
        if i % 50 == 0:
            print(f"{i}/{len(paths)} {(time.time()-t0)/i:.2f}s/img", flush=True)
print("DONE", flush=True)
