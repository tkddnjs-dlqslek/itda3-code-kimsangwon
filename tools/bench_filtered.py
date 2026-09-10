"""s1 에서 틀린 이미지: 정답이 필터로 걸러진 작은 조각에 있었는지."""
import sys, os, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd, ocr, dateparse
g = pd.read_csv("labels/gold.csv", dtype=str).fillna(""); g["gold"] = g.year + "-" + g.month + "-" + g.day
p = pd.read_csv("labels/auto_gold_v4.csv", dtype=str).fillna("")
m = g.merge(p[["image_id", "final_date", "stage"]], on="image_id")
wrong = m[(m.stage == "s1") & (m.final_date != m.gold)]
files = {os.path.splitext(f)[0]: os.path.join("../images", f) for f in os.listdir("../images")}
def dates(items):
    out = set()
    for t in ocr.group_lines(items):
        for c in dateparse.find_candidates(t):
            if None not in (c.y, c.m, c.d): out.add(f"{c.y}-{c.m:02d}-{c.d:02d}")
    return out
in_small = 0; in_big = 0; nowhere = 0; rows = []
for _, r in wrong.iterrows():
    img = ocr._load(files[r.image_id]); items = ocr._crops(img)
    keep = lambda c: c.shape[0] >= 20 and c.shape[1] / c.shape[0] <= 12
    big = [it for it in items if keep(it[0])]
    small = [it for it in items if not keep(it[0])]
    db = dates(ocr.hybrid_rec(big)); ds = dates(ocr.hybrid_rec(small)) if small else set()
    if r.gold in db: in_big += 1; k = "s1조각에 있음(규칙이 못 고름)"
    elif r.gold in ds: in_small += 1; k = "걸러진 조각에 있음"
    else: nowhere += 1; k = "어디에도 없음(OCR 오독)"
    rows.append((r.image_id, r.gold, r.final_date, k))
print(f"s1 오답 {len(wrong)}장: s1 조각에 정답 있음 {in_big} / 걸러진 조각에만 있음 {in_small} / 어디에도 없음 {nowhere}")
for x in rows: print(" ", x)
