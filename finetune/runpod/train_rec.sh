#!/usr/bin/env bash
# rec 파인튜닝 실행. RunPod pod 안에서, setup.sh 실행 뒤에 돌린다.
# 사용법 (pod 의 /workspace 에서): bash ../runpod/train_rec.sh
set -euo pipefail
cd /workspace/PaddleOCR

# rec_korean_v5_finetune.yml(오버라이드만 담은 파일)을 -o 인자 문자열로 펼친다.
# PaddleOCR 은 `tools/train.py -c <base.yml> -o key=value key2=value2 ...` 로
# 커맨드라인 오버라이드를 지원한다 (config 파일을 다시 옮겨 쓰지 않아도 됨).
OVERRIDES=$(python3 - <<'PY'
import yaml

def flat(d, prefix=""):
    out = []
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out += flat(v, key + ".")
        elif isinstance(v, list):
            out.append(f"{key}=[{','.join(str(x) for x in v)}]")
        else:
            out.append(f"{key}={v}")
    return out

cfg = yaml.safe_load(open("../runpod/rec_korean_v5_finetune.yml", encoding="utf-8"))
print(" ".join(flat(cfg)))
PY
)
echo "오버라이드: $OVERRIDES"

mkdir -p ../logs
nohup python3 tools/train.py \
    -c configs/rec/PP-OCRv5/PP-OCRv5_mobile_rec.yml \
    -o $OVERRIDES \
    > ../logs/train_rec.log 2>&1 &
echo "학습 시작 (PID $!). 진행: tail -f /workspace/logs/train_rec.log"
echo "끝나면: bash export_rec.sh"
