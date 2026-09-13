"""v3 파인튜닝 가중치를 재시도 단계에 물려 골드 1,000장을 다시 읽는다.

제출 코드(src/ocr.py)는 손대지 않고, 임포트 후 RETRY_REC 만 바꿔 끼운다.
    python tools/score_v3_gold.py [가중치파일명] [출력csv]
기본값: korean_PP-OCRv5_rec_ft_v3.onnx -> labels/auto_gold_v5_ft_v3_retry.csv
"""
import csv
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import ocr
from pipeline import list_images, predict_one

WEIGHT = sys.argv[1] if len(sys.argv) > 1 else "korean_PP-OCRv5_rec_ft_v3.onnx"
OUT = sys.argv[2] if len(sys.argv) > 2 else "labels/auto_gold_v5_ft_v3_retry.csv"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

if not os.path.exists(os.path.join("weights", WEIGHT)):
    sys.exit(f"가중치 없음: weights/{WEIGHT}")
ocr.RETRY_REC = WEIGHT
assert ocr._retry_key() == "ko_retry", "재시도 엔진이 base 로 폴백됨. 가중치 로딩 실패"

ids = {l.strip() for l in open("labels/gold_ids.txt", encoding="utf-8") if l.strip()}
paths = [p for p in list_images("../images")
         if os.path.splitext(os.path.basename(p))[0] in ids]

done = set()                                   # 이어하기: 중간에 죽어도 남은 것만 처리
if os.path.exists(OUT):
    done = {r["image_id"] for r in csv.DictReader(open(OUT, encoding="utf-8"))}
    paths = [p for p in paths if os.path.splitext(os.path.basename(p))[0] not in done]
limit = int(os.environ.get("ITDA_LIMIT", "0"))  # 0이면 전부. 메모리가 부족하면 나눠 돌린다
if limit:
    paths = paths[:limit]
print(f"{WEIGHT} | 이번 실행 {len(paths)}장 (완료 {len(done)})", flush=True)

t0 = time.time()
with open(OUT, "a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    if not done:
        w.writerow(["image_id", "year", "month", "day", "final_date", "stage", "texts", "raw"])
    for i, p in enumerate(paths, 1):
        r = predict_one(p, strict=True, retry_upscale=True)
        w.writerow([r["image_id"], r["year"], r["month"], r["day"], r["final_date"],
                    r["stage"], " | ".join(r["texts"]), r["raw"]])
        if i % 100 == 0:
            f.flush()
            print(f"{i}/{len(paths)}  {(time.time()-t0)/i:.2f}s/img", flush=True)
print(f"done {OUT} in {(time.time()-t0)/60:.1f} min")
