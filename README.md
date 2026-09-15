# ITDA 3rd 학술제: 소비기한 OCR 제출

상품 뒷면 이미지에서 소비기한(유통기한) 날짜를 뽑아 `image_id,year,month,day,final_date` 스키마의
`submission.csv` 로 저장하는 오프라인 파이프라인입니다.

## 1. 설치

```bash
pip install -r requirements.txt
```

CPU 전용(GPU, torch 없음), 인터넷 차단 환경(4 vCPU)에서 그대로 동작하도록 맞춰져 있습니다.

`requirements.txt` 의 `opencv-python @ ...whl` 한 줄은 파일이 없는 빈 휠입니다. `rapidocr-onnxruntime` 이
일반판 `opencv-python` 을 요구하는데, 그 `cv2` 는 `libGL.so.1` 이 필요해 서버용 Ubuntu 22.04에서 import가
실패합니다. 빈 휠로 요구만 채우고 실제 `cv2` 는 `opencv-python-headless` 가 제공합니다
(순정 `ubuntu:22.04` 컨테이너에서 확인).

## 2. 가중치 다운로드 (채점 전 1회)

```bash
bash download_weights.sh
```

`weights/` 에 아래 4개 rec/det ONNX 가중치를 받아옵니다. det 기본 모델은 `rapidocr-onnxruntime`
패키지에 동봉되어 있어 별도 다운로드가 필요 없습니다.

- `ch_PP-OCRv5_det_mobile.onnx` (재시도용 v5 검출기, 도트 프린팅에 강함)
- `korean_PP-OCRv5_rec_mobile.onnx` (기본 인식기)
- `ch_PP-OCRv3_rec_infer.onnx` (숫자 재확인용 인식기)
- `korean_PP-OCRv5_rec_ft_v2.onnx` (재시도 단계 전용 파인튜닝 인식기, 이 저장소 Release v1.0.0에서 받음)

가중치는 Git에 커밋하지 않습니다(`.gitignore`). 노트북 실행 도중에는 다운로드를 시도하지 않고,
`download_weights.sh` 로 미리 받아둔 로컬 파일만 `download_enabled=False` 상당으로 오프라인 로드합니다.

## 3. 노트북 실행 (채점 재현성 검증)

채점 환경 (09-14 운영진 공지): Ubuntu 22.04 LTS (x86_64), Python 3.10, CPU 4코어, RAM 8GB, GPU 없음,
인터넷 차단, 팀별 독립 가상환경(venv)에 `requirements.txt` 설치 후 실행.

```bash
export ITDA_INPUT_DIR=./val_images
export ITDA_OUTPUT_PATH=./submission.csv
jupyter nbconvert --to notebook --execute predict.ipynb \
    --ExecutePreprocessor.timeout=2400 \
    --output /tmp/executed.ipynb
```

레포 루트에서 실행하는 것을 전제로 합니다(`predict.ipynb` 가 `src/` 를 `sys.path` 에 추가).

### 제출 전 자가 점검 (운영진 안내 순서)

1. 저장소를 새 폴더에 clone
2. 새 가상환경 생성 후 `pip install -r requirements.txt`
3. `bash download_weights.sh` 실행
4. 인터넷 연결 해제
5. 위 명령어 실행 후 `submission.csv` 생성 확인

- 노트북은 가중치를 내려받지 않고 `weights/` 의 로컬 파일만 읽습니다.
- 로컬 경로 하드코딩과 GPU 코드(cuda)는 없습니다. 입력과 출력 경로는 환경변수로만 받습니다.
`input()` 등 대화형 코드, 로컬 절대경로 하드코딩은 없습니다.

## 4. 아키텍처 요약

- **검출(det)**: `rapidocr-onnxruntime` 번들 det로 우선 검출하고, 실패 시 도트 프린팅에
  강한 `ch_PP-OCRv5_det_mobile.onnx` 로 재검출합니다 (`src/ocr.py::_det`).
- **단계 재시도**: 싼 단계부터 순서대로 시도하고 날짜 후보가 잡히는 즉시 멈춥니다
  (`s1` 큰 글자 박스 → `s2` 작은 박스 포함 → `det5` v5 재검출 → 90/180/270도 회전 →
  CLAHE 대비 강화 → 원본 고해상도 → 2배 확대 → 5x5/3x3 침식(도트 프린팅용, 필요하면 seam-carving으로
  두 줄 분리)). `src/ocr.py::read_raw`.
- **인식(rec) 하이브리드**: 한국어 v5 인식기로 전부 읽고, 숫자 3자리 이상인데 날짜가 안 풀리는
  조각만 중국어 v3 인식기로 다시 읽어 완전한 날짜가 나오면 교체합니다 (`src/ocr.py::hybrid_rec`).
- **규칙 엔진**: 순수 파이썬으로 키워드 오탈자 사전 교정, 정규식 패턴 매칭, 달력 검증, 점수화를
  거쳐 소비기한 하나를 고릅니다. 소비기한/유통기한 동시 표기, 부터~까지 범위, 포장일자 제외,
  부분 날짜(NONE 혼합) 판정을 포함합니다 (`src/dateparse.py`).
- **시간 예산**: `pipeline.set_budget(total_seconds, n_images)` 로 전체 예산을 걸어두면,
  이미지마다 남은 시간/남은 장 수를 계산해 여유가 없어지면 회전·재시도 단계를 건너뛰고(`cheap`),
  더 빠듯하면 가장 싼 `s1` 단계만 씁니다. 예산을 걸지 않으면 기존 동작 그대로입니다
  (`src/pipeline.py::set_budget`, `_decide_stage`). `predict.ipynb` 는 2400초 제한에
  120초 여유를 둔 2280초로 설정합니다.

## 5. 오프라인 제약

채점 서버는 인터넷이 완전히 차단됩니다. 모든 가중치는 `download_weights.sh` 로 노트북 실행
전에 로컬에 존재해야 하며, `predict.ipynb` 안에서는 어떤 다운로드도 하지 않습니다.

## 6. 라벨과 평가 스크립트

- 정답 라벨: `labels/gold.csv`, 라벨링 기준: `labels/LABELING_RULES.md`
- 평가: `python tools/evaluate.py labels/gold.csv <예측 csv>` (정확도, 오류 유형별 집계,
  `labels/errors.csv` 출력)
- 그 외 벤치마크/실험 스크립트는 `tools/`, 파인튜닝 관련 자료는 `finetune/` 에 있습니다
  (둘 다 채점 대상 아님).

## 6-1. 직접 라벨링한 데이터 (가산점 증빙)

- 위치: `custom_data/`. 라벨은 `custom_data/labels/` 의 CSV 와 XLSX, 라벨과 짝지어진 글자 조각 이미지는
  `custom_data/crops/` 에 있습니다.
- 핵심 파일은 `custom_data/labels/gold_1000.csv` (골드셋 1,000장 정답)와
  `custom_data/labels/v3_crop_labels_298.csv` (글자 조각 298개 정답)이며, 구축 기준은 요약서 PDF 2쪽에
  적었습니다.

## 7. 테스트

```bash
python -m pytest tests -q
```

## 로컬에서 노트북 실행할 때 주의

`predict.ipynb` 의 커널스펙은 채점 환경 기본값인 `python3` 로 둔다. 로컬에 다른 `python3` 커널이 있으면
`ModuleNotFoundError: No module named 'cv2'` 가 날 수 있으므로, 이 저장소 환경을 커널로 등록해 지정 실행한다.

```bash
python -m ipykernel install --user --name itda --display-name "Python (itda)"
ITDA_INPUT_DIR=./val_images ITDA_OUTPUT_PATH=./submission.csv   python -m jupyter nbconvert --to notebook --execute predict.ipynb   --ExecutePreprocessor.timeout=2400 --ExecutePreprocessor.kernel_name=itda --output /tmp/executed.ipynb
```

채점 서버는 requirements.txt 를 설치한 환경의 기본 커널로 돌리므로 kernel_name 을 지정하지 않는다.
