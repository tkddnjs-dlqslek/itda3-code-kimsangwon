"""검수 엑셀(비고) -> labels/gold.csv. python tools/gold_from_xlsx.py ../검수_전체_3352.xlsx 1000"""
import sys, re, csv
from openpyxl import load_workbook
xlsx, n = sys.argv[1], int(sys.argv[2])
auto = {r["image_id"]: r for r in csv.DictReader(open("labels/auto.csv", encoding="utf-8"))}
ws = load_workbook(xlsx).active
def note_date(s):
    m = re.search(r"(20\d{2})[.\-/년 ]\s?(\d{1,2})[.\-/월 ]\s?(\d{1,2})", s)
    if m: return m[1], f"{int(m[2]):02d}", f"{int(m[3]):02d}"
    m = re.search(r"(20\d{2})년\s?(\d{1,2})월", s)
    if m: return m[1], f"{int(m[2]):02d}", "NONE"
    m = re.search(r"(20\d{2})[.](\d{2})(?![.\d])", s)          # 2026.01 (일 없음)
    if m: return m[1], m[2], "NONE"
    m = re.search(r"(?<!\d)(\d{1,2})월\s?(\d{1,2})일", s)
    if m: return "NONE", f"{int(m[1]):02d}", f"{int(m[2]):02d}"
    return None
rows = []
for r in ws.iter_rows(min_row=2, max_row=n + 1):
    iid, note = str(r[0].value), (r[2].value or "")
    a = auto[iid]
    g = note_date(str(note))
    if g:
        y, mo, d = g
    elif any(k in str(note) for k in ("모르겠", "알아보기 힘든", "확인 필요", "?")) and not g:
        y, mo, d = a["year"], a["month"], a["day"]   # 판단 불가 코멘트: 예측 유지
    else:
        y, mo, d = a["year"], a["month"], a["day"]   # 비고 없음 = 맞음
    rows.append([iid, y, mo, d, str(note).replace("\n", " ")])
with open("labels/gold.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["image_id", "year", "month", "day", "note"]); w.writerows(rows)
print("gold rows:", len(rows), " corrected:", sum(1 for r in rows if r[4] and note_date(r[4])))
