"""전량 자동 라벨. python tools/autolabel.py ../images labels/auto.csv"""
import sys, os, time, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from pipeline import list_images, predict_one

src, out = sys.argv[1], sys.argv[2]
paths = list_images(src)
done = set()
if os.path.exists(out):                       # 이어하기: 이미 처리한 image_id 건너뜀
    done = {r["image_id"] for r in csv.DictReader(open(out, encoding="utf-8"))}
    paths = [p for p in paths if os.path.splitext(os.path.basename(p))[0] not in done]
    print(f"resume: {len(done)} done, {len(paths)} left", flush=True)
t0 = time.time()
with open(out, "a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    if not done:
        w.writerow(["image_id", "year", "month", "day", "final_date", "stage", "texts"])
    for i, p in enumerate(paths, 1):
        r = predict_one(p, strict=True, retry_upscale=True)
        w.writerow([r["image_id"], r["year"], r["month"], r["day"], r["final_date"], r["stage"], " | ".join(r["texts"])])
        if i % 100 == 0:
            f.flush()
            print(f"{i}/{len(paths)}  {(time.time()-t0)/i:.2f}s/img", flush=True)
print(f"done {len(paths)} in {(time.time()-t0)/60:.1f} min")
