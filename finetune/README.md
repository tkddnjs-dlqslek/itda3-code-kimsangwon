# OCR 파인튜닝 준비 (rec 우선, det 2단계)

이 폴더는 학습을 대신 실행하지 않는다. 데이터 수확, RunPod 스크립트, ONNX 변환,
로컬 검증까지 "준비"만 담당한다. 실제 학습(RunPod 접속, `bash train_rec.sh` 실행)은
사용자가 직접 한다.

## 1. 목표

- 골드 1,000장 기준 rec 오독(6↔5, 2↔0 등)과 det 미검출(도트 프린팅, 금속면, 저대비)을
  줄이기 위해 korean_PP-OCRv5_rec_mobile 을 먼저 파인튜닝하고, 여유가 되면
  ch_PP-OCRv5_det_mobile 도 파인튜닝한다.
- 최종 산출물은 rapidocr-onnxruntime 1.3.24 가 그대로 읽는 ONNX 파일. `weights/` 안의
  기존 파일을 교체하는 것만으로 `src/ocr.py` 수정 없이 반영되게 만든다.

## 2. 전체 흐름

```
[로컬] prep_rec_data.py           골드셋에서 rec 학습 데이터 자동 수확 + hard 크롭 추출
   -> (수동) hard_labels.xlsx 라벨링
[로컬] build_labels.py            수동 라벨을 train_label.txt 에 합침
   -> finetune/data 를 RunPod pod 로 업로드
[RunPod] setup.sh                 PaddlePaddle-GPU, PaddleOCR, paddle2onnx 설치 + 사전학습 가중치 다운로드
[RunPod] log_usage.py start       사용량 기록 시작
[RunPod] train_rec.sh             rec 파인튜닝 (30 epoch)
[RunPod] export_rec.sh            체크포인트 -> 추론모델 -> ONNX(+ 딕셔너리 내장)
[RunPod] log_usage.py end         사용량 기록 종료
   -> ONNX 파일을 로컬로 다운로드
[로컬] weights/ 에 복사
[로컬] validate_local.py          골드셋 재평가, 기존 대비 diff 확인
   -> 개선되면 weights/ 교체 확정, requirements.txt/제출 준비
(선택, 2단계) det 도 같은 흐름: prep_det_data.py -> PPOCRLabel 수동 라벨링 ->
             train_det.sh -> export (export_rec.sh 참고해 경로만 바꿔 사용)
```

## 3. 사전 준비물

- 로컬: `C:/anaconda/envs/itda/python.exe` (rapidocr-onnxruntime, opencv, pandas, openpyxl 이미 설치됨)
- RunPod 계정, 결제 수단 등록, API 키 (`RUNPOD_API_KEY`, 콘솔 Settings > API Keys)
- RunPod pod: PyTorch/CUDA 12.x 템플릿, GPU 1장 (RTX 4090 이나 3090 정도로 충분, A100 불필요)
- 인터넷 (로컬 준비 단계는 오프라인, RunPod 단계만 인터넷 필요 — 채점 서버는 계속 오프라인이라 무관)

## 4. 단계별 명령

### 4.1 로컬: rec 학습 데이터 수확

```bash
cd "C:/Users/user/Desktop/ITDA 공모전/repo"
PYTHONIOENCODING=utf-8 "C:/anaconda/envs/itda/python.exe" finetune/prep_rec_data.py --limit 30 --out finetune/data_test
# 문제 없으면 전체 실행 (약 1~2시간, 배경 실행 권장)
PYTHONIOENCODING=utf-8 "C:/anaconda/envs/itda/python.exe" finetune/prep_rec_data.py --out finetune/data
```

끝나면 콘솔에 auto 양성 수, hard 크롭 수, hard 이미지 수가 찍힌다.

### 4.2 로컬: hard 크롭 수동 라벨링 (사용자 작업)

`finetune/data/rec/hard_labels.xlsx` 를 열어 미리보기를 보면서 `label` 칸에 실제
표기를 정확히 입력한다 (예: `2026.06.28`). 날짜 크롭이 아니면 `skip` 칸에 `x`.
비워 둔 행은 다음 단계에서 자동으로 건너뛴다.

### 4.3 로컬: 수동 라벨 합치기

```bash
PYTHONIOENCODING=utf-8 "C:/anaconda/envs/itda/python.exe" finetune/build_labels.py --data finetune/data
```

`train_label.txt` 에 hard 라벨이 추가된다. 콘솔에 최종 train/val 건수가 찍힌다.

### 4.4 RunPod: pod 생성 후 데이터 업로드

로컬 `finetune/data/` 를 pod 의 `/workspace/data` 로 올린다 (RunPod 웹 파일탐색기,
`scp`, 또는 `runpodctl send`/`receive` 중 편한 것). 예시(scp, pod SSH 정보는 콘솔에서 확인):

```bash
scp -r "C:/Users/user/Desktop/ITDA 공모전/repo/finetune/data" root@<POD_IP>:/workspace/data
```

### 4.5 RunPod: 환경 설치

```bash
bash setup.sh
```

`finetune/runpod/` 의 파일들(`setup.sh`, `*.yml`, `train_rec.sh`, `export_rec.sh`)도
pod 의 `/workspace/runpod/` 로 함께 올려 둘 것 (`train_rec.sh` 가 `../runpod/*.yml` 을 참조).

### 4.6 RunPod: 사용량 기록 시작 + 학습

```bash
cd /workspace/runpod
python3 log_usage.py start --gpu "RTX 4090" --price 0.69 --purpose "rec finetune"
cd /workspace/PaddleOCR
bash ../runpod/train_rec.sh
tail -f /workspace/logs/train_rec.log
```

### 4.7 RunPod: ONNX 변환 + 사용량 기록 종료

```bash
bash ../runpod/export_rec.sh                 # 기본으로 output/rec_korean_v5_ft/best_accuracy 사용
cd /workspace/runpod
python3 log_usage.py end --krw-rate 1450      # 환율은 실행 시점 값으로 교체
```

`/workspace/korean_PP-OCRv5_rec_ft.onnx` 가 산출물. 로컬로 내려받는다.

### 4.8 로컬: weights 교체 + 검증

```bash
cp korean_PP-OCRv5_rec_ft.onnx "C:/Users/user/Desktop/ITDA 공모전/repo/weights/"
cd "C:/Users/user/Desktop/ITDA 공모전/repo"
PYTHONIOENCODING=utf-8 "C:/anaconda/envs/itda/python.exe" finetune/validate_local.py --rec korean_PP-OCRv5_rec_ft.onnx
```

`evaluate.py` 결과와 `auto_gold_v4.csv` 대비 고침/깨짐 이미지 목록이 출력된다.
정확도가 오르고 깨짐이 고침보다 적으면 `weights/korean_PP-OCRv5_rec_mobile.onnx` 를
이 파일로 교체 확정.

### 4.9 (선택) det 2단계

```bash
PYTHONIOENCODING=utf-8 "C:/anaconda/envs/itda/python.exe" finetune/runpod/prep_det_data.py --data finetune/data
```

`finetune/data/det/images/` 를 PPOCRLabel 로 직접 박스 라벨링 (자동화 범위 밖, 안내는
`finetune/data/det/labeling_instructions.xlsx` 참고). 라벨링 끝나면 RunPod 에서
`train_det.sh` 실행, export 는 `export_rec.sh` 를 복사해 경로만 det 용으로 바꿔 사용.

## 5. RunPod 사용량과 비용 기록 방법

- `finetune/runpod/log_usage.py start/end` : `finetune/USAGE_LOG.md` 에 시작/종료
  시각, GPU 종류, 시간당 단가, 총 시간, USD/KRW 비용을 표로 남긴다. 보고서에 그대로
  옮겨 쓸 수 있게 표 형식(마크다운)으로 저장.
- 실제 청구액 확인(공식 기록): RunPod 콘솔 Settings > Billing > Usage.
- API 로 조회: `RUNPOD_API_KEY=xxxx python3 finetune/runpod/runpod_usage.py` 가 현재
  떠 있는(또는 최근) pod 목록과 시간당 단가, 가동 시간, 추정 비용을 출력. GraphQL
  쿼리 원형은 `query { myself { pods { id name costPerHr uptimeSeconds } } }`.
- 보고서(가산점 아님, 규정 "비용 명시": 클라우드 GPU만 명시 필요)에는
  `USAGE_LOG.md` 의 표를 그대로 인용.

## 6. 예상 시간과 비용

| 단계 | 예상 시간 | 비고 |
|---|---|---|
| prep_rec_data.py (전체 993장) | 1.5~2시간 | 로컬 CPU, det 3종 + rec 2종 매 이미지 |
| hard_labels.xlsx 수동 라벨링 | 1~2시간 | hard 크롭 수(약 200장 이미지 기준 600~900개)에 비례 |
| RunPod 환경 설치 | 10~15분 | PaddlePaddle-GPU + PaddleOCR clone + pip |
| rec 학습 30 epoch | 30분~1.5시간 | 데이터 수백~1천 장, RTX 4090 기준. epoch 당 데이터 적어 빠름 |
| export + ONNX 변환 | 5분 | |
| 로컬 검증(골드 1,000장, retry_upscale) | 15~25분 | 기존 autolabel_gold_v4 실측(64분/1,000장 x 0.4 정도) 참고 |
| **RunPod GPU 합계** | **1시간 내외** | RTX 4090 시간당 $0.4~0.7 기준 **$0.5~1 (약 700원~1,500원)** |

det 2단계는 박스 라벨링(수동, 200~300장 기준 2~4시간)이 병목이라 별도 산정.
det 학습 자체는 rec 과 비슷하게 1시간 이내.

## 7. 주의점

- `src/ocr.py`, `tools/`, `tests/` 는 이 작업에서 건드리지 않았다. `validate_local.py` 는
  import 후 `ocr._REC_FILES`/`ocr.DET_FILE` 을 런타임에 바꿔치기하는 방식으로 원본을
  그대로 둔다.
- ONNX 에 문자 딕셔너리를 메타데이터 키 `character` 로 박아 넣었기 때문에
  `weights/` 파일만 교체하면 끝난다. rapidocr-onnxruntime 버전이 메타데이터를 못 읽는
  경우의 대안으로 `rec_keys_path` 에 별도 dict 파일을 넘기는 방법도 `export_rec.sh`
  주석에 적어 뒀다.
- **가중치 파일(.onnx, .pdparams 등)은 git에 올리지 않는다** (`.gitignore` 이미 차단).
  파인튜닝된 ONNX 는 규정대로 Release Assets 또는 외부 링크 + `download_weights.sh` 로 배포.
- `finetune/data/` 는 이미지 크롭이 수천 장 쌓이므로 git에서 제외했다.
- 학습 자체는 하지 않았다. RunPod 접속, `train_rec.sh` 실행, 결과 확인은 사용자 몫.
- **미검증 항목** (인터넷 접속 가능한 이 세션에서 09-11 기준으로 웹 확인했지만 실제
  pod 에서 재확인 필요):
  - `korean_PP-OCRv5_mobile_rec_pretrained.pdparams` 다운로드 URL은 PaddleOCR 공식 문서에서
    직접 확인함. `PP-OCRv5_mobile_det_pretrained.pdparams` URL은 같은 경로 패턴으로 추정한
    것으로, 검색 결과 기반이라 setup.sh 의 `curl --fail` 이 실패하면 PaddleOCR 이슈/모델
    zoo 문서를 다시 찾아야 함.
  - `character_dict_path`: CLAUDE.md 는 `ppocr/utils/dict/ppocrv5_korean_dict.txt` 로
    적어 뒀지만 그런 파일은 실재하지 않는다. 실제로는 PP-OCRv5 전체가 언어 공용
    딕셔너리 `ppocr/utils/dict/ppocrv5_dict.txt` 하나를 쓴다 (여러 언어가 한 딕셔너리에
    합쳐져 있음, ONNX 메타데이터로 직접 확인 완료: 11,946개 토큰).
  - `Optimizer.lr.learning_rate: 0.0005`: CLAUDE.md 는 "기본값의 1/10"이라 적었지만
    실제 base config(`PP-OCRv5_mobile_rec.yml`)의 기본값도 이미 0.0005. 지시받은 값
    0.0005 는 그대로 넣었고, 이 사실만 기록해 둔다 (더 보수적으로 가려면 0.0001 검토).
  - PaddleOCR 태그 `v3.4.0` 에 `configs/rec/PP-OCRv5/`, `configs/det/PP-OCRv5/`,
    `ppocr/utils/dict/ppocrv5_dict.txt` 가 실제로 있는지는 `main` 브랜치에서만 확인했다.
    `setup.sh` clone 직후 `ls` 로 확인하는 줄을 넣어 뒀으니 없으면 태그를 올리거나
    `main` 으로 바꿀 것.
  - `rec_korean_v5_finetune.yml`/`det_v5_finetune.yml` 은 base config 전체를 옮겨 쓰지
    않고 바뀌는 키만 담아 `-o` 커맨드라인 오버라이드로 합친다(`train_rec.sh`/`train_det.sh`
    가 자동으로 펼침). base config 의 Backbone/Head/증강 설정을 손으로 옮기다 shape 를
    잘못 맞춰 사전학습 가중치 로딩이 깨지는 위험을 피하기 위한 선택.
