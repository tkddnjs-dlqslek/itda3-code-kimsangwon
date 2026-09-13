"""쉬운 단계(s1, s2)는 기존 한국어 모델, 재시도 단계(det5 이후)는 파인튜닝 v2 로 읽는 혼합 구성.
근거: v2 는 골드 전체에서는 밀리지만 어려운 사진 41장에서 크게 앞섰다 (기존 3, v1 11, v2 16).
어려운 사진은 대부분 재시도 단계로 내려오므로 그 구간만 v2 로 바꾼다."""
import os, sys, csv, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import cv2, numpy as np
import dateparse, ocr

WAIT = ["labels/auto_gold_v5_ft_v2.csv", "labels/auto_gold_v5_ftdigit_v2.csv", "labels/auto_gold_v5_ftmerge_v2.csv"]
def rows(p):
    return sum(1 for _ in open(p, encoding="utf-8")) - 1 if os.path.exists(p) else 0
while any(rows(p) < 1000 for p in WAIT):
    time.sleep(120)

ocr._REC_FILES["kov2"] = "korean_PP-OCRv5_rec_ft_v2.onnx"

def hybrid_with(items, ko_key):
    if not items:
        return []
    crops = [c for c, _ in items]
    res = list(ocr._rec(ko_key)(crops)[0])
    redo = [i for i, (t, _) in enumerate(res)
            if sum(ch.isdigit() for ch in t) >= 3 or dateparse.find_candidates(t)]
    if redo:
        for i, (t, conf) in zip(redo, ocr._rec("ch")([crops[i] for i in redo])[0]):
            if ocr._has_complete_date(t) or not ocr._has_complete_date(res[i][0]):
                res[i] = (t, conf)
    return [(t, box) for (t, conf), (_, box) in zip(res, items) if conf >= ocr._MIN_CONF]

def read_mixed(path):
    img = ocr._load(path)
    keep = lambda c: c.shape[0] >= 20 and c.shape[1] / c.shape[0] <= 12
    items = ocr._crops(img)
    big = [it for it in items if keep(it[0])]
    small = [it for it in items if not keep(it[0])]
    out = hybrid_with(big, "ko")
    if ocr._ok(out):
        return out, "s1"
    out = out + hybrid_with(small, "ko")
    if ocr._ok(out):
        return out, "s2"
    # 여기부터 파인튜닝 v2
    saved = ocr.hybrid_rec
    ocr.hybrid_rec = lambda it: hybrid_with(it, "kov2")     # _split_rec 내부 호출도 v2 로
    try:
        d5 = hybrid_with(ocr._crops(img, v5=True), "kov2")
        if ocr._ok(d5):
            return d5, "det5"
        out += d5
        for code, stage in ((cv2.ROTATE_90_CLOCKWISE, "rot90"), (cv2.ROTATE_90_COUNTERCLOCKWISE, "rot270"),
                            (cv2.ROTATE_180, "rot180")):
            rot = hybrid_with(ocr._crops(cv2.rotate(img, code)), "kov2")
            if ocr._ok(rot):
                return rot, stage
            out += rot
        cl = hybrid_with(ocr._crops(ocr._clahe(img), loose=True), "kov2")
        if ocr._ok(cl):
            return cl, "clahe"
        out += cl
        hi = hybrid_with(ocr._crops(ocr._clahe(ocr._load(path, 1920)), loose=True), "kov2")
        if ocr._ok(hi):
            return hi, "hires"
        out += hi
        up = hybrid_with(ocr._crops(cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC), loose=True), "kov2")
        if ocr._ok(up):
            return up, "up2x"
        out += up
        for k in (5, 3):
            er = ocr._split_rec(ocr._crops(cv2.erode(img, np.ones((k, k), np.uint8)), loose=True))
            if ocr._ok(er):
                return er, f"erode{k}"
            out += er
    finally:
        ocr.hybrid_rec = saved
    return out, "fail"

from pipeline import list_images
ids = {l.strip() for l in open("labels/gold_ids.txt", encoding="utf-8") if l.strip()}
out_csv = "labels/auto_gold_v5_mixed_v2.csv"
done = set()
if os.path.exists(out_csv):
    done = {r["image_id"] for r in csv.DictReader(open(out_csv, encoding="utf-8"))}
paths = [p for p in list_images("../images") if os.path.splitext(os.path.basename(p))[0] in ids
         and os.path.splitext(os.path.basename(p))[0] not in done]
t0 = time.time()
with open(out_csv, "a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    if not done:
        w.writerow(["image_id", "year", "month", "day", "final_date", "stage", "texts"])
    for i, p in enumerate(paths, 1):
        iid = os.path.splitext(os.path.basename(p))[0]
        try:
            items, stage = read_mixed(p)
            lines = ocr.group_lines(items)
            r = dateparse.extract_date(lines)
            y, m, d = r if r else ("NONE", "NONE", "NONE")
        except Exception as e:
            y = m = d = "NONE"; stage = f"error:{type(e).__name__}"; lines = []
        final = "NONE" if (y, m, d) == ("NONE", "NONE", "NONE") else f"{y}-{m}-{d}"
        w.writerow([iid, y, m, d, final, stage, " | ".join(lines)])
        f.flush()
        if i % 50 == 0:
            print(f"{i}/{len(paths)} {(time.time()-t0)/i:.2f}s/img", flush=True)
print("DONE", flush=True)
