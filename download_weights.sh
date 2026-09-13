#!/usr/bin/env bash
# 채점 전 운영진이 1회 실행. det/cls 모델은 rapidocr-onnxruntime pip 패키지에 동봉되어 있고,
# 아래 rec 모델 2개만 외부에서 받는다. (.onnx 는 .gitignore 로 커밋 금지)
set -e
cd "$(dirname "$0")"
mkdir -p weights
dl() { [ -s "weights/$1" ] && echo "skip $1" || curl -L --fail -o "weights/$1" "$2"; }
dl ch_PP-OCRv3_rec_infer.onnx "https://huggingface.co/SWHL/RapidOCR/resolve/main/PP-OCRv3/ch_PP-OCRv3_rec_infer.onnx"
dl ch_PP-OCRv5_det_mobile.onnx "https://modelscope.cn/api/v1/models/RapidAI/RapidOCR/repo?Revision=master&FilePath=onnx/PP-OCRv5/det/ch_PP-OCRv5_det_mobile.onnx"
dl korean_PP-OCRv5_rec_mobile.onnx "https://modelscope.cn/api/v1/models/RapidAI/RapidOCR/repo?Revision=master&FilePath=onnx/PP-OCRv5/rec/korean_PP-OCRv5_rec_mobile.onnx"
# 재시도 단계(det5 이후)에서 쓰는 파인튜닝 rec. src/ocr.py 의 RETRY_REC 가 이 파일을 찾는다.
# 없으면 경고를 찍고 기본 rec 로 폴백하므로 정확도가 떨어진다 (골드 1,000장 exact 901 -> 884).
dl korean_PP-OCRv5_rec_ft_v2.onnx "https://github.com/tkddnjs-dlqslek/itda3-code-kimsangwon/releases/download/v1.0.0/korean_PP-OCRv5_rec_ft_v2.onnx"

ls -la weights
