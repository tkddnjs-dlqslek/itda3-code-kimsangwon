import sys, os, time, glob, random, statistics
import cv2
from rapidocr_onnxruntime import RapidOCR

IMG = "../images"
def load(p, ms=960):
    img = cv2.imread(p); h, w = img.shape[:2]; s = ms / max(h, w)
    return cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else img

random.seed(0)
sample = random.sample(sorted(glob.glob(IMG + "/*")), 100)
imgs = [load(p) for p in sample]

# 1) box count distribution (det only)
det = RapidOCR(intra_op_num_threads=4, inter_op_num_threads=1)
counts = []
t = time.time()
for im in imgs:
    r, _ = det(im, use_cls=False, use_rec=False)
    counts.append(len(r) if r else 0)
print(f"det only: {(time.time()-t)/len(imgs):.2f}s/img")
counts.sort()
print("boxes/img  min", counts[0], "p25", counts[25], "median", counts[50], "p75", counts[75], "p90", counts[90], "max", counts[-1], "mean", round(statistics.mean(counts), 1))

# 2) rec model comparison on 20 images (full pipeline, no cls)
sub = imgs[:20]
models = {
    "ch_v4(default)": {},
    "ch_v3": {"rec_model_path": "weights/ch_PP-OCRv3_rec_infer.onnx"},
    "en_v3": {"rec_model_path": "weights/en_PP-OCRv3_rec_infer.onnx"},
    "ko_v4": {"rec_model_path": "weights/korean_PP-OCRv4_rec_mobile.onnx", "rec_keys_path": "weights/korean_dict.txt"},
    "ko_v5": {"rec_model_path": "weights/korean_PP-OCRv5_rec_mobile.onnx", "rec_keys_path": "weights/korean_dict.txt"},
}
show = {}
for name, kw in models.items():
    try:
        e = RapidOCR(intra_op_num_threads=4, inter_op_num_threads=1, **kw)
        e(sub[0], use_cls=False)
        t = time.time(); rec_t = 0; outs = []
        for im in sub:
            r, el = e(im, use_cls=False); rec_t += el[2]; outs.append([x[1] for x in (r or [])])
        n = len(sub)
        print(f"{name:15s} total {(time.time()-t)/n:.2f}s/img  rec {rec_t/n:.2f}s/img")
        show[name] = outs[:3]
    except Exception as ex:
        print(f"{name:15s} FAILED: {type(ex).__name__}: {str(ex)[:150]}")
for name, outs in show.items():
    print("==", name)
    for o in outs: print("  ", o)
