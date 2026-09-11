# -*- coding: utf-8 -*-
"""파인튜닝한 ONNX 를 weights/ 에 놓은 뒤 골드셋으로 검증한다.

src/ocr.py 는 수정 금지이므로, 이 스크립트가 import 시점에 ocr._REC_FILES 를 바꿔치기한다.
tools/autolabel.py 의 루프를 그대로 재구현(20줄)해서 labels/auto_gold_ft.csv 를 만들고,
tools/evaluate.py 를 그 파일로 돌린 뒤 auto_gold_v4.csv 와의 diff(고침/깨짐)를 보여준다.

python finetune/validate_local.py --rec korean_PP-OCRv5_rec_ft.onnx
python finetune/validate_local.py --rec korean_PP-OCRv5_rec_ft.onnx --det ch_PP-OCRv5_det_ft.onnx
"""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_REPO, "src"))

_WEIGHTS = os.path.join(_REPO, "weights")
_GOLD_CSV = os.path.join(_REPO, "labels", "gold.csv")
_GOLD_IDS = os.path.join(_REPO, "labels", "gold_ids.txt")
_BASELINE = os.path.join(_REPO, "labels", "auto_gold_v4.csv")
_OUT_CSV = os.path.join(_REPO, "labels", "auto_gold_ft.csv")
_IMAGES_DIR = os.path.normpath(os.path.join(_REPO, os.pardir, "images"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rec", required=True, help="weights/ 안의 새 rec onnx 파일명")
    ap.add_argument("--det", default=None, help="weights/ 안의 새 v4 det onnx 파일명 (선택, phase 2)")
    args = ap.parse_args()

    rec_path = os.path.join(_WEIGHTS, args.rec)
    if not os.path.exists(rec_path):
        sys.exit(f"없음: {rec_path} (RunPod export_rec.sh 결과물을 weights/ 로 복사하세요)")

    import ocr  # noqa: E402
    from pipeline import list_images, predict_one  # noqa: E402

    ocr._REC_FILES["ko"] = args.rec  # src/ocr.py 는 그대로 두고 여기서만 교체
    if args.det:
        det_path = os.path.join(_WEIGHTS, args.det)
        if not os.path.exists(det_path):
            sys.exit(f"없음: {det_path}")
        ocr.DET_FILE = args.det

    ids = {l.strip() for l in open(_GOLD_IDS, encoding="utf-8") if l.strip()}
    paths = [p for p in list_images(_IMAGES_DIR)
              if os.path.splitext(os.path.basename(p))[0] in ids]
    print(f"검증 대상 {len(paths)}장, rec={args.rec}, det={args.det or '(기본)'}")

    t0 = time.time()
    with open(_OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["image_id", "year", "month", "day", "final_date", "stage", "texts", "raw"])
        for i, p in enumerate(paths, 1):
            r = predict_one(p, strict=False, retry_upscale=True)
            w.writerow([r["image_id"], r["year"], r["month"], r["day"], r["final_date"],
                        r["stage"], " | ".join(r["texts"]), r["raw"]])
            if i % 100 == 0:
                f.flush()
                print(f"{i}/{len(paths)}  {(time.time()-t0)/i:.2f}s/img", flush=True)
    print(f"완료: {len(paths)}장, {(time.time()-t0)/60:.1f}분 -> {_OUT_CSV}")

    print("\n===== evaluate.py (파인튜닝 결과) =====")
    subprocess.run([sys.executable, os.path.join(_REPO, "tools", "evaluate.py"), _GOLD_CSV, _OUT_CSV], check=True)

    print("\n===== v4(기존) 대비 diff =====")
    _diff(_GOLD_CSV, _BASELINE, _OUT_CSV)


def _diff(gold_csv: str, old_csv: str, new_csv: str) -> None:
    gold = {r["image_id"]: r for r in csv.DictReader(open(gold_csv, encoding="utf-8"))}
    old = {r["image_id"]: r for r in csv.DictReader(open(old_csv, encoding="utf-8"))}
    new = {r["image_id"]: r for r in csv.DictReader(open(new_csv, encoding="utf-8"))}

    def exact(pred, g):
        return (pred["year"], pred["month"], pred["day"]) == (g["year"], g["month"], g["day"])

    fixed, broke, common = [], [], 0
    for iid, g in gold.items():
        if iid not in old or iid not in new:
            continue
        common += 1
        ok_old, ok_new = exact(old[iid], g), exact(new[iid], g)
        if not ok_old and ok_new:
            fixed.append(iid)
        elif ok_old and not ok_new:
            broke.append(iid)
    print(f"비교 대상: {common}  고침: {len(fixed)}  깨짐: {len(broke)}")
    if fixed:
        print("고침:", ", ".join(fixed[:30]), "..." if len(fixed) > 30 else "")
    if broke:
        print("깨짐:", ", ".join(broke[:30]), "..." if len(broke) > 30 else "")


if __name__ == "__main__":
    main()
