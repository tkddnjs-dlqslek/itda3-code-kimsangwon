# OCR 파인튜닝 준비 (rec 우선, det 2단계)

이 폴더는 학습을 대신 실행하지 않는다. 데이터 준비, RunPod 스크립트, ONNX 변환,
로컬 검증까지 "준비"만 담당한다. 실제 학습(RunPod 접속, `bash train_rec.sh` 실행)은
사용자가 직접 한다.

## 1. 목표

- 골드 1,000장 기준 rec 오독(6↔5, 2↔0 등)과 det 미검출(도트 프린팅, 금속면, 저대비)을
  줄이기 위해 korean_PP-OCRv5_rec_mobile 을 먼저 파인튜닝하고, 여유가 되면
  ch_PP-OCRv5_det_mobile 도 파인튜닝한다.
- 최종 산출물은 rapidocr-onnxruntime 1.3.24 가 그대로 읽는 ONNX 파일. `weights/` 안의
  기존 파일을 교체하는 것만으로 `src/ocr.py` 수정 없이 반영되게 만든다.

## 2. 전체 흐름 (09-12 갱신)

이번 라운드 학습 데이터는 이미 만들어져 있다: `../finetune_data/`
(`finetune_data/README.md` 참고). ExpDate Products-Real 크롭에서 골드 1,000장과
겹치는 96장을 제외하고 만든 것이라 **골드셋 오염이 없고, 수동 라벨링(hard_labels.xlsx)이
필요 없다** — 예전 `prep_rec_data.py` -> 수동 라벨링 -> `build_labels.py` 흐름(부록 참고)은
이번 라운드에서 건너뛴다.

```
[로컬, 완료됨] finetune_data/build_dataset.py   ExpDate 라벨 기반 rec 학습 데이터 자동 생성
   -> finetune_data/{base,aug}/imgs, train_label.txt(6,748줄), val_label.txt(776줄)
   -> upload_data.md 로 RunPod pod 의 /workspace/finetune_data 로 업로드
[RunPod] setup.sh                 PaddlePaddle-GPU, PaddleOCR, paddle2onnx 설치 + 사전학습 가중치 다운로드
[RunPod] log_usage.py start       사용량 기록 시작
[RunPod] train_rec.sh             rec 파인튜닝 (60 epoch, ~3,180 iter)
[RunPod] export_rec.sh            체크포인트 -> 추론모델 -> ONNX(+ 딕셔너리 내장)
[RunPod] log_usage.py end         사용량 기록 종료, pod 정지
   -> ONNX 파일을 로컬로 다운로드
[로컬] weights/ 에 복사
[로컬] validate_local.py          골드 1,000장 + ExpDate 라벨셋으로 기존 대비 diff 확인
   -> 개선되면 weights/ 교체 확정, requirements.txt/제출 준비
(선택, 2단계) det 도 같은 흐름: prep_det_data.py -> PPOCRLabel 수동 라벨링 ->
             train_det.sh -> export (export_rec.sh 참고해 경로만 바꿔 사용)
```

## 3. 사전 준비물

- 로컬: `C:/anaconda/envs/itda/python.exe` (rapidocr-onnxruntime, opencv, pandas, openpyxl 이미 설치됨)
- RunPod 계정, 결제 수단 등록, API 키 (`RUNPOD_API_KEY`, 콘솔 Settings > API Keys)
- RunPod pod: PyTorch/CUDA 12.x 템플릿, GPU 1장. **RTX 4090 권장** (시간당 $0.4~0.7대,
  콘솔 Secure/Community Cloud 시세 확인). 데이터가 수천 장 수준이라 A100 등 고가 GPU 불필요,
  RTX 3090 도 충분
- 인터넷 (로컬 준비 단계는 오프라인, RunPod 단계만 인터넷 필요, 채점 서버는 계속 오프라인이라 무관)

## 4. 단계별 명령 (이번 라운드 실행 순서)

### 4.1 로컬: 데이터 확인 (이미 준비됨)

```bash
cd "C:/Users/user/Desktop/ITDA 공모전"
wc -l finetune_data/train_label.txt finetune_data/val_label.txt   # 6748 / 776
```

새로 데이터를 더 넣고 싶으면 `finetune_data/build_dataset.py` 의 `add_crops(entries)` 로
크롭을 추가한 뒤 재실행 (`finetune_data/README.md` 참고). 이번 라운드는 추가 작업 없이 그대로 사용.

### 4.2 RunPod: pod 생성

콘솔에서 PyTorch/CUDA 12.x 템플릿으로 GPU pod 1개 생성 (RTX 4090 또는 3090, 위 "3. 사전
준비물" 참고). On-Demand 로 띄우고, 끝나면 반드시 4.9 에서 정지할 것 (켜둔 시간만큼 과금).

### 4.2-1 pod 설정 메모 (09-12 확정)

- GPU: RTX 4090 (Secure Cloud) $0.74/hr, 24GB. 템플릿은 `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`
- Container disk 30GB 그대로 충분 (PaddleOCR + 사전학습 가중치 + 데이터 140MB)
- Network volume 없이 진행. 종료 시 전부 삭제되므로 ONNX 를 내려받은 뒤 Terminate 할 것
- setup.sh 의 `CUDA_IDX` 기본값 cu126 유지. 드라이버가 12.8 이어도 하위 호환으로 동작하며,
  paddlepaddle-gpu 3.0.0 은 cu128 휠을 제공하지 않는다

### 4.3 RunPod: 환경 설치

`finetune/runpod/` 의 파일들(`setup.sh`, `*.yml`, `train_rec.sh`, `export_rec.sh`,
`log_usage.py`)을 pod 의 `/workspace/runpod/` 로 올린다 (웹 파일탐색기, scp, 또는
`runpodctl send/receive` — 방법은 `upload_data.md` 참고, 대상 폴더만 다르게).

```bash
cd /workspace/runpod
bash setup.sh
```

### 4.4 로컬 -> RunPod: 학습 데이터 업로드

`upload_data.md` 그대로 실행: `finetune_data/` 를 tar.gz 로 묶어 pod 의
`/workspace/finetune_data` 로 올리고 그 안에서 풀기. (`rec_korean_v5_finetune.yml` 이
이 경로를 `data_dir`/`label_file_list` 로 그대로 참조한다.)

### 4.5 RunPod: 사용량 기록 시작 + 학습 실행

```bash
cd /workspace/runpod
python3 log_usage.py start --gpu "RTX 4090" --price 0.74 --purpose "rec finetune"
cd /workspace/PaddleOCR
bash ../runpod/train_rec.sh
```

### 4.6 RunPod: 학습 로그 확인

```bash
tail -f /workspace/logs/train_rec.log
```

`eval_batch_step: [0, 150]` 이라 150 iter(약 2.8 epoch)마다 평가 로그가 찍힌다.
`best_accuracy` 가 갱신될 때마다 `output/rec_korean_v5_ft/best_accuracy.*` 로 자동 저장됨
(PaddleOCR `tools/train.py` 기본 동작, 이 설정에서 따로 건드리지 않음). 60 epoch(~3,180 iter)
완료까지 기다린다 (예상 시간은 6절 표 참고).

### 4.7 RunPod: ONNX 변환

```bash
cd /workspace/PaddleOCR
bash ../runpod/export_rec.sh                 # 기본으로 output/rec_korean_v5_ft/best_accuracy 사용
```

`/workspace/korean_PP-OCRv5_rec_ft.onnx` 가 산출물 (문자 딕셔너리가 ONNX 메타데이터
`character` 키로 내장됨, 콘솔에 "메타데이터 character 문자 수: 11945" 확인).

### 4.8 RunPod: ONNX 다운로드 + 사용량 기록 종료 + pod 정지

```bash
cd /workspace/runpod
python3 log_usage.py end --krw-rate 1450      # 환율은 실행 시점 값으로 교체
```

`/workspace/korean_PP-OCRv5_rec_ft.onnx` 를 로컬로 내려받는다 (웹 파일탐색기, scp, 또는
`runpodctl send`). 다운로드 확인 후 **RunPod 콘솔에서 pod 를 Stop(또는 Terminate)** 한다.
Stop 만 하면 볼륨 요금이 계속 붙을 수 있으니, 재사용 계획이 없으면 Terminate 권장.

### 4.9 로컬: weights 교체 + 검증

```bash
cp korean_PP-OCRv5_rec_ft.onnx "C:/Users/user/Desktop/ITDA 공모전/repo/weights/"
cd "C:/Users/user/Desktop/ITDA 공모전/repo"
PYTHONIOENCODING=utf-8 "C:/anaconda/envs/itda/python.exe" finetune/validate_local.py \
    --rec korean_PP-OCRv5_rec_ft.onnx --eval-set both
```

골드 1,000장(2-fold 권장 시 `--rec-a/--rec-b`)과 ExpDate 라벨셋
(`../expdate_check/expdate_answers.csv`, 골드 겹침 제외) 각각에 대해 baseline(현재
`weights/korean_PP-OCRv5_rec_mobile.onnx`) 대비 candidate 의 exact/field 점수와
고침/깨짐 이미지 목록이 출력된다. 정확도가 오르고 깨짐이 고침보다 적으면
`weights/korean_PP-OCRv5_rec_mobile.onnx` 를 이 파일로 교체 확정.

### 4.10 (선택) det 2단계

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
- **보고서에는 클라우드 GPU 사용 시간과 비용을 명시해야 한다** (규정 "비용 명시").
  `USAGE_LOG.md` 의 표를 그대로 인용할 것.

## 6. 예상 시간과 비용

| 단계 | 예상 시간 | 비고 |
|---|---|---|
| 데이터 준비 | 완료 | finetune_data/ (6,748 train / 776 val, base+aug) |
| finetune_data 업로드 (~140MB) | 5~15분 | 네트워크 속도에 따라 다름 |
| RunPod 환경 설치 | 10~15분 | PaddlePaddle-GPU + PaddleOCR clone + pip |
| rec 학습 60 epoch(~3,180 iter) | 30분~1.5시간 | RTX 4090 기준, 데이터 수천 장이라 epoch 당 빠름 |
| export + ONNX 변환 | 5분 | |
| 로컬 검증(골드 1,000장 + ExpDate셋, retry_upscale) | 20~35분 | 기존 autolabel_gold_v4 실측(64분/1,000장 x 0.4 정도) 참고, ExpDate셋(~1,300장) 추가분 포함 |
| **RunPod GPU 합계** | **1~2시간** | RTX 4090 시간당 $0.4~0.7 기준 **$0.5~1.5 (약 700원~2,200원)** |

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
- `finetune_data/`, `finetune/data*/` 는 이미지가 수천 장 쌓이므로 git에서 제외했다.
- 학습 자체는 하지 않았다. RunPod 접속, `train_rec.sh` 실행, 결과 확인, pod 정지는 사용자 몫.
- 09-12 하이퍼파라미터 결정 근거 (파인튜닝 가이드, 단일 GPU 기준): batch 128, lr 1e-4 ->
  2e-5 로 감쇠(Piecewise, epoch 40 지점에서 전환), warmup 3 epoch(~159 iter, 가이드 권장
  100~200 iter), epoch_num 60(=~3,180 iter, 가이드 권장 "수천 iteration" 충족),
  eval_batch_step 150 로 자주 평가 + best_accuracy 자동 저장. 상세 근거는
  `runpod/rec_korean_v5_finetune.yml` 주석 참고.
- `Optimizer.lr` 을 Cosine 에서 Piecewise 로 바꾼 이유: PaddleOCR 의 Cosine 스케줄러는
  0 으로 수렴해 "2e-5 까지만 낮추기"가 안 됨. Piecewise 는 `values` 로 하한을 직접 지정 가능.
- `train_rec.sh` 의 override 플래튼 스크립트는 float 를 고정소수점 문자열로 변환한다
  (09-12 수정). `str(2e-05)` 가 `'2e-05'`(지수표기, 점 없음)를 내놓는데, PaddleOCR 의
  `-o` 파서(`yaml.load`)는 점 없는 지수표기를 float 이 아니라 문자열로 읽어버려 학습률이
  깨진다 — 재현/검증은 이 세션에서 로컬로 override 파싱을 시뮬레이션해 확인함.
- **미검증 항목** (인터넷 접속 가능한 이 세션에서 09-11/09-12 기준으로 웹 확인했지만 실제
  pod 에서 재확인 필요):
  - 사전학습 가중치 URL 2개는 09-11 응답 확인 완료: `korean_PP-OCRv5_mobile_rec_pretrained.pdparams`
    약 111MB, `PP-OCRv5_mobile_det_pretrained.pdparams` 약 14MB.
  - 학습 base config 는 `configs/rec/PP-OCRv5/multi_language/korean_PP-OCRv5_mobile_rec.yml`, 문자 사전은 `ppocr/utils/dict/ppocrv5_korean_dict.txt` (11,945자).
    로컬 `korean_PP-OCRv5_rec_mobile.onnx` 메타데이터와 순서까지 같고, PaddleOCR v3.4.0 태그에 두 파일이
    모두 있음 (09-11 확인). base config 의 `Global.epoch_num=75`, `Optimizer.lr.name=Cosine`,
    `warmup_epoch=5` 도 09-12 웹에서 재확인함.
  - `rec_korean_v5_finetune.yml`/`det_v5_finetune.yml` 은 base config 전체를 옮겨 쓰지
    않고 바뀌는 키만 담아 `-o` 커맨드라인 오버라이드로 합친다(`train_rec.sh`/`train_det.sh`
    가 자동으로 펼침). base config 의 Backbone/Head/증강 설정을 손으로 옮기다 shape 를
    잘못 맞춰 사전학습 가중치 로딩이 깨지는 위험을 피하기 위한 선택.
  - `paddle2onnx --opset_version 14` 는 export_rec.sh 에 09-11 부터 그대로, onnxruntime
    CPU 추론과 호환되는 표준 opset (재확인은 pod 에서 export 실행 시).

## 부록: 이전 라운드 수동 라벨링 방식 (이번 라운드는 미사용)

골드셋에서 직접 rec 크롭을 뽑아 일부만 수동 라벨링하던 초기 방식. `finetune_data/` 로
대체되어 이번 파인튜닝 라운드에서는 실행하지 않지만, 스크립트는 남겨 둔다(참고/향후 데이터
추가용).

```bash
cd "C:/Users/user/Desktop/ITDA 공모전/repo"
PYTHONIOENCODING=utf-8 "C:/anaconda/envs/itda/python.exe" finetune/prep_rec_data.py --limit 30 --out finetune/data_test
# 문제 없으면 전체 실행 (약 1~2시간, 배경 실행 권장)
PYTHONIOENCODING=utf-8 "C:/anaconda/envs/itda/python.exe" finetune/prep_rec_data.py --out finetune/data
```

`finetune/data/rec/hard_labels.xlsx` 를 열어 미리보기를 보면서 `label` 칸에 실제
표기를 정확히 입력(예: `2026.06.28`), 날짜 크롭이 아니면 `skip` 칸에 `x`. 비워 둔 행은
다음 단계에서 자동으로 건너뛴다.

```bash
PYTHONIOENCODING=utf-8 "C:/anaconda/envs/itda/python.exe" finetune/build_labels.py --data finetune/data
```

`train_label.txt` 에 hard 라벨이 추가된다. 이 방식으로 만든 데이터를 쓰려면
`rec_korean_v5_finetune.yml` 의 `data_dir`/`label_file_list` 를 해당 경로로 바꿔야 한다.
