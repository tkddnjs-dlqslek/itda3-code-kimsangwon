"""저장된 OCR 원문에 현재 규칙 엔진 재적용. python tools/reapply_rules.py labels/auto.csv labels/auto_rules.csv"""
import sys, os, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import json
from dateparse import extract_date
from ocr import group_lines
src, out = sys.argv[1], sys.argv[2]
rows = list(csv.DictReader(open(src, encoding="utf-8")))
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["image_id", "year", "month", "day", "final_date", "stage", "texts", "raw"])
    for r in rows:
        if r.get("raw"):                                   # 좌표가 있으면 줄 묶기부터 다시
            items = [(t, [[cx, cy - h / 2], [cx + 100, cy - h / 2], [cx + 100, cy + h / 2], [cx, cy + h / 2]])
                     for t, cy, h, cx in json.loads(r["raw"])]
            texts = group_lines(items)
        else:
            texts = [t for t in r["texts"].split(" | ") if t]
        d = extract_date(texts)
        y, m, dd = d if d else ("NONE",) * 3
        w.writerow([r["image_id"], y, m, dd, f"{y}-{m}-{dd}" if d else "NONE", r["stage"], " | ".join(texts), r.get("raw", "")])
