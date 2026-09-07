"""python tools/evaluate.py labels/gold.csv labels/auto.csv  -> 정확도, 오류 유형, labels/errors.csv"""
import sys, csv
import pandas as pd
gold = pd.read_csv(sys.argv[1], dtype=str).fillna("")
pred = pd.read_csv(sys.argv[2], dtype=str).fillna("")
m = gold.merge(pred, on="image_id", how="left", suffixes=("_g", "_p"))
for c in ("year", "month", "day"):
    m[c + "_ok"] = m[c + "_g"] == m[c + "_p"]
m["exact"] = m.year_ok & m.month_ok & m.day_ok
m["field_score"] = (m.year_ok.astype(int) + m.month_ok.astype(int) + m.day_ok.astype(int)) / 3
def kind(r):
    if r.exact: return "ok"
    gnone = (r.year_g, r.month_g, r.day_g) == ("NONE",) * 3
    pnone = (r.year_p, r.month_p, r.day_p) == ("NONE",) * 3
    if gnone: return "false_positive"
    if pnone: return "miss"
    if r.month_ok and r.day_ok: return "wrong_year"
    if r.year_ok and r.month_ok: return "wrong_day"
    if r.year_ok: return "wrong_md"
    if r.year_p == "NONE" and r.year_g != "NONE": return "partial_wrong"
    return "wrong_all"
m["kind"] = m.apply(kind, axis=1)
n = len(m)
print(f"n={n}  exact={m.exact.mean():.3f}  field_score={m.field_score.mean():.3f}  "
      f"(year {m.year_ok.mean():.3f} month {m.month_ok.mean():.3f} day {m.day_ok.mean():.3f})")
print(m.kind.value_counts().to_string())
if "stage" in m:
    print("\nexact by stage:"); print(m.groupby("stage").exact.agg(["count", "mean"]).round(3).to_string())
cols = ["image_id", "kind", "year_g", "month_g", "day_g", "year_p", "month_p", "day_p", "stage", "note", "texts"]
m[m.kind != "ok"][[c for c in cols if c in m]].to_csv("labels/errors.csv", index=False)
