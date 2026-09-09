"""숫자 오독 이미지: 날짜 조각을 ko/ch3/ch5/en5 로 각각 읽어 어느 모델이 정답인지."""
import sys, os, csv, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import ocr, dateparse
gold = {r["image_id"]: f'{r["year"]}-{r["month"]}-{r["day"]}' for r in csv.DictReader(open("labels/gold.csv", encoding="utf-8"))}
err = [r for r in csv.DictReader(open("labels/errors.csv", encoding="utf-8")) if r["kind"] in ("wrong_day", "wrong_md", "wrong_year")]
files = {os.path.splitext(f)[0]: os.path.join("../images", f) for f in os.listdir("../images")}
recs = {"ko": "korean_PP-OCRv5_rec_mobile.onnx", "ch3": "ch_PP-OCRv3_rec_infer.onnx", "ch5": "ch_PP-OCRv5_rec_mobile.onnx", "en5": "en_PP-OCRv5_rec_mobile.onnx"}
for k, f in recs.items(): ocr._REC_FILES[k] = f
def dates_of(texts):
    out = set()
    for t in texts:
        for c in dateparse.find_candidates(t):
            if None not in (c.y, c.m, c.d): out.add(f"{c.y}-{c.m:02d}-{c.d:02d}")
    return out
hits = {k: 0 for k in recs}; anyhit = 0; rows = []
for r in err:
    iid = r["image_id"]; img = ocr._load(files[iid]); items = ocr._crops(img)
    crops = [c for c, _ in items]
    if not crops: continue
    per = {}
    for k in recs:
        res = ocr._rec(k)(crops)[0]
        per[k] = dates_of([t for t, conf in res if conf >= 0.3])
    g = gold[iid]
    ok = [k for k in recs if g in per[k]]
    for k in ok: hits[k] += 1
    anyhit += bool(ok)
    rows.append((iid, g, ok, {k: sorted(v)[:3] for k, v in per.items()}))
print(f"숫자 오독 {len(err)}장: 정답을 낸 모델 수  " + "  ".join(f"{k}:{v}" for k, v in hits.items()) + f"  어느 하나라도:{anyhit}")
for row in rows: print(row)
