import time, glob, random, re, sys
sys.path.insert(0, "src")
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
DIGITY = re.compile(r"\d{2}[^\d\s]?\s?\d{2}")   # 숫자 덩어리 있는데 유효 날짜 아님 -> 재인식 후보

det = RapidOCR(intra_op_num_threads=4, inter_op_num_threads=1)
ch = RapidOCR(intra_op_num_threads=4, inter_op_num_threads=1, rec_model_path="weights/ch_PP-OCRv3_rec_infer.onnx").text_rec
ko = RapidOCR(intra_op_num_threads=4, inter_op_num_threads=1, rec_model_path="weights/korean_PP-OCRv5_rec_mobile.onnx").text_rec

stats = dict(ch=0, ko=0, hyb=0, union=0, none=0, t_det=0, t_ch=0, t_ko=0, t_hyb=0)
diff = []
for p in sample:
    im = load(p)
    t = time.time(); boxes, _ = det.text_det(im); stats["t_det"] += time.time() - t
    if boxes is None: stats["none"] += 1; continue
    crops = [c for c in det.get_crop_img_list(im, boxes) if c.shape[0] >= 20 and c.shape[1] / c.shape[0] <= 12]
    if not crops: stats["none"] += 1; continue
    t = time.time(); r_ch = [x[0] for x in ch(crops)[0]]; stats["t_ch"] += time.time() - t
    t = time.time(); r_ko = [x[0] for x in ko(crops)[0]]; stats["t_ko"] += time.time() - t
    d_ch, d_ko = valid_dates(r_ch), valid_dates(r_ko)
    # hybrid: ko first; crops whose ko text is digit-y but not a valid date -> rerun with ch
    t = time.time()
    redo = [i for i, tx in enumerate(r_ko) if DIGITY.search(tx) and not valid_dates([tx])]
    r_hyb = list(r_ko)
    if redo:
        for i, (tx, _) in zip(redo, ch([crops[i] for i in redo])[0]): r_hyb[i] = tx
    stats["t_hyb"] += stats["t_ko"] * 0 + (time.time() - t)
    d_hyb = valid_dates(r_hyb)
    stats["ch"] += bool(d_ch); stats["ko"] += bool(d_ko); stats["hyb"] += bool(d_hyb); stats["union"] += bool(d_ch | d_ko)
    if d_ch != d_ko: diff.append((p[-10:], sorted(d_ch), sorted(d_ko), sorted(d_hyb), len(redo)))
n = len(sample)
print(f"images with >=1 valid date: ch {stats['ch']}  ko {stats['ko']}  hybrid {stats['hyb']}  union {stats['union']}  / {n}")
print(f"time/img: det {stats['t_det']/n:.2f}  rec_ch {stats['t_ch']/n:.2f}  rec_ko {stats['t_ko']/n:.2f}  hybrid_extra {stats['t_hyb']/n:.2f}")
print("differences (file, ch, ko, hybrid, n_redo):")
for d in diff: print("  ", d)
