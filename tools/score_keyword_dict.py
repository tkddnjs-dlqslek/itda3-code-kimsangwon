# -*- coding: utf-8 -*-
"""저장된 OCR 원문(raw)에서 줄 묶기를 다시 만들어 (a) 저장된 texts 컬럼과 일치율을 검증하고,
(b) 사전 교정 OFF(OLD)/ON(NEW) 규칙으로 채점, gold.csv 와 비교해 exact/field 정확도와
바뀐 이미지, 교정된 줄 수를 report. OCR 재실행 없음.

python tools/score_keyword_dict.py
"""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import dateparse  # noqa: E402
import ocr  # noqa: E402

REPO = os.path.join(os.path.dirname(__file__), "..")
GOLD = os.path.join(REPO, "labels", "gold.csv")
MODES = {
    "hybrid": os.path.join(REPO, "labels", "auto_gold_v5.csv"),
    "ko": os.path.join(REPO, "labels", "auto_gold_v5_ko.csv"),
    "merge": os.path.join(REPO, "labels", "auto_gold_v5_merge.csv"),
}
OUT = os.path.join(REPO, "labels", "keyword_dict_scores.txt")


def _rebuild(raw_json: str):
    """raw 컬럼 [[text, cy, h, cx], ...] -> group_lines_geo 로 재구성한 (texts, geo).
    reapply_rules.py 와 같은 방식으로 cy/h/cx 에서 합성 박스를 만든다 (너비는 임의 100)."""
    rows = json.loads(raw_json) if raw_json else []
    items = [(t, [[cx, cy - h / 2], [cx + 100, cy - h / 2], [cx + 100, cy + h / 2], [cx, cy + h / 2]])
             for t, cy, h, cx in rows]
    lines_geo = ocr.group_lines_geo(items)
    texts = [t for t, _, _ in lines_geo]
    geo = [(cy, h) for _, cy, h in lines_geo]
    return texts, geo


def _score(g: pd.DataFrame, suffix: str) -> dict:
    """g 는 gold + pred 를 이미 합친 프레임. year_g/month_g/day_g 와 year_{suffix} 등을 비교."""
    year_ok = g.year_g == g["year_" + suffix]
    month_ok = g.month_g == g["month_" + suffix]
    day_ok = g.day_g == g["day_" + suffix]
    exact = year_ok & month_ok & day_ok
    field = (year_ok.astype(int) + month_ok.astype(int) + day_ok.astype(int)) / 3
    return {"exact": exact.mean(), "field": field.mean(),
            "year": year_ok.mean(), "month": month_ok.mean(), "day": day_ok.mean(),
            "exact_mask": exact}


def main():
    gold = pd.read_csv(GOLD, dtype=str).fillna("NONE")
    report = []
    match_total, match_ok = 0, 0

    for mode, path in MODES.items():
        df = pd.read_csv(path, dtype=str).fillna("")
        rebuilt_texts, rebuilt_geo, n_match = [], [], 0
        for _, r in df.iterrows():
            texts, geo = _rebuild(r["raw"])
            rebuilt_texts.append(texts)
            rebuilt_geo.append(geo)
            stored = [t for t in r["texts"].split(" | ") if t] if r["texts"] else []
            if texts == stored:
                n_match += 1
        rate = n_match / len(df) if len(df) else 1.0
        match_total += len(df); match_ok += n_match
        report.append(f"[{mode}] 줄 재구성 일치율: {n_match}/{len(df)} = {rate:.4f}")

        rows_old, rows_new = [], []
        for (_, r), texts, geo in zip(df.iterrows(), rebuilt_texts, rebuilt_geo):
            dateparse.USE_KEYWORD_DICT = False
            d_old = dateparse.extract_date(texts, geo)
            y, mo, dd = d_old if d_old else ("NONE",) * 3
            rows_old.append({"image_id": r["image_id"], "year": y, "month": mo, "day": dd})

            dateparse.USE_KEYWORD_DICT = True
            d_new = dateparse.extract_date(texts, geo)
            y2, mo2, dd2 = d_new if d_new else ("NONE",) * 3
            rows_new.append({"image_id": r["image_id"], "year": y2, "month": mo2, "day": dd2})
        dateparse.USE_KEYWORD_DICT = True

        old_df = pd.DataFrame(rows_old).rename(columns={"year": "year_old", "month": "month_old", "day": "day_old"})
        new_df = pd.DataFrame(rows_new).rename(columns={"year": "year_new", "month": "month_new", "day": "day_new"})

        # OLD 가 csv 에 저장된 final_date(원래 사전 없이 뽑은 값)를 재현하는지
        stored = df[["image_id", "year", "month", "day"]].fillna("NONE").rename(
            columns={"year": "year_s", "month": "month_s", "day": "day_s"})
        old_join = stored.merge(old_df, on="image_id")
        repro = ((old_join.year_s == old_join.year_old) & (old_join.month_s == old_join.month_old)
                 & (old_join.day_s == old_join.day_old)).mean()
        report.append(f"[{mode}] OLD 가 저장된 final_date 재현율: {repro:.4f}")

        merged = gold.rename(columns={"year": "year_g", "month": "month_g", "day": "day_g"})
        merged = merged.merge(old_df, on="image_id", how="left").merge(new_df, on="image_id", how="left").fillna("NONE")
        sc_old = _score(merged, "old")
        sc_new = _score(merged, "new")
        report.append(f"[{mode}] OLD exact={sc_old['exact']:.4f} field={sc_old['field']:.4f} "
                       f"(year {sc_old['year']:.4f} month {sc_old['month']:.4f} day {sc_old['day']:.4f})")
        report.append(f"[{mode}] NEW exact={sc_new['exact']:.4f} field={sc_new['field']:.4f} "
                       f"(year {sc_new['year']:.4f} month {sc_new['month']:.4f} day {sc_new['day']:.4f})")

        old_exact = sc_old["exact_mask"]
        new_exact = sc_new["exact_mask"]
        improved, regressed = [], []
        for i, r in merged.iterrows():
            if not old_exact[i] and new_exact[i]:
                improved.append((r.image_id, f"{r.year_g}-{r.month_g}-{r.day_g}",
                                  f"{r.year_old}-{r.month_old}-{r.day_old}",
                                  f"{r.year_new}-{r.month_new}-{r.day_new}"))
            elif old_exact[i] and not new_exact[i]:
                regressed.append((r.image_id, f"{r.year_g}-{r.month_g}-{r.day_g}",
                                   f"{r.year_old}-{r.month_old}-{r.day_old}",
                                   f"{r.year_new}-{r.month_new}-{r.day_new}"))
        report.append(f"[{mode}] 정답으로 바뀜 ({len(improved)}건): " +
                      ", ".join(f"{i}(gold={g},전={b},후={a})" for i, g, b, a in improved))
        report.append(f"[{mode}] 오답으로 바뀜 ({len(regressed)}건): " +
                      ", ".join(f"{i}(gold={g},전={b},후={a})" for i, g, b, a in regressed))

        n_lines_corrected = 0
        dateparse.USE_KEYWORD_DICT = True
        for texts, geo in zip(rebuilt_texts, rebuilt_geo):
            _, whys = dateparse._correct_lines(texts, geo)
            n_lines_corrected += sum(1 for w in whys if w)
        report.append(f"[{mode}] 사전 교정이 적용된 줄 수: {n_lines_corrected}")
        report.append("")

    report.insert(0, f"전체 줄 재구성 일치율: {match_ok}/{match_total} = {match_ok/match_total:.4f}\n")
    text = "\n".join(report)
    print(text)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text + "\n")


if __name__ == "__main__":
    main()
