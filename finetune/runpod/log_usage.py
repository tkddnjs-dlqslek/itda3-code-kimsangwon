# -*- coding: utf-8 -*-
"""RunPod GPU 사용량/비용을 finetune/USAGE_LOG.md 에 기록. 공모전 보고서용 (클라우드 GPU
비용 명시 규칙, CLAUDE.md "비용 명시" 참고).

python finetune/runpod/log_usage.py start --gpu "RTX 4090" --price 0.69 --purpose "rec finetune"
  (pod 켜자마자 실행, pending 행 하나 추가)
python finetune/runpod/log_usage.py end [--krw-rate 1450]
  (학습 끝나고 실행, 가장 최근 pending 행을 찾아 종료시각/시간/비용을 채움)
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_LOG = os.path.join(os.path.dirname(_HERE), "USAGE_LOG.md")
_HEADER = "| 시작 | 종료 | GPU | 시간당(USD) | 시간(h) | 비용(USD) | 비용(KRW) | 용도 |\n" \
          "|---|---|---|---|---|---|---|---|\n"


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def _read_rows() -> list:
    if not os.path.exists(_LOG):
        return []
    lines = open(_LOG, encoding="utf-8").read().splitlines()
    return [l for l in lines if l.startswith("|") and not l.startswith("|---") and "시작" not in l]


def _write_rows(rows: list) -> None:
    with open(_LOG, "w", encoding="utf-8") as f:
        f.write("# RunPod 사용량 기록\n\n")
        f.write(_HEADER)
        f.write("\n".join(rows) + ("\n" if rows else ""))


def cmd_start(args) -> None:
    rows = _read_rows()
    row = f"| {_now()} | (진행중) | {args.gpu} | {args.price:.2f} |  |  |  | {args.purpose} |"
    rows.append(row)
    _write_rows(rows)
    print(f"기록 시작: {row}")


def cmd_end(args) -> None:
    rows = _read_rows()
    pending = [i for i, r in enumerate(rows) if "(진행중)" in r]
    if not pending:
        raise SystemExit("(진행중) 행이 없음. log_usage.py start 를 먼저 실행했는지 확인")
    i = pending[-1]
    cells = [c.strip() for c in rows[i].strip("|").split("|")]
    start_s, _, gpu, price_s = cells[0], cells[1], cells[2], cells[3]
    start = dt.datetime.strptime(start_s, "%Y-%m-%d %H:%M")
    end = dt.datetime.now()
    hours = (end - start).total_seconds() / 3600
    price = float(price_s)
    cost_usd = hours * price
    cost_krw = cost_usd * args.krw_rate
    purpose = cells[7] if len(cells) > 7 else ""
    rows[i] = (f"| {start_s} | {end.strftime('%Y-%m-%d %H:%M')} | {gpu} | {price:.2f} | "
               f"{hours:.2f} | {cost_usd:.2f} | {cost_krw:,.0f} | {purpose} |")
    _write_rows(rows)
    print(f"기록 종료: {hours:.2f}h, ${cost_usd:.2f} (~{cost_krw:,.0f}원)")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("start")
    p1.add_argument("--gpu", required=True)
    p1.add_argument("--price", type=float, required=True, help="시간당 USD")
    p1.add_argument("--purpose", required=True)
    p1.set_defaults(func=cmd_start)
    p2 = sub.add_parser("end")
    p2.add_argument("--krw-rate", type=float, default=1450.0)
    p2.set_defaults(func=cmd_end)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
