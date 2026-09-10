"""fail 이미지에 원본 해상도 재시도 효과. 1920 / 1440 / 축소본 2배(현재) 비교."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd, numpy as np, cv2, ocr, dateparse
g = pd.read_csv("labels/gold.csv", dtype=str).fillna(""); g["gold"] = g.year + "-" + g.month + "-" + g.day
p = pd.read_csv("labels/auto_gold_v4.csv", dtype=str)
ids = list(p[p.stage == "fail"].image_id); gold = dict(zip(g.image_id, g.gold))
files = {os.path.splitext(f)[0]: os.path.join("../images", f) for f in os.listdir("../images")}
def load_side(path, side):
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    s = side / max(img.shape[:2])
    return cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
def run(img, loose=True, v5=False):
    r = dateparse.extract_date(ocr.group_lines(ocr.hybrid_rec(ocr._crops(img, loose=loose, v5=v5))))
    return "-".join(r) if r else "NONE"
V = {"cur_up2x(960x2)": lambda pth: cv2.resize(load_side(pth, 960), None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC),
     "orig1440": lambda pth: load_side(pth, 1440),
     "orig1920": lambda pth: load_side(pth, 1920),
     "orig1920_clahe": lambda pth: cv2.cvtColor(cv2.createCLAHE(3.0, (8, 8)).apply(cv2.cvtColor(load_side(pth, 1920), cv2.COLOR_BGR2GRAY)), cv2.COLOR_GRAY2BGR)}
hit = {k: 0 for k in V}; found = {k: 0 for k in V}; tm = {k: 0.0 for k in V}; union = 0
for i in ids:
    got = {}
    for k, f in V.items():
        t = time.time(); r = run(f(files[i])); tm[k] += time.time() - t
        got[k] = r; found[k] += r != "NONE"; hit[k] += r == gold[i]
    union += any(v == gold[i] for v in got.values())
print(f"fail {len(ids)}장")
for k in V: print(f"{k:18s} 날짜 나옴 {found[k]:3d}  정답 {hit[k]:3d}  {tm[k]/len(ids):.2f}s/img")
print("어느 하나라도 정답:", union)
