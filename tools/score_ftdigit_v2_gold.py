"""파인튜닝 모델을 '숫자 재판독' 자리에만 쓰는 구성으로 골드 1,000장 채점.
한국어 모델은 기존 그대로 두고, 숫자 3개 이상 조각을 다시 읽는 자리(기존 ch_PP-OCRv3)만 교체한다.
앞선 채점(auto_gold_v5_ft.csv)이 끝나기를 기다렸다가 시작해 CPU 경합을 피한다."""
import os, sys, csv, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
WAIT_FOR = None
while False:
    time.sleep(60)
import ocr
ocr._REC_FILES["ch"] = "korean_PP-OCRv5_rec_ft_v2.onnx"   # 숫자 재판독만 파인튜닝 모델로
from pipeline import predict_one, list_images
ids = {l.strip() for l in open("labels/gold_ids.txt", encoding="utf-8") if l.strip()}
out = "labels/auto_gold_v5_ftdigit_v2.csv"
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
