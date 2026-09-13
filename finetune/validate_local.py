# -*- coding: utf-8 -*-
"""파인튜닝한 ONNX 를 weights/ 에 놓은 뒤 평가셋으로 검증한다.

src/ocr.py 는 수정 금지이므로, 이 스크립트가 import 시점에 ocr._REC_FILES 를 바꿔치기한다.
tools/autolabel.py 의 루프를 그대로 재구현(20줄)해서 예측 CSV 를 만들고 채점한다.

평가셋 두 가지 (--eval-set 로 선택, 기본 gold):
  gold    : labels/gold.csv 기준 골드 1,000장. year/month/day 정확히 채점.
  expdate : ../expdate_check/expdate_answers.csv 기준. 골드 1,000장과 겹치는 image_id 는
            제외. 정답이 " | " 로 여러 개일 수 있어(제조일/유통기한 표기가 모호한 사례)
            후보 중 하나와 일치하면 정답으로 인정.
  both    : 위 둘 다 실행.

  **주의(09-12 확인)**: expdate 평가셋의 image_id 1,300개(골드 제외)는 전부
  finetune_data/ 학습 데이터의 원본 사진과 겹친다(같은 사진의 다른 크롭이 학습에
  쓰였음). 즉 expdate 평가셋 점수는 "본 사진으로 채점"이라 파인튜닝 효과가 실제보다
  부풀어 보일 수 있다. 신뢰할 수 있는 지표는 골드 1,000장(특히 2-fold 모드) 뿐이고,
  expdate 점수는 참고용(오독 패턴 확인, 회귀 체크)으로만 쓸 것.

모델 비교 방식:
  --rec 후보(파인튜닝) 모델과 --baseline 모델(기본값: 현재 production 모델
  korean_PP-OCRv5_rec_mobile.onnx)을 같은 이미지에 대해 각각 돌려 exact/field 점수와
  고침/깨짐 이미지 목록을 바로 비교한다. baseline 을 후보와 같은 파일로 주면(또는
  --no-baseline) 스모크 테스트(같은 모델끼리 비교해 점수가 같은지 확인)로 쓸 수 있다.

  python finetune/validate_local.py --rec korean_PP-OCRv5_rec_ft.onnx --eval-set both
  python finetune/validate_local.py --rec korean_PP-OCRv5_rec_mobile.onnx --eval-set gold --limit 30   # 드라이런

2-fold 모드(골드 전용, leakage 없이 골드 1,000장 전체를 "자신을 학습에 안 쓴 모델"로
채점하고 싶을 때): fold A 모델은 000501~001000 만, fold B 모델은 000001~000500 만
채점해서 두 결과를 합친다. 기존 auto_gold_v4.csv 와의 diff 도 같이 보여준다.
  python finetune/validate_local.py --rec-a korean_ft_foldA.onnx --rec-b korean_ft_foldB.onnx
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
_LABELS = os.path.join(_REPO, "labels")
_GOLD_CSV = os.path.join(_LABELS, "gold.csv")
_GOLD_IDS = os.path.join(_LABELS, "gold_ids.txt")
_BASELINE_CSV = os.path.join(_LABELS, "auto_gold_v4.csv")
_OUT_CSV = os.path.join(_LABELS, "auto_gold_ft.csv")
_EXPDATE_CSV = os.path.normpath(os.path.join(_REPO, os.pardir, "expdate_check", "expdate_answers.csv"))
_EXPDATE_OUT_CSV = os.path.join(_LABELS, "auto_expdate_ft.csv")
_IMAGES_DIR = os.path.normpath(os.path.join(_REPO, os.pardir, "images"))
_DEFAULT_BASELINE = "korean_PP-OCRv5_rec_mobile.onnx"  # 현재 production 모델 (weights/ 기본 파일)


def _load_ids(path: str) -> list:
    return [l.strip() for l in open(path, encoding="utf-8") if l.strip()]


def _check(name: str) -> str:
    path = os.path.join(_WEIGHTS, name)
    if not os.path.exists(path):
        sys.exit(f"없음: {path} (RunPod export_rec.sh 결과물을 weights/ 로 복사하세요)")
    return path


def _set_engine(ocr, rec: str, det: str | None) -> None:
    """src/ocr.py 는 안 건드리고, 여기서 모듈 전역만 바꿔치기한다.
    엔진은 이름으로 캐시되므로 rec/det 파일을 바꿀 때마다 캐시를 비워야 실제로 새 가중치가 실린다."""
    _check(rec)
    ocr._ENGINES.pop("ko", None)
    ocr._REC_FILES["ko"] = rec
    if det:
        _check(det)
        ocr._ENGINES.pop("det", None)
        ocr._ENGINES.pop("det_loose", None)
        ocr.DET_FILE = det


def _predict(predict_one, list_images, ids: set, label: str) -> list:
    paths = [p for p in list_images(_IMAGES_DIR) if os.path.splitext(os.path.basename(p))[0] in ids]
    print(f"[{label}] 검증 대상 {len(paths)}장", flush=True)
    rows = []
    t0 = time.time()
    for i, p in enumerate(paths, 1):
        rows.append(predict_one(p, strict=False, retry_upscale=True))
        if i % 100 == 0:
            print(f"[{label}] {i}/{len(paths)}  {(time.time() - t0) / i:.2f}s/img", flush=True)
    print(f"[{label}] 완료: {len(paths)}장, {(time.time() - t0) / 60:.1f}분", flush=True)
    return rows


def _write_csv(rows: list, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["image_id", "year", "month", "day", "final_date", "stage", "texts", "raw"])
        for r in rows:
            w.writerow([r["image_id"], r["year"], r["month"], r["day"], r["final_date"],
                        r["stage"], " | ".join(r["texts"]), r["raw"]])


def _score(gold_by_id: dict, rows: list, label: str) -> None:
    n = exact = field_sum = 0
    for r in rows:
        g = gold_by_id.get(r["image_id"])
        if g is None:
            continue
        n += 1
        ok = (r["year"] == g["year"], r["month"] == g["month"], r["day"] == g["day"])
        exact += int(all(ok))
        field_sum += sum(ok) / 3
    if n == 0:
        print(f"[{label}] 대상 0장")
        return
    print(f"[{label}] n={n}  exact={exact / n:.3f}  field_score={field_sum / n:.3f}")


def _load_expdate(exclude_ids: set) -> dict:
    """image_id -> [(year,month,day), ...] 후보 리스트. exclude_ids(골드) 는 제외."""
    out = {}
    with open(_EXPDATE_CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            iid = r["image_id"]
            if iid in exclude_ids:
                continue
            cands = []
            for d in r["expdate_date"].split("|"):
                parts = d.strip().split("-")
                if len(parts) == 3:
                    cands.append(tuple(parts))
            if cands:
                out[iid] = cands
    return out


def _score_multi(gold_multi: dict, rows: list, label: str) -> None:
    """ExpDate 셋 채점. exact 는 정답 후보 중 하나와 3필드 모두 일치하면 인정.
    field 는 필드별로 아무 후보와 일치하면 맞은 것으로 치는 관대한 근사치
    (서로 다른 후보의 필드를 섞어 맞혀도 인정 — 부분점수를 후하게 보는 근사, 엄밀한
    "하나의 정답을 통째로 맞혔는지"는 exact 로 확인할 것)."""
    n = exact = field_sum = 0
    for r in rows:
        cands = gold_multi.get(r["image_id"])
        if cands is None:
            continue
        n += 1
        pred = (r["year"], r["month"], r["day"])
        exact += int(any(pred == c for c in cands))
        field_hits = sum(1 for i in range(3) if any(pred[i] == c[i] for c in cands))
        field_sum += field_hits / 3
    if n == 0:
        print(f"[{label}] 대상 0장")
        return
    print(f"[{label}] n={n}  exact={exact / n:.3f}  field_score={field_sum / n:.3f}")


def _diff_rows(truth: dict, rows_old: list, rows_new: list, exact_fn, label: str) -> None:
    old_by_id = {r["image_id"]: r for r in rows_old}
    new_by_id = {r["image_id"]: r for r in rows_new}
    fixed, broke, common = [], [], 0
    for iid, g in truth.items():
        if iid not in old_by_id or iid not in new_by_id:
            continue
        common += 1
        ok_old, ok_new = exact_fn(old_by_id[iid], g), exact_fn(new_by_id[iid], g)
        if not ok_old and ok_new:
            fixed.append(iid)
        elif ok_old and not ok_new:
            broke.append(iid)
    print(f"[{label}] 비교 대상: {common}  고침: {len(fixed)}  깨짐: {len(broke)}")
    if fixed:
        print("  고침:", ", ".join(fixed[:30]), "..." if len(fixed) > 30 else "")
    if broke:
        print("  깨짐:", ", ".join(broke[:30]), "..." if len(broke) > 30 else "")


_EXACT_GOLD = lambda row, g: (row["year"], row["month"], row["day"]) == (g["year"], g["month"], g["day"])
_EXACT_MULTI = lambda row, cands: (row["year"], row["month"], row["day"]) in cands


def _run_eval_set(ocr, list_images, predict_one, name: str, ids: set, truth: dict, scorer,
                   rec: str, baseline: str | None, det: str | None, limit: int | None,
                   out_csv: str | None, exact_fn) -> None:
    if limit:
        ids = set(sorted(ids)[:limit])
    print(f"\n===== {name} (n={len(ids)}) =====")
    rows_by_label = {}
    for label, rec_name in (("baseline", baseline), ("candidate", rec)):
        if rec_name is None:
            continue
        _set_engine(ocr, rec_name, det)
        rows = _predict(predict_one, list_images, ids, f"{name}/{label}:{rec_name}")
        scorer(truth, rows, f"{name}/{label}")
        rows_by_label[label] = rows
    if "candidate" in rows_by_label and out_csv:
        _write_csv(rows_by_label["candidate"], out_csv)
        print(f"[{name}] candidate 예측 -> {out_csv}")
    if "baseline" in rows_by_label and "candidate" in rows_by_label:
        _diff_rows(truth, rows_by_label["baseline"], rows_by_label["candidate"], exact_fn, name)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rec", default=None, help="후보(파인튜닝) rec onnx 파일명 (weights/ 기준). "
                                                  "--rec-a/--rec-b 와 함께 쓸 수 없음")
    ap.add_argument("--baseline", default=_DEFAULT_BASELINE,
                     help=f"비교 기준 rec onnx 파일명 (기본: 현재 production {_DEFAULT_BASELINE}). "
                          "비워서 비교를 끄려면 빈 문자열 전달: --baseline ''")
    ap.add_argument("--rec-a", default=None, help="[골드 전용 2-fold] fold A 모델 (000001~000500 학습) -> 000501~001000 채점")
    ap.add_argument("--rec-b", default=None, help="[골드 전용 2-fold] fold B 모델 (000501~001000 학습) -> 000001~000500 채점")
    ap.add_argument("--det", default=None, help="weights/ 안의 새 det onnx 파일명 (선택, 모든 모드 공통, baseline/candidate 동일 det 사용)")
    ap.add_argument("--eval-set", choices=["gold", "expdate", "both"], default="gold",
                     help="gold=labels/gold.csv, expdate=expdate_check/expdate_answers.csv(골드 제외), both=둘 다")
    ap.add_argument("--limit", type=int, default=None, help="평가셋마다 앞에서 N장만 (드라이런용)")
    args = ap.parse_args()

    if args.rec and (args.rec_a or args.rec_b):
        sys.exit("--rec 은 --rec-a/--rec-b 와 함께 쓸 수 없음")
    if bool(args.rec_a) != bool(args.rec_b):
        sys.exit("2-fold 모드는 --rec-a 와 --rec-b 를 둘 다 지정해야 함")
    if not args.rec and not args.rec_a:
        sys.exit("--rec 또는 (--rec-a 와 --rec-b) 중 하나는 필요")
    if args.rec_a and args.eval_set != "gold":
        sys.exit("2-fold 모드(--rec-a/--rec-b)는 gold 전용. expdate 는 --rec 단일 모드로 실행하세요")

    baseline = args.baseline or None

    import ocr  # noqa: E402
    from pipeline import list_images, predict_one  # noqa: E402

    gold_by_id = {r["image_id"]: r for r in csv.DictReader(open(_GOLD_CSV, encoding="utf-8"))}

    if args.rec_a:
        ids_a_eval = set(_load_ids(os.path.join(_LABELS, "fold_A_eval_ids.txt")))
        ids_b_eval = set(_load_ids(os.path.join(_LABELS, "fold_B_eval_ids.txt")))

        _set_engine(ocr, args.rec_a, args.det)
        rows_a = _predict(predict_one, list_images, ids_a_eval, "fold A")
        _set_engine(ocr, args.rec_b, args.det)
        rows_b = _predict(predict_one, list_images, ids_b_eval, "fold B")

        combined = rows_a + rows_b
        _write_csv(combined, _OUT_CSV)
        print(f"\n===== 2-fold 결과 (골드 {len(combined)}장, 전부 학습 안 한 모델이 채점) =====")
        _score(gold_by_id, combined, "전체")
        _score(gold_by_id, rows_a, "fold A (eval 000501~001000)")
        _score(gold_by_id, rows_b, "fold B (eval 000001~000500)")

        print(f"\n-> {_OUT_CSV}")
        print("\n===== evaluate.py =====")
        subprocess.run([sys.executable, os.path.join(_REPO, "tools", "evaluate.py"), _GOLD_CSV, _OUT_CSV], check=True)

        print("\n===== v4(기존) 대비 diff =====")
        old = {r["image_id"]: r for r in csv.DictReader(open(_BASELINE_CSV, encoding="utf-8"))}
        _diff_rows(gold_by_id, list(old.values()), combined, _EXACT_GOLD, "2-fold vs v4")
        return

    # 단일 --rec 모드: eval-set 별로 baseline(기본 production 모델) 대비 candidate 비교
    if args.eval_set in ("gold", "both"):
        gold_ids = set(_load_ids(_GOLD_IDS))
        _run_eval_set(ocr, list_images, predict_one, "gold", gold_ids, gold_by_id, _score,
                      args.rec, baseline, args.det, args.limit, _OUT_CSV, _EXACT_GOLD)

    if args.eval_set in ("expdate", "both"):
        gold_ids_all = set(_load_ids(_GOLD_IDS))
        expdate_multi = _load_expdate(gold_ids_all)
        print("\n[경고] ExpDate 평가셋 image_id 는 finetune_data/ 학습 소스 사진과 대부분 겹침"
              "(09-12 확인, 골드 제외분 100% 겹침). 파인튜닝 효과가 부풀어 보일 수 있으니 참고용으로만"
              " 볼 것 — 신뢰 가능한 지표는 gold(특히 --rec-a/--rec-b 2-fold).")
        _run_eval_set(ocr, list_images, predict_one, "expdate", set(expdate_multi), expdate_multi, _score_multi,
                      args.rec, baseline, args.det, args.limit, _EXPDATE_OUT_CSV, _EXACT_MULTI)


if __name__ == "__main__":
    main()
