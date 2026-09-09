"""숫자 조각 rec 정책 비교 (s1 단계만, 골드 전체). python tools/bench_policy.py labels/gold.csv"""
import sys, os, csv, re, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import ocr, dateparse
gold = {r["image_id"]: f'{r["year"]}-{r["month"]}-{r["day"]}' for r in csv.DictReader(open(sys.argv[1], encoding="utf-8"))}
files = {os.path.splitext(f)[0]: os.path.join("../images", f) for f in os.listdir("../images")}
ocr._REC_FILES["ch5"] = "ch_PP-OCRv5_rec_mobile.onnx"
def complete(t):
    return any(None not in (c.y, c.m, c.d) for c in dateparse.find_candidates(t))
def ndig(t): return sum(ch.isdigit() for ch in t)
POL = {
 "P0_ko_first": lambda ko, ch: ch if (ndig(ko) >= 3 and not complete(ko) and ch) else ko,
 "P1_ch_first": lambda ko, ch: ch if (ch and complete(ch)) else ko,
 "P2_more_digits": lambda ko, ch: (ch if (ch and complete(ch) and (not complete(ko) or ndig(ch) >= ndig(ko))) else ko),
 "P3_ch_if_disagree_year": lambda ko, ch: ch if (ch and complete(ch) and (not complete(ko) or ch != ko)) else ko,
}
hits = {k: 0 for k in POL}; n = 0
out = open("labels/policy_detail.csv", "w", newline="", encoding="utf-8"); w = csv.writer(out); w.writerow(["image_id", "gold"] + list(POL))
for iid, g in gold.items():
    img = ocr._load(files[iid]); items = ocr._crops(img)
    keep = [(c, b) for c, b in items if c.shape[0] >= 20 and c.shape[1] / c.shape[0] <= 12]
    if not keep: continue
    crops = [c for c, _ in keep]; boxes = [b for _, b in keep]
    ko = [t for t, cf in ocr._rec("ko")(crops)[0]]
    idx = [i for i, t in enumerate(ko) if ndig(t) >= 3]
    ch = [""] * len(ko)
    if idx:
        for i, (t, cf) in zip(idx, ocr._rec("ch")([crops[i] for i in idx])[0]): ch[i] = t
    row = [iid, g]; n += 1
    for name, f in POL.items():
        texts = [f(k, c) for k, c in zip(ko, ch)]
        lines = ocr.group_lines(list(zip(texts, boxes)))
        d = dateparse.extract_date(lines); ds = "-".join(d) if d else "NONE"
        hits[name] += ds == g; row.append(ds)
    w.writerow(row)
    if n % 100 == 0: print(n, {k: v for k, v in hits.items()}, flush=True)
print("FINAL n=", n, hits)
