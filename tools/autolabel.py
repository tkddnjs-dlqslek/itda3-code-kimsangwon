"""전량 자동 라벨. python tools/autolabel.py ../images labels/auto.csv"""
import sys, os, time, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from pipeline import list_images, predict_one

src, out = sys.argv[1], sys.argv[2]
paths = list_images(src)
t0 = time.time()
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["image_id", "year", "month", "day", "final_date", "stage", "texts"])
    for i, p in enumerate(paths, 1):
        r = predict_one(p, strict=True, retry_upscale=True)
        w.writerow([r["image_id"], r["year"], r["month"], r["day"], r["final_date"], r["stage"], " | ".join(r["texts"])])
        if i % 100 == 0:
            f.flush()
            print(f"{i}/{len(paths)}  {(time.time()-t0)/i:.2f}s/img", flush=True)
print(f"done {len(paths)} in {(time.time()-t0)/60:.1f} min")
