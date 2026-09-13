#!/usr/bin/env bash
# 학습 끝난 rec 체크포인트 -> 추론 모델 -> ONNX(+ 딕셔너리 내장). pod 의 /workspace 에서 실행.
set -euo pipefail
cd /workspace/PaddleOCR

CKPT=${1:-./output/rec_korean_v5_ft_v3/best_accuracy}
INFER_DIR=./inference/rec_korean_v5_ft_v3
ONNX_OUT=/workspace/korean_PP-OCRv5_rec_ft_v3.onnx

python3 tools/export_model.py \
    -c configs/rec/PP-OCRv5/multi_language/korean_PP-OCRv5_mobile_rec.yml \
    -o Global.pretrained_model="$CKPT" Global.save_inference_dir="$INFER_DIR" \
       Global.character_dict_path=./ppocr/utils/dict/ppocrv5_korean_dict.txt Global.use_space_char=true

# Paddle 3.x 는 inference.json, 2.x 는 inference.pdmodel 을 씀. 있는 쪽으로 자동 선택
if [ -f "$INFER_DIR/inference.json" ]; then
    MODEL_FILE=inference.json
else
    MODEL_FILE=inference.pdmodel
fi

paddle2onnx \
    --model_dir "$INFER_DIR" \
    --model_filename "$MODEL_FILE" \
    --params_filename inference.pdiparams \
    --save_file "$ONNX_OUT" \
    --opset_version 14 \
    --enable_onnx_checker True

# rapidocr-onnxruntime 은 ONNX 메타데이터 키 "character" (줄바꿈으로 이어붙인 문자 목록)를
# 우선 찾고, 없으면 rec_keys_path 로 넘긴 별도 dict 파일을 쓴다. 여기서는 메타데이터에 박아
# weights/ 교체만으로 끝나게 한다 (dict 파일 별도 배포 불필요).
python3 - <<PY
import onnx

dict_path = "ppocr/utils/dict/ppocrv5_korean_dict.txt"
chars = [l.rstrip("\n") for l in open(dict_path, encoding="utf-8")]
model = onnx.load("$ONNX_OUT")
# 기존에 같은 키가 있으면 지우고 새로 넣는다 (재실행 대비)
del_idx = [i for i, p in enumerate(model.metadata_props) if p.key == "character"]
for i in reversed(del_idx):
    del model.metadata_props[i]
prop = model.metadata_props.add()
prop.key = "character"
prop.value = "\n".join(chars) + "\n"   # 원본 korean v5 onnx 메타데이터와 같은 형식 (끝 줄바꿈 포함)
onnx.save(model, "$ONNX_OUT")
print(f"메타데이터 character 문자 수: {len(chars)}")
PY

echo "완료: $ONNX_OUT"
echo "로컬로 내려받아 weights/korean_PP-OCRv5_rec_ft_v3.onnx 로 복사한 뒤"
echo "python finetune/validate_local.py --rec korean_PP-OCRv5_rec_ft.onnx 로 검증."
echo "(rapidocr 가 메타데이터를 못 읽는 버전이면 대안: RapidOCR(..., rec_keys_path='ppocrv5_korean_dict.txt') 로 dict 파일을 같이 배포)"
