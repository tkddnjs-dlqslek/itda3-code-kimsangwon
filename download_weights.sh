#!/usr/bin/env bash
# 채점 전 운영진이 1회 실행. det/cls 모델은 rapidocr-onnxruntime pip 패키지에 동봉되어 있고,
# 아래 rec 모델 2개만 외부에서 받는다. (.onnx 는 .gitignore 로 커밋 금지)
set -e
cd "$(dirname "$0")"
mkdir -p weights
dl() { [ -s "weights/$1" ] && echo "skip $1" || curl -L --fail -o "weights/$1" "$2"; }
dl ch_PP-OCRv3_rec_infer.onnx "https://huggingface.co/SWHL/RapidOCR/resolve/main/PP-OCRv3/ch_PP-OCRv3_rec_infer.onnx"
dl korean_PP-OCRv5_rec_mobile.onnx "https://modelscope.cn/api/v1/models/RapidAI/RapidOCR/repo?Revision=master&FilePath=onnx/PP-OCRv5/rec/korean_PP-OCRv5_rec_mobile.onnx"
ls -la weights
