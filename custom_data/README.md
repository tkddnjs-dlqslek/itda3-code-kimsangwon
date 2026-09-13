# custom_data: 직접 라벨링한 데이터

주최측이 제공한 이미지 3,352장에 **직접 정답을 붙인 결과물**입니다. 사진 자체를 새로 촬영해 모은 것이
아니라, 라벨이 없는 제공 데이터에 사람이 판독한 정답을 붙였습니다. 구축 논리와 판정 기준은 요약서 PDF
2쪽에 있습니다.

## 폴더 구조

```
custom_data/
  labels/
    gold_1000.csv                 골드셋 1,000장 정답 (image_id, year, month, day, final_date, note)
    nongold_known_dates_336.csv   골드 밖 336장 정답 (image_id, source, date)
    v3_crop_review_475.csv        글자 조각 475개 검수 원본 (모델이 읽은 글자, 사람이 고친 값, 메모)
    v3_crop_labels_298.csv        위 검수에서 학습에 쓸 수 있게 확정한 298개 (file, label, source)
    v3_crop_overrides.tsv         475개 중 89개를 고치거나 뺀 판단 근거 (id, action, 사유)
    keyword_variants.xlsx         OCR 이 자주 틀리는 키워드 변형 22종 (유동기한 -> 유통기한 등)
    LABELING_RULES.md             라벨링 판정 기준
  crops/                          298개 글자 조각 이미지 (png, v3_crop_labels_298.csv 의 file 열과 대응)
```

## 각 파일이 만들어진 방식

- `gold_1000.csv`: 1,000장을 사람이 눈으로 보고 채웠습니다. 연, 월, 일을 각각 독립으로 적고 판독 불가는
  NONE 으로 둡니다. 파이프라인 성능 판정은 전부 이 파일 기준입니다.
- `nongold_known_dates_336.csv`: 골드 밖에서 파이프라인이 실패한 사진을 따로 검수해 날짜를 채운 것입니다.
- `v3_crop_review_475.csv` 와 `v3_crop_labels_298.csv`: 재시도 단계에서 뽑힌 글자 조각을 사람이 검수해
  정답 문자열을 확정했습니다. 조각이 잘렸거나 두 줄이 섞였거나 뒤집힌 것은 제외했습니다.
- `keyword_variants.xlsx`: 실제 오인식 사례에서 모은 변형 표이고, 후처리 규칙의 키워드 교정 사전으로
  코드에 반영돼 있습니다.

## 사용처

- `gold_1000.csv` 는 저장소의 `labels/gold.csv` 와 같은 파일입니다. 코드가 그 경로를 참조하므로 양쪽에
  두었습니다.
- `crops/` 와 `v3_crop_labels_298.csv` 는 rec 모델 추가 파인튜닝(v3) 학습 데이터로 썼습니다. 측정 결과
  골드 1,000장에서 901 에서 896 으로 떨어져 채택하지 않았고, 그 판단 과정은 `EXPERIMENT_LOG.md` 에
  기록했습니다.
