"""노트북 검증이 끝나면 채택 구성(RETRY_REC)으로 전체 3,352장을 다시 실행한다. 제출용 최종 산출물."""
import os, sys, time, subprocess
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
LOG = "labels/verify_notebook.log"
while not (os.path.exists(LOG) and "DONE" in open(LOG, encoding="utf-8", errors="ignore").read()):
    time.sleep(60)
time.sleep(20)
print("노트북 검증 완료. 채택 구성으로 전체 실행 시작", flush=True)
subprocess.run([sys.executable, "tools/autolabel.py", "../images", "labels/auto_full_v7_adopted.csv"], check=False)
print("DONE", flush=True)
