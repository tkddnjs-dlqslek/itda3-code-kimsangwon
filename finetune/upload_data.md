# finetune_data 업로드 (로컬 -> RunPod pod)

`finetune_data/`(로컬 `C:/Users/user/Desktop/ITDA 공모전/finetune_data/`, 학습에 필요한
`base/`+`aug/`+`train_label.txt`+`val_label.txt` 실측 약 140MB, `__pycache__`/미리보기
PNG/`build_dataset.py` 는 학습에 안 쓰므로 제외)를 pod 의 `/workspace/finetune_data` 로
올린다. `rec_korean_v5_finetune.yml` 이 이 경로를 그대로 참조하므로 경로를 바꾸면 yml 도
같이 바꿔야 한다.

## 1. 로컬(Windows, Git Bash): tar.gz 압축

```bash
cd "C:/Users/user/Desktop/ITDA 공모전"
tar -czf finetune_data.tar.gz -C finetune_data base aug train_label.txt val_label.txt
ls -lh finetune_data.tar.gz   # 130~140MB 내외 예상 (이미지가 이미 PNG라 gzip 효율은 낮음)
```

## 2. 전송 (둘 중 편한 것)

### 2a. scp (pod 에 SSH 포트가 열려 있을 때, RunPod 콘솔 pod 상세 > Connect > SSH over exposed TCP 에서 포트/IP 확인)

```bash
scp -P <SSH_PORT> finetune_data.tar.gz root@<POD_IP>:/workspace/
```

### 2b. runpodctl send/receive (SSH 없이, RunPod 릴레이 경유 — 방화벽 문제 있을 때 대안)

로컬:
```bash
runpodctl send finetune_data.tar.gz
# 출력되는 1회용 코드(예: 8342-cactus-happy-tree)를 복사
```
pod 웹 터미널(또는 SSH)에서:
```bash
runpodctl receive 8342-cactus-happy-tree   # 위에서 복사한 코드로 교체
```
(`runpodctl` 이 pod 에 없으면: `curl -L https://github.com/runpod/runpodctl/releases/latest/download/runpodctl-linux-amd64 -o /usr/local/bin/runpodctl && chmod +x /usr/local/bin/runpodctl`)

## 3. pod 에서 압축 해제

```bash
mkdir -p /workspace/finetune_data
tar -xzf finetune_data.tar.gz -C /workspace/finetune_data
rm finetune_data.tar.gz   # 디스크 정리(선택)
wc -l /workspace/finetune_data/train_label.txt /workspace/finetune_data/val_label.txt
# 6748 / 776 이 나와야 함 (로컬 실측과 동일, 09-12 확인)
```
