"""침식/두줄분리 효과 분리 측정.
v5 채점에서 stage 가 erode5, erode3, fail 인 이미지만 (다른 이미지는 침식 전에 이미 끝나서
no-erode 든 erode 든 결과가 같다) no_erode / erode_no_split 두 변형으로 다시 돌려
labels/bench_erode_split.csv 에 (image_id, variant) 한 쌍당 한 행씩 이어쓴다.
(erode_split = v5 결과를 그대로 쓴다, 이 스크립트는 재실행하지 않는다)

전체를 한 번에 돌리는 용도. 행 하나 계산할 때마다 바로 flush 해서, 강제 종료돼도
(image_id, variant) 쌍 단위로 재실행 시 이어서 돈다. labels/auto_gold_v5.csv 가
gold 1,000장을 다 채울 때까지 자체적으로 기다렸다가 시작한다.

python tools/bench_erode_split.py labels/auto_gold_v5.csv labels/gold.csv
"""
import sys, os, csv, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import ocr
from pipeline import list_images, predict_one

V5, GOLD = sys.argv[1], sys.argv[2]
OUT = "labels/bench_erode_split.csv"
IMG_DIR = "../images"
N_GOLD = 1000
FIELDS = ["image_id", "variant", "year", "month", "day", "final_date", "stage"]

VARIANTS = {
    "no_erode": lambda: setattr(ocr, "USE_ERODE", False),
    "erode_no_split": lambda: (setattr(ocr, "USE_ERODE", True), setattr(ocr, "SPLIT_LINES", False)),
}


def _wait_for_gold(path: str, n: int):
    while True:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                rows = sum(1 for _ in f) - 1  # header 제외
            if rows >= n:
                return
            print(f"waiting: {path} has {rows}/{n} rows", flush=True)
        else:
            print(f"waiting: {path} not found yet", flush=True)
        time.sleep(60)


def main():
    _wait_for_gold(V5, N_GOLD)

    v5_stage = {r["image_id"]: r["stage"] for r in csv.DictReader(open(V5, encoding="utf-8"))}
    targets = sorted(iid for iid, st in v5_stage.items() if st in ("erode5", "erode3", "fail"))
    paths = {os.path.splitext(os.path.basename(p))[0]: p for p in list_images(IMG_DIR)}

    done = set()
    file_exists = os.path.exists(OUT)
    if file_exists:
        with open(OUT, encoding="utf-8") as f:
            done = {(r["image_id"], r["variant"]) for r in csv.DictReader(f)}
    pairs = [(iid, v) for iid in targets for v in VARIANTS if (iid, v) not in done]
    print(f"targets={len(targets)} images, {len(pairs)} (image,variant) pairs left "
          f"({len(done)} already done)", flush=True)

    t0 = time.time()
    with open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not file_exists:
            w.writeheader()
            f.flush()
        n = 0
        for iid, variant in pairs:
            p = paths.get(iid)
            if p is None:
                continue
            VARIANTS[variant]()
            r = predict_one(p, strict=True, retry_upscale=True)
            ocr.USE_ERODE, ocr.SPLIT_LINES = True, True  # 다음 이미지를 위해 기본값(v5) 복원
            w.writerow({"image_id": iid, "variant": variant, "year": r["year"], "month": r["month"],
                        "day": r["day"], "final_date": r["final_date"], "stage": r["stage"]})
            f.flush()
            n += 1
            if n % 10 == 0:
                print(f"{n}/{len(pairs)}  {(time.time() - t0) / n:.2f}s/pair", flush=True)

    print(f"done. total targets={len(targets)} images, {len(done) + len(pairs)} pairs on disk")


if __name__ == "__main__":
    main()
