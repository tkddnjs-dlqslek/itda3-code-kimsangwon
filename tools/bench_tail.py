"""재시도 꼬리 단계 구조 비교. 대상: 골드에서 clahe/hires/up2x/fail 로 끝난 이미지."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd, cv2, ocr, dateparse
g = pd.read_csv("labels/gold.csv", dtype=str).fillna(""); g["gold"] = g.year + "-" + g.month + "-" + g.day
p = pd.read_csv("labels/auto_gold_v4.csv", dtype=str)
ids = list(p[p.stage.isin(["clahe", "up2x", "fail"])].image_id); gold = dict(zip(g.image_id, g.gold))
files = {os.path.splitext(f)[0]: os.path.join("../images", f) for f in os.listdir("../images")}
def run(img):
    r = dateparse.extract_date(ocr.group_lines(ocr.hybrid_rec(ocr._crops(img, loose=True))))
    return "-".join(r) if r else None
def ladder(path, steps):
    for name, f in steps:
        r = run(f(path))
        if r: return r, name
    return "NONE", "fail"
CUR = [("clahe", lambda pth: ocr._clahe(ocr._load(pth, 960))),
       ("hires", lambda pth: ocr._clahe(ocr._load(pth, 1920))),
       ("up2x", lambda pth: cv2.resize(ocr._load(pth, 960), None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))]
NEW = [("clahe1920", lambda pth: ocr._clahe(ocr._load(pth, 1920))),
       ("hires1920", lambda pth: ocr._load(pth, 1920))]
NEW2 = [("clahe960", lambda pth: ocr._clahe(ocr._load(pth, 960))),
        ("clahe1920", lambda pth: ocr._clahe(ocr._load(pth, 1920))),
        ("hires1920", lambda pth: ocr._load(pth, 1920))]
for label, steps in (("현재 clahe960>hires1920clahe>up2x", CUR), ("새 clahe1920>hires1920", NEW), ("절충 clahe960>clahe1920>hires1920", NEW2)):
    t = time.time(); hit = 0; found = 0
    for i in ids:
        r, st = ladder(files[i], steps); found += r != "NONE"; hit += r == gold[i]
    print(f"{label:38s} 날짜 나옴 {found:3d}  정답 {hit:3d} / {len(ids)}   {(time.time()-t)/len(ids):.2f}s/img", flush=True)
