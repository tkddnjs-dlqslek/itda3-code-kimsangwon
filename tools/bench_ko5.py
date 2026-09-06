import time, glob, random
import cv2
from rapidocr_onnxruntime import RapidOCR
random.seed(0)
sample = random.sample(sorted(glob.glob("../images/*")), 100)[:20]
def load(p, ms=960):
    img = cv2.imread(p); h, w = img.shape[:2]; s = ms / max(h, w)
    return cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else img
imgs = [load(p) for p in sample]
for name, kw in {"ch_v3": {"rec_model_path": "weights/ch_PP-OCRv3_rec_infer.onnx"},
                 "ko_v5": {"rec_model_path": "weights/korean_PP-OCRv5_rec_mobile.onnx"}}.items():
    e = RapidOCR(intra_op_num_threads=4, inter_op_num_threads=1, **kw)
    e(imgs[0], use_cls=False)
    t = time.time(); rec = 0; outs = []
    for im in imgs:
        r, el = e(im, use_cls=False); rec += el[2]; outs.append([x[1] for x in (r or [])])
    print(f"{name}  total {(time.time()-t)/len(imgs):.2f}s/img  rec {rec/len(imgs):.2f}s/img")
    for o in outs[:5]: print("   ", o)
