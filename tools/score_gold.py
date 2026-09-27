# -*- coding: utf-8 -*-
"""현재 src/ 그대로 골드 1,000장을 읽어 CSV 로 남긴다 (변경 채택 판정용).
    python tools/score_gold.py labels/auto_gold_reorder.csv
이어하기와 ITDA_LIMIT 청크 지원. 채점 노트북과 같은 인자(strict=False, retry_upscale=True), 예산 없음."""
import csv, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from pipeline import list_images, predict_one
OUT = sys.argv[1] if len(sys.argv) > 1 else "labels/auto_gold_reorder.csv"
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ids = {l.strip() for l in open(os.environ.get("ITDA_IDS", "labels/gold_ids.txt"), encoding="utf-8") if l.strip()}
paths = [p for p in list_images("../images") if os.path.splitext(os.path.basename(p))[0] in ids]
done = set()
if os.path.exists(OUT):
    done = {r["image_id"] for r in csv.DictReader(open(OUT, encoding="utf-8"))}
    paths = [p for p in paths if os.path.splitext(os.path.basename(p))[0] not in done]
limit = int(os.environ.get("ITDA_LIMIT", "0"))
if limit:
    paths = paths[:limit]
print(f"이번 실행 {len(paths)}장 (완료 {len(done)})", flush=True)
t0 = time.time()
with open(OUT, "a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    if not done:
        w.writerow(["image_id", "year", "month", "day", "final_date", "stage", "seconds", "texts", "raw"])
    for i, p in enumerate(paths, 1):
        t = time.time()
        r = predict_one(p, strict=False, retry_upscale=True)
        w.writerow([r["image_id"], r["year"], r["month"], r["day"], r["final_date"], r["stage"],
                    f"{time.time() - t:.2f}", " | ".join(r["texts"]), r["raw"]])
        if i % 50 == 0:
            f.flush(); print(f"{i}/{len(paths)} {(time.time() - t0) / i:.2f}s/img", flush=True)
print(f"done {OUT} in {(time.time() - t0) / 60:.1f} min")
