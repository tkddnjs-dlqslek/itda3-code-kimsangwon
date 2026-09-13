#!/usr/bin/env bash
# RunPod PyTorch/CUDA 12.x 템플릿 pod 에서 1회 실행.
# 사용법: bash setup.sh  (workspace 기준 /workspace 에 PaddleOCR 클론)
set -euo pipefail
cd /workspace

# ----- PaddlePaddle GPU (CUDA 12.6 휠) -----------------------------------
# 공식 인덱스. pod 의 CUDA 버전이 다르면 https://www.paddlepaddle.org.cn/ 에서 맞는 cuXXX 인덱스로 교체
CUDA_IDX=${CUDA_IDX:-cu126}   # nvidia-smi 의 CUDA Version 이 12.6 미만이면: CUDA_IDX=cu118 bash setup.sh
pip install paddlepaddle-gpu==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/${CUDA_IDX}/

# ----- PaddleOCR 소스 (config/tools 사용, pip 패키지가 아니라 레포 필요) -----
# v3.4.0 = 2026-01-29 릴리스, PP-OCRv5 config 확인은 main 브랜치에서만 했음.
# clone 뒤 아래 확인 명령으로 태그에도 파일이 있는지 재확인할 것 (미검증 항목, README 참고)
git clone --branch v3.4.0 --depth 1 https://github.com/PaddlePaddle/PaddleOCR.git
cd PaddleOCR
ls configs/rec/PP-OCRv5/multi_language/korean_PP-OCRv5_mobile_rec.yml configs/det/PP-OCRv5/PP-OCRv5_mobile_det.yml \
   ppocr/utils/dict/ppocrv5_korean_dict.txt   # v3.4.0 태그에 모두 존재 (09-11 확인)
pip install -r requirements.txt
pip install paddle2onnx onnxruntime rapidocr-onnxruntime==1.3.24

cd /workspace

# ----- 사전학습 가중치 (파인튜닝 시작점) -----------------------------------
# URL 은 PaddleOCR 공식 문서(PP-OCRv5_multi_languages.en.md, PP-OCRv5.en.md) 및
# HuggingFace PaddlePaddle/korean_PP-OCRv5_mobile_rec 리포에서 확인. det 쪽 URL 은
# rec 과 동일한 official_pretrained_model 경로 패턴으로 유추 (직접 200 확인 권장, README 참고)
mkdir -p pretrained
REC_URL="https://paddle-model-ecology.bj.bcebos.com/paddlex/official_pretrained_model/korean_PP-OCRv5_mobile_rec_pretrained.pdparams"
DET_URL="https://paddle-model-ecology.bj.bcebos.com/paddlex/official_pretrained_model/PP-OCRv5_mobile_det_pretrained.pdparams"
curl -L --fail -o pretrained/korean_PP-OCRv5_mobile_rec_pretrained.pdparams "$REC_URL"
curl -L --fail -o pretrained/PP-OCRv5_mobile_det_pretrained.pdparams "$DET_URL"   # phase 2(det)용, rec만 할 거면 생략 가능

echo "완료. 다음: finetune_data/ 를 이 pod 의 /workspace/finetune_data 로 올리고 (upload_data.md 참고),"
echo "runpod/rec_korean_v5_finetune.yml 을 PaddleOCR/ 밖(../runpod/)에 두고"
echo "python log_usage.py start --gpu <타입> --price <시간당 USD> --purpose 'rec finetune' 로 사용량 기록 시작 후"
echo "bash train_rec.sh 실행."
