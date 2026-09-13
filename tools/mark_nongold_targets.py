"""363장(골드 밖, v4 첫 단계 실패) v5 실행이 끝나면 검수_전체_3352.xlsx 에 대상, v5 결과 열을 추가한다.
실행 완료를 스스로 기다리고, 최신 규칙을 texts 에 다시 적용해 v5 결과를 쓴다. 기존 열(image_id, 모델 결과, 비고)은 건드리지 않음."""
import os, sys, time, shutil, subprocess
ROOT = r"C:/Users/user/Desktop/ITDA 공모전"
REPO = ROOT + "/repo"
sys.path.insert(0, REPO + "/src")
import pandas as pd, openpyxl
import dateparse

CSV = REPO + "/labels/auto_nongold_retry_v5.csv"
IDS = [l.strip() for l in open(REPO + "/labels/nongold_retry_ids.txt", encoding="utf-8") if l.strip()]
XLSX = ROOT + "/검수_전체_3352.xlsx"
LOG = REPO + "/labels/mark_nongold_targets.log"

def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S ") + msg + "\n")

def autolabel_running():
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | ForEach-Object { $_.CommandLine }"],
        capture_output=True, text=True).stdout
    return "auto_nongold_retry_v5.csv" in out

while True:
    n = len(pd.read_csv(CSV, dtype=str)) if os.path.exists(CSV) else 0
    if n >= len(IDS) and not autolabel_running():
        break
    time.sleep(60)
log(f"run finished rows={n}")

p = pd.read_csv(CSV, dtype=str, keep_default_na=False)
res = {}
for i, t in zip(p.image_id, p.texts):
    f = dateparse.extract_date(t.split(" | ") if t else [])
    res[i] = "-".join(f) if f else "NONE"
changed = sum(res[i] != fd for i, fd in zip(p.image_id, p.final_date))
log(f"rules reapplied, differs from stored final_date: {changed}")

target = XLSX
lock = os.path.join(ROOT, "~$" + os.path.basename(XLSX))
if os.path.exists(lock):
    target = ROOT + "/검수_전체_3352_v5대상.xlsx"
    shutil.copy(XLSX, target)
    log("excel is open (lock file). writing a copy instead: " + target)
else:
    shutil.copy(XLSX, ROOT + "/det_check/backup/검수_전체_3352_before_v5_0912.xlsx")

wb = openpyxl.load_workbook(target)
ws = wb["검수"]
hdr = [c.value for c in ws[1]]
assert hdr[:3] == ["image_id", "모델 결과", "비고"], hdr
if "대상" not in hdr:
    ws.cell(1, 4).value = "대상"
    ws.cell(1, 5).value = "v5 결과"
tset = set(IDS); marked = 0
for r in range(2, ws.max_row + 1):
    iid = str(ws.cell(r, 1).value)
    if iid in tset:
        ws.cell(r, 4).value = "O"
        ws.cell(r, 5).value = res.get(iid, "실행 누락")
        marked += 1
ws.auto_filter.ref = f"A1:E{ws.max_row}"
wb.save(target)
log(f"saved {target} marked={marked}")
