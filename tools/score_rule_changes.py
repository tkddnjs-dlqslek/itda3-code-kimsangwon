# -*- coding: utf-8 -*-
"""Change 1/2 규칙 온오프 조합별 골드/리뷰셋 점수 재계산 (OCR 재실행 없음).

texts 컬럼(" | " 로 조인된 OCR 조각)만 다시 파싱해서 gold.csv / nongold_review_parsed.csv 와 비교한다.
"""
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
import dateparse  # noqa: E402

LABELS = REPO / "labels"

GOLD_FILES = {
    "hybrid(v5)": LABELS / "auto_gold_v5.csv",
    "ko(v5_ko)": LABELS / "auto_gold_v5_ko.csv",
    "merge(v5_merge)": LABELS / "auto_gold_v5_merge.csv",
}

CONFIGS = {
    "baseline": (False, False),
    "change1_only": (True, False),
    "change2_only": (False, True),
    "both": (True, True),
}


def _predict(texts_field: str) -> tuple[str, str, str]:
    if not isinstance(texts_field, str) or not texts_field:
        texts = []
    else:
        texts = texts_field.split(" | ")
    result = dateparse.extract_date(texts)
    if result is None:
        return ("NONE", "NONE", "NONE")
    return result


def _score(pred_df: pd.DataFrame, truth: dict[str, tuple[str, str, str]]) -> tuple[int, float, int]:
    """(exact_count, field_accuracy, n) — truth: image_id -> (y,m,d) 문자열 3튜플."""
    exact = 0
    field_correct = 0
    field_total = 0
    n = 0
    for _, row in pred_df.iterrows():
        img = row["image_id"]
        if img not in truth:
            continue
        n += 1
        py, pm, pd_ = row["_pred"]
        ty, tm, td = truth[img]
        if (py, pm, pd_) == (ty, tm, td):
            exact += 1
        field_correct += (py == ty) + (pm == tm) + (pd_ == td)
        field_total += 3
    return exact, (field_correct / field_total if field_total else 0.0), n


def _norm3(y, m, d) -> tuple[str, str, str]:
    def f(v):
        v = str(v).strip()
        return "NONE" if v.upper() in ("NONE", "NAN", "") else v.zfill(2) if len(v) <= 2 and v.isdigit() else v
    return f(y), f(m), f(d)


def load_gold_truth() -> dict[str, tuple[str, str, str]]:
    g = pd.read_csv(LABELS / "gold.csv", dtype=str)
    out = {}
    for _, row in g.iterrows():
        out[row["image_id"]] = _norm3(row["year"], row["month"], row["day"])
    return out


def load_review_truth() -> dict[str, tuple[str, str, str]]:
    r = pd.read_csv(LABELS / "nongold_review_parsed.csv", dtype=str)
    sub = r[r["kind"].isin(["parsed", "partial"]) & r["ans"].notna() & (r["ans"].str.strip() != "")]
    out = {}
    for _, row in sub.iterrows():
        parts = row["ans"].strip().split("-")
        y, m, d = (parts + ["NONE", "NONE", "NONE"])[:3]
        out[row["image_id"]] = _norm3(y, m, d)
    return out


def run_config(junk: bool, keyword_partial: bool):
    dateparse.USE_JUNK_GUARD = junk
    dateparse.USE_KEYWORD_PARTIAL = keyword_partial

    gold_truth = load_gold_truth()
    review_truth = load_review_truth()

    gold_results = {}
    for name, path in GOLD_FILES.items():
        df = pd.read_csv(path, dtype=str)
        df["_pred"] = df["texts"].apply(_predict)
        exact, field, n = _score(df, gold_truth)
        gold_results[name] = (exact, field, n)

    retry_df = pd.read_csv(LABELS / "auto_nongold_retry_v5.csv", dtype=str)
    retry_df["_pred"] = retry_df["texts"].apply(_predict)
    review_exact, review_field, review_n = _score(retry_df, review_truth)

    return gold_results, (review_exact, review_field, review_n), retry_df


def image_pred_map(retry_df: pd.DataFrame) -> dict[str, tuple[str, str, str]]:
    return {row["image_id"]: row["_pred"] for _, row in retry_df.iterrows()}


def gold_pred_map(junk: bool, keyword_partial: bool, which: str) -> dict[str, tuple[str, str, str]]:
    dateparse.USE_JUNK_GUARD = junk
    dateparse.USE_KEYWORD_PARTIAL = keyword_partial
    df = pd.read_csv(GOLD_FILES[which], dtype=str)
    df["_pred"] = df["texts"].apply(_predict)
    return {row["image_id"]: row["_pred"] for _, row in df.iterrows()}


def main():
    gold_truth = load_gold_truth()
    review_truth = load_review_truth()
    print(f"gold n={len(gold_truth)}, reviewed-subset n={len(review_truth)}\n")

    all_results = {}
    for cfg_name, (junk, kp) in CONFIGS.items():
        gold_results, review_result, retry_df = run_config(junk, kp)
        all_results[cfg_name] = (gold_results, review_result, retry_df)
        print(f"=== {cfg_name} (USE_JUNK_GUARD={junk}, USE_KEYWORD_PARTIAL={kp}) ===")
        for name, (exact, field, n) in gold_results.items():
            print(f"  gold/{name:16s} exact={exact}/{n} ({exact/n:.4f})  field={field:.4f}")
        r_exact, r_field, r_n = review_result
        print(f"  reviewed-subset      exact={r_exact}/{r_n} ({r_exact/r_n:.4f})  field={r_field:.4f}")
        print()

    base_exact, base_field, base_n = all_results["baseline"][0]["hybrid(v5)"]
    print(f"[check] baseline hybrid gold exact={base_exact} (expect 878), field={base_field:.4f} (expect 0.9130)")
    if base_exact != 878 or abs(base_field - 0.9130) > 0.0005:
        print("[check] MISMATCH vs expected baseline numbers -- see report")

    # 변경 전/후(둘 다 vs baseline) 골드 hybrid에서 정오 방향이 바뀐 image_id
    truth = gold_truth
    base_pred = gold_pred_map(False, False, "hybrid(v5)")
    both_pred = gold_pred_map(True, True, "hybrid(v5)")
    fixed, broken = [], []
    for img, t in truth.items():
        if img not in base_pred or img not in both_pred:
            continue
        b_ok = base_pred[img] == t
        n_ok = both_pred[img] == t
        if not b_ok and n_ok:
            fixed.append(img)
        elif b_ok and not n_ok:
            broken.append(img)
    print(f"\n[gold hybrid, both vs baseline] fixed={len(fixed)} {fixed[:30]}")
    print(f"[gold hybrid, both vs baseline] broken={len(broken)} {broken[:30]}")

    # 리뷰 서브셋에서 baseline vs both 로 고쳐지거나 깨진 image_id
    base_retry = all_results["baseline"][2]
    both_retry = all_results["both"][2]
    base_rp = image_pred_map(base_retry)
    both_rp = image_pred_map(both_retry)
    r_fixed, r_broken = [], []
    for img, t in review_truth.items():
        if img not in base_rp or img not in both_rp:
            continue
        b_ok = base_rp[img] == t
        n_ok = both_rp[img] == t
        if not b_ok and n_ok:
            r_fixed.append(img)
        elif b_ok and not n_ok:
            r_broken.append(img)
    print(f"\n[reviewed-subset, both vs baseline] fixed={len(r_fixed)} {r_fixed}")
    print(f"[reviewed-subset, both vs baseline] broken={len(r_broken)} {r_broken}")


if __name__ == "__main__":
    main()
