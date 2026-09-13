"""저장된 texts 컬럼(줄 묶기 이미 끝난 상태)에 규칙 엔진만 재적용. OCR/줄 묶기 재실행 없음.
python tools/reapply_rules_from_texts.py labels/auto_gold_v5.csv labels/auto_gold_v5_rangefix.csv
"""
import sys, os, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from dateparse import extract_date

src, out = sys.argv[1], sys.argv[2]
rows = list(csv.DictReader(open(src, encoding="utf-8")))
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["image_id", "year", "month", "day", "final_date", "stage", "texts", "raw"])
    for r in rows:
        texts = [t for t in r["texts"].split(" | ") if t]
        d = extract_date(texts)
        y, m, dd = d if d else ("NONE",) * 3
        w.writerow([r["image_id"], y, m, dd, f"{y}-{m}-{dd}" if d else "NONE", r["stage"], " | ".join(texts), r.get("raw", "")])
