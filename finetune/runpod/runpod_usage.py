# -*- coding: utf-8 -*-
"""RunPod GraphQL API 로 실제 실행 중/과거 pod 와 현재까지의 대략적 비용을 조회.
로컬에서 실행 (RunPod pod 안이 아니어도 됨). API 키: https://www.runpod.io/console/user/settings

RUNPOD_API_KEY=xxxx python finetune/runpod/runpod_usage.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

_QUERY = """
query {
  myself {
    pods {
      id
      name
      costPerHr
      uptimeSeconds
      desiredStatus
      machine { gpuDisplayName }
    }
  }
}
"""


def main() -> None:
    key = os.environ.get("RUNPOD_API_KEY")
    if not key:
        sys.exit("RUNPOD_API_KEY 환경변수를 설정하세요 (RunPod 콘솔 > Settings > API Keys)")
    url = f"https://api.runpod.io/graphql?api_key={key}"
    body = json.dumps({"query": _QUERY}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)

    if "errors" in data:
        sys.exit(f"API 오류: {data['errors']}")

    pods = data["data"]["myself"]["pods"]
    if not pods:
        print("실행 중이거나 최근 조회 가능한 pod 없음 (종료된 pod 는 이 쿼리로 안 보일 수 있음 -> "
              "정확한 청구 내역은 콘솔 Billing > Usage 페이지에서 확인)")
        return

    total = 0.0
    print(f"{'name':20s} {'gpu':18s} {'상태':10s} {'시간(h)':>8s} {'비용(USD)':>10s}")
    for p in pods:
        hours = p["uptimeSeconds"] / 3600
        cost = hours * p["costPerHr"]
        total += cost
        gpu = (p.get("machine") or {}).get("gpuDisplayName", "?")
        print(f"{p['name'][:20]:20s} {gpu[:18]:18s} {p['desiredStatus']:10s} {hours:8.2f} {cost:10.2f}")
    print(f"\n합계(현재 조회된 pod 기준, 이미 종료/삭제된 pod 는 미포함): ${total:.2f}")
    print("정확한 최종 청구액은 콘솔 Settings > Billing > Usage 에서 확인할 것")


if __name__ == "__main__":
    main()
