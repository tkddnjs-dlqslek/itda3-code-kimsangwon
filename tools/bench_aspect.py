import time, glob, random, re, collections
import cv2
from rapidocr_onnxruntime import RapidOCR
random.seed(0)
sample = random.sample(sorted(glob.glob("../images/*")), 40)
DATE = re.compile(r"(?<!\d)(20\d{2}|\d{2})[.\-/ ]?\s?(\d{1,2})[.\-/ ]?\s?(\d{1,2})(?!\d)")
def load(p, ms=960):
    img = cv2.imread(p); h, w = img.shape[:2]; s = ms / max(h, w)
    return cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else img
e = RapidOCR(intra_op_num_threads=4, inter_op_num_threads=1, rec_model_path="weights/ch_PP-OCRv3_rec_infer.onnx")
imgs = [load(p) for p in sample]
# 1) per-crop time by aspect bucket, and which crops carry dates
bucket_t = collections.defaultdict(list); date_ratio = []
for im in imgs:
    boxes, _ = e.text_det(im)
    if boxes is None: continue
    for c in e.get_crop_img_list(im, boxes):
        h, w = c.shape[:2]; r = w / max(h, 1)
        t = time.time(); (txt, conf), = e.text_rec([c])[0]; dt = time.time() - t
        b = "<4" if r < 4 else "<8" if r < 8 else "<12" if r < 12 else "<20" if r < 20 else ">=20"
        bucket_t[b].append(dt)
        if conf >= 0.5 and DATE.search(txt): date_ratio.append(round(r, 1))
for b in ["<4", "<8", "<12", "<20", ">=20"]:
    v = bucket_t[b]; print(f"aspect {b:4s} n={len(v):4d} mean {sum(v)/max(len(v),1)*1000:.0f}ms")
print("aspect ratios of crops containing a date:", sorted(date_ratio))
# 2) end-to-end with filters, each config twice, report min
def run(im, min_h, max_r):
    boxes, _ = e.text_det(im)
    if boxes is None: return []
    crops = [c for c in e.get_crop_img_list(im, boxes) if c.shape[0] >= min_h and c.shape[1] / c.shape[0] <= max_r]
    if not crops: return []
    return [t for t, c in e.text_rec(crops)[0] if c >= 0.5]
for min_h, max_r in [(0, 999), (0, 12), (16, 12), (20, 12), (20, 10)]:
    best = 9e9; found = 0
    for rep in range(2):
        t = time.time(); f = 0
        for im in imgs:
            f += any(DATE.search(x) for x in run(im, min_h, max_r))
        best = min(best, (time.time() - t) / len(imgs)); found = f
    print(f"min_h={min_h:2d} max_ratio={max_r:3d}  {best:.2f}s/img  date_found {found}/40")
