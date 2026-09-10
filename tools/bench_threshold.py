import sys, os, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd, ocr, dateparse
d = pd.read_csv("labels/policy_detail.csv", dtype=str)
ids = list(d[d.P0_ko_first != d.P1_ch_first].image_id)
gold = dict(zip(d.image_id, d.gold))
files = {os.path.splitext(f)[0]: os.path.join("../images", f) for f in os.listdir("../images")}
def ndig(t): return sum(c.isdigit() for c in t)
def complete(t): return any(None not in (c.y, c.m, c.d) for c in dateparse.find_candidates(t))
TH = [3, 5, 6, 8, 10]
hit = {t: 0 for t in TH}; sent = {t: 0 for t in TH}; ncrop = 0
for iid in ids:
    img = ocr._load(files[iid]); items = ocr._crops(img)
    keep = [(c, b) for c, b in items if c.shape[0] >= 20 and c.shape[1] / c.shape[0] <= 12]
    crops = [c for c, _ in keep]; boxes = [b for _, b in keep]; ncrop += len(crops)
    ko = [t for t, _ in ocr._rec("ko")(crops)[0]]
    idx_all = [i for i, t in enumerate(ko) if ndig(t) >= 3]
    ch = [""] * len(ko)
    if idx_all:
        for i, (t, _) in zip(idx_all, ocr._rec("ch")([crops[i] for i in idx_all])[0]): ch[i] = t
    for th in TH:
        texts = [ (ch[i] if (ndig(k) >= th and ch[i] and complete(ch[i])) else k) for i, k in enumerate(ko)]
        sent[th] += sum(1 for k in ko if ndig(k) >= th)
        r = dateparse.extract_date(ocr.group_lines(list(zip(texts, boxes))))
        hit[th] += ("-".join(r) if r else "NONE") == gold[iid]
print(f"불일치 {len(ids)}장, s1 조각 평균 {ncrop/len(ids):.1f}개")
for th in TH: print(f"숫자>={th:2d}: 정답 {hit[th]:2d}/{len(ids)}   ch에 보낸 조각 장당 {sent[th]/len(ids):.1f}개")
