import sys, time, glob, random, re
import cv2, numpy as np
from rapidocr_onnxruntime import RapidOCR


IMG = "../images"
random.seed(0)
sample = random.sample(sorted(glob.glob(IMG + "/*")), 40)
DATE = re.compile(r"(?<!\d)(20\d{2}|\d{2})[.\-/ ]?\s?(\d{1,2})[.\-/ ]?\s?(\d{1,2})(?!\d)")

def load(p, ms):
    img = cv2.imread(p); h, w = img.shape[:2]; s = ms / max(h, w)
    return cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else img

def run(e, img, min_h, batch):
    boxes, _ = e.text_det(img)
    if boxes is None: return [], 0
    crops = e.get_crop_img_list(img, boxes)
    keep = [c for c in crops if c.shape[0] >= min_h]
    if not keep: return [], 0
    e.text_rec.rec_batch_num = batch
    res, _ = e.text_rec(keep)
    return [t for t, c in res if c >= 0.5], len(keep)

e = RapidOCR(intra_op_num_threads=4, inter_op_num_threads=1, rec_model_path="weights/ch_PP-OCRv3_rec_infer.onnx")
configs = [(960, 0, 6), (960, 0, 16), (800, 0, 16), (640, 0, 16), (960, 16, 16), (960, 20, 16), (800, 16, 16)]
imgs = {ms: [load(p, ms) for p in sample] for ms in (960, 800, 640)}
run(e, imgs[960][0], 0, 6)
base = None
for ms, mh, bt in configs:
    t = time.time(); found = 0; nbox = 0; dates = []
    for im in imgs[ms]:
        texts, n = run(e, im, mh, bt); nbox += n
        d = sorted(set(m.group(0) for tx in texts for m in DATE.finditer(tx)))
        dates.append(d); found += bool(d)
    if base is None: base = dates
    agree = sum(a == b for a, b in zip(base, dates))
    print(f"ms={ms} min_h={mh:2d} batch={bt:2d}  {(time.time()-t)/len(sample):.2f}s/img  boxes/img {nbox/len(sample):.1f}  date_found {found}/{len(sample)}  same_as_base {agree}/{len(sample)}")
