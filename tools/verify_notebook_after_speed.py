"""속도 측정이 끝나면 predict.ipynb 를 실제로 Run All 실행해 제출 형식을 검증한다."""
import os, sys, time, glob, shutil, tempfile, subprocess, csv, random
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
LOG = "labels/bench_speed_mixed.log"
while not (os.path.exists(LOG) and "RESULT" in open(LOG, encoding="utf-8", errors="ignore").read()):
    time.sleep(60)
time.sleep(20)
imgs = sorted(glob.glob(os.path.join("..", "images", "*.jpg")))
random.Random(7).shuffle(imgs)
tmp = tempfile.mkdtemp(prefix="nbcheck_")
for p in imgs[:30]:
    shutil.copy2(p, tmp)
out_csv = os.path.join(tmp, "submission.csv")
env = dict(os.environ, ITDA_INPUT_DIR=tmp, ITDA_OUTPUT_PATH=out_csv, PYTHONIOENCODING="utf-8")
t0 = time.time()
r = subprocess.run([sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute",
                    "predict.ipynb", "--ExecutePreprocessor.timeout=900",
                    "--output", os.path.join(tmp, "executed.ipynb")],
                   env=env, capture_output=True, text=True)
print("nbconvert 종료코드", r.returncode, f"{time.time()-t0:.1f}초", flush=True)
if r.returncode != 0:
    print(r.stderr[-1500:], flush=True)
rows = list(csv.DictReader(open(out_csv, encoding="utf-8"))) if os.path.exists(out_csv) else []
print("행 수", len(rows), "| 열", list(rows[0].keys()) if rows else None, flush=True)
bad = []
for x in rows:
    y, m, d, f = x["year"], x["month"], x["day"], x["final_date"]
    if m != "NONE" and len(m) != 2: bad.append(("month 2자리 아님", x))
    if d != "NONE" and len(d) != 2: bad.append(("day 2자리 아님", x))
    if y != "NONE" and len(y) != 4: bad.append(("year 4자리 아님", x))
    want = "NONE" if (y, m, d) == ("NONE", "NONE", "NONE") else f"{y}-{m}-{d}"
    if f != want: bad.append(("final_date 규칙 위반", x))
print("형식 위반", len(bad), bad[:3], flush=True)
shutil.rmtree(tmp, ignore_errors=True)
print("DONE", flush=True)
