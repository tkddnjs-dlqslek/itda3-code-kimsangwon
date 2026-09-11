#!/usr/bin/env bash
# det(2단계) 파인튜닝. box 라벨(PPOCRLabel/LabelMe로 수동)이 끝난 뒤 실행.
set -euo pipefail
cd /workspace/PaddleOCR

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

cfg = yaml.safe_load(open("../runpod/det_v5_finetune.yml", encoding="utf-8"))
print(" ".join(flat(cfg)))
PY
)
echo "오버라이드: $OVERRIDES"

mkdir -p ../logs
nohup python3 tools/train.py \
    -c configs/det/PP-OCRv5/PP-OCRv5_mobile_det.yml \
    -o $OVERRIDES \
    > ../logs/train_det.log 2>&1 &
echo "학습 시작 (PID $!). 진행: tail -f /workspace/logs/train_det.log"
echo "export 는 export_rec.sh 를 참고해 configs/det 경로와 산출 파일명만 바꿔서 사용"
