#!/bin/bash
# 휴대폰 브라우저는 https 가 아니면 카메라를 열지 않는다. 같은 와이파이에서 쓸 자체 서명 인증서를 만든다.
#   bash app/tools/make_cert.sh 192.168.0.10     (PC 의 와이파이 IP, ipconfig 의 IPv4 주소)
# 휴대폰에서 https://<IP>:8443 접속 후 "안전하지 않음 > 계속" 한 번 누르면 된다.
set -e
IP="${1:?PC 의 IP 를 인자로 주세요}"
DIR="$(cd "$(dirname "$0")/.." && pwd)/.data"
mkdir -p "$DIR"
TMP="$(mktemp -d)"                              # Git Bash 의 openssl 이 한글 경로에 못 써서 임시 폴더 경유
WTMP="$(cygpath -w "$TMP" 2>/dev/null || echo "$TMP")"
openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
  -keyout "$WTMP/key.pem" -out "$WTMP/cert.pem" -subj "//CN=$IP" \
  -addext "subjectAltName=IP:$IP,DNS:localhost" 2>/dev/null
cp "$TMP/key.pem" "$TMP/cert.pem" "$DIR/"
rm -rf "$TMP"
echo "만듦: app/.data/cert.pem, key.pem"
echo "실행: python -m uvicorn server:create_app --factory --app-dir app --host 0.0.0.0 --port 8443 --ssl-keyfile app/.data/key.pem --ssl-certfile app/.data/cert.pem"
