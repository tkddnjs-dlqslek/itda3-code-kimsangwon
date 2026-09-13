"""파인튜닝 rec(korean_PP-OCRv5_rec_ft_v2.onnx)로 골드 1,000장 재실행. 한 줄마다 flush, 이어하기 지원."""
import os, sys, csv, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import ocr
ocr._REC_FILES["ko"] = "korean_PP-OCRv5_rec_ft_v2.onnx"   # 엔진 캐시 전에 교체
from pipeline import predict_one, list_images
ids = {l.strip() for l in open("labels/gold_ids.txt", encoding="utf-8") if l.strip()}
out = "labels/auto_gold_v5_ft_v2.csv"
done = set()
if os.path.exists(out):
    done = {r["image_id"] for r in csv.DictReader(open(out, encoding="utf-8"))}
paths = [p for p in list_images("../images") if os.path.splitext(os.path.basename(p))[0] in ids
         and os.path.splitext(os.path.basename(p))[0] not in done]
t0 = time.time()
with open(out, "a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    if not done:
        w.writerow(["image_id", "year", "month", "day", "final_date", "stage", "texts", "raw"])
    for i, p in enumerate(paths, 1):
        r = predict_one(p, strict=False, retry_upscale=True)
        w.writerow([r["image_id"], r["year"], r["month"], r["day"], r["final_date"], r["stage"],
                    " | ".join(r["texts"]), r["raw"]])
        f.flush()
        if i % 50 == 0:
            print(f"{i}/{len(paths)} {(time.time()-t0)/i:.2f}s/img", flush=True)
print("DONE", flush=True)
