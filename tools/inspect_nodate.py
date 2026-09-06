import glob, random, re, sys, csv
import cv2
from datetime import date
from rapidocr_onnxruntime import RapidOCR
random.seed(0)
sample = random.sample(sorted(glob.glob("../images/*")), 100)
def load(p, ms=960):
    img = cv2.imread(p); h, w = img.shape[:2]; s = ms / max(h, w)
    return cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else img
PAT = re.compile(r"(?<!\d)(20\d{2}|\d{2})[.\-/년 ]\s?(\d{1,2})[.\-/월 ]\s?(\d{1,2})(?!\d)")
def valid_dates(texts):
    out = set()
    for t in texts:
        for m in PAT.finditer(t):
            y, mo, d = m.groups(); y = int(y); y = y + 2000 if y < 100 else y
            try: date(y, int(mo), int(d))
            except ValueError: continue
            if 2015 <= y <= 2040: out.add(f"{y}-{int(mo):02d}-{int(d):02d}")
    return out
DIGITY = re.compile(r"\d{2}[^\d\s]?\s?\d{2}")
det = RapidOCR(intra_op_num_threads=4, inter_op_num_threads=1)
ch = RapidOCR(intra_op_num_threads=4, inter_op_num_threads=1, rec_model_path="weights/ch_PP-OCRv3_rec_infer.onnx").text_rec
ko = RapidOCR(intra_op_num_threads=4, inter_op_num_threads=1, rec_model_path="weights/korean_PP-OCRv5_rec_mobile.onnx").text_rec
rows = []
for p in sample:
    im = load(p); boxes, _ = det.text_det(im)
    crops_all = det.get_crop_img_list(im, boxes) if boxes is not None else []
    s1 = [c for c in crops_all if c.shape[0] >= 20 and c.shape[1] / c.shape[0] <= 12]
    s2 = [c for c in crops_all if not (c.shape[0] >= 20 and c.shape[1] / c.shape[0] <= 12)]
    def hyb(crops):
        if not crops: return []
        r = [x[0] for x in ko(crops)[0]]
        redo = [i for i, t in enumerate(r) if DIGITY.search(t) and not valid_dates([t])]
        if redo:
            for i, (t, _) in zip(redo, ch([crops[i] for i in redo])[0]): r[i] = t
        return r
    t1 = hyb(s1); d1 = valid_dates(t1)
    t2 = hyb(s2) if not d1 else []; d2 = valid_dates(t2)
    rows.append([p.split("/")[-1], len(crops_all), len(s1), " ".join(sorted(d1)), " ".join(sorted(d2)), " | ".join(t1 + t2)])
with open("labels/inspect100.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["file", "n_boxes", "n_stage1", "date_stage1", "date_stage2", "texts"]); w.writerows(rows)
nd = [r for r in rows if not r[3]]
print("stage1 no date:", len(nd), " of which stage2 found:", sum(bool(r[4]) for r in nd))
for r in nd: print(r[0], r[1], r[2], "| s2:", r[4], "|", r[5][:150])
