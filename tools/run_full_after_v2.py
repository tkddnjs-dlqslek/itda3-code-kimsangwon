"""v2 채점 3종이 끝나면 전체 3,352장을 현재 파이프라인(파인튜닝 미적용, 골드 892)으로 실행한다.
오류 없이 끝나는지 확인하고 전량 예측을 남기는 용도."""
import os, sys, time, subprocess
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
WAIT = ["labels/auto_gold_v5_ft_v2.csv", "labels/auto_gold_v5_ftdigit_v2.csv", "labels/auto_gold_v5_ftmerge_v2.csv"]
def rows(p):
    return sum(1 for _ in open(p, encoding="utf-8")) - 1 if os.path.exists(p) else 0
while any(rows(p) < 1000 for p in WAIT):
    print("대기: " + ", ".join(f"{os.path.basename(p)} {rows(p)}/1000" for p in WAIT), flush=True)
    time.sleep(120)
print("v2 채점 완료. 전체 실행 시작", flush=True)
subprocess.run([sys.executable, "tools/autolabel.py", "../images", "labels/auto_full_v6.csv"], check=False)
print("DONE", flush=True)
