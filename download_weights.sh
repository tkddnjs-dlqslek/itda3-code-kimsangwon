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
# 파인튜닝 rec 를 채택하는 경우에만 사용한다 (가중치는 커밋 금지, Release Assets 로 배포).
# 채택 확정 후 아래 주석을 풀고 URL 을 실제 Release 주소로 바꾼다.
# dl korean_PP-OCRv5_rec_ft_v2.onnx "https://github.com/tkddnjs-dlqslek/itda3-code-kimsangwon/releases/download/v1.0.0/korean_PP-OCRv5_rec_ft_v2.onnx"

ls -la weights
