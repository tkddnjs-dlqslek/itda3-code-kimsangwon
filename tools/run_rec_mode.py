# -*- coding: utf-8 -*-
"""gold 1,000장을 rec merge 정책(ko|merge)으로 재라벨.
python tools/run_rec_mode.py --mode ko|merge --out labels/auto_gold_v5_ko.csv

시작 시 labels/auto_gold_v5.csv 가 1,000행이 되고 그 csv 를 쓰는 autolabel.py
프로세스가 끝날 때까지 60초 간격으로 대기한다 (같은 CPU, det/rec 엔진 캐시를
공유하지 않으려는 목적이 아니라 스코어 산정용 원본이 완성되길 기다리는 것).
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import ocr
import dateparse
from pipeline import list_images, predict_one

ROOT = os.path.join(os.path.dirname(__file__), "..")
GOLD_V5 = os.path.join(ROOT, "labels", "auto_gold_v5.csv")
IDS_PATH = os.path.join(ROOT, "labels", "gold_ids.txt")
IMAGES_DIR = os.path.join(ROOT, "..", "images")

# --- merge_digits: tools/bench_merge.py 그대로 복사 (그 파일은 import 시 벤치를 돌려서 import 금지) ---
_DIGITS_SEP_RE = re.compile(r"[0-9OoIl|.\-/:,\s]+")


def _complete_cands(text):
    return [c for c in dateparse.find_candidates(text) if None not in (c.y, c.m, c.d)]


def merge_digits(K: str, C: str) -> str:
    """K(ko) 텍스트에 C(ch)가 읽어낸 완전 날짜 D 만 이식한다. 한자는 D 바깥으로 새지 않는다."""
    c_cands = _complete_cands(C)
    if not c_cands:
        return K
    d_cand = max(c_cands, key=lambda c: len(c.text))
    D = d_cand.text
    if any((c.y, c.m, c.d) == (d_cand.y, d_cand.m, d_cand.d) for c in _complete_cands(K)):
        return K
    best = None
    for m in _DIGITS_SEP_RE.finditer(K):
        s, e = m.span()
        while s < e and K[s].isspace():
            s += 1
        while e > s and K[e - 1].isspace():
            e -= 1
        if sum(ch.isdigit() for ch in K[s:e]) >= 4:
            if best is None or (e - s) > (best[1] - best[0]):
                best = (s, e)
    if best is None:
        return D + " " + K
    s, e = best
    return K[:s] + D + K[e:]


def _run_asserts():
    cases = [
        (("2025.12.14 까지", "2025.12.11外"), "2025.12.11 까지"),
        (("소비기한", "2025.12.11外"), "2025.12.11 소비기한"),
        (("2025.12.11", "2025.12.11外"), "2025.12.11"),
        (("2025.12.11 까지", "소비기한外"), "2025.12.11 까지"),
        (("소비기한 2025.12.19", "2025.12.11外"), "소비기한 2025.12.11"),
        (("2026.03.14", "2026.03.20A"), "2026.03.20"),
    ]
    for (k, c), expected in cases:
        got = merge_digits(k, c)
        assert got == expected, f"merge_digits({k!r}, {c!r}) = {got!r}, expected {expected!r}"
    print(f"[assert] merge_digits: {len(cases)}/{len(cases)} passed", flush=True)


_run_asserts()


# --- 정책 --------------------------------------------------------------------
def ko_rec(items: list) -> list:
    """ko 모델 단독. items = [(crop, box)] -> [(text, box)] (conf 기준 통과분)."""
    if not items:
        return []
    res = ocr._rec("ko")([c for c, _ in items])[0]
    return [(t, box) for (t, conf), (_, box) in zip(res, items) if conf >= ocr._MIN_CONF]


def merge_rec(items: list) -> list:
    """hybrid_rec 과 같은 크롭 선정(숫자 3개 이상 또는 날짜 후보)이지만, ch 결과로 크롭
    전체를 교체하지 않고 merge_digits 로 날짜 부분만 이식한다."""
    if not items:
        return []
    crops = [c for c, _ in items]
    res = list(ocr._rec("ko")(crops)[0])
    redo = [i for i, (t, _) in enumerate(res)
            if sum(c.isdigit() for c in t) >= 3 or dateparse.find_candidates(t)]
    if redo:
        for i, (t_ch, conf_ch) in zip(redo, ocr._rec("ch")([crops[i] for i in redo])[0]):
            t_ko, conf_ko = res[i]
            res[i] = (merge_digits(t_ko, t_ch), max(conf_ko, conf_ch))
    return [(t, box) for (t, conf), (_, box) in zip(res, items) if conf >= ocr._MIN_CONF]


POLICIES = {"ko": ko_rec, "merge": merge_rec}


# --- auto_gold_v5.csv 대기 ----------------------------------------------------
def _v5_running() -> bool:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Select-Object -ExpandProperty CommandLine"],
            capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return True  # 확인 실패 시 안전하게 "돌고 있다"고 본다
    return any("autolabel.py" in l and "auto_gold_v5.csv" in l for l in out.splitlines())


def _v5_rows() -> int:
    if not os.path.exists(GOLD_V5):
        return 0
    with open(GOLD_V5, encoding="utf-8") as f:
        return max(sum(1 for _ in f) - 1, 0)


def wait_for_v5():
    while True:
        n, running = _v5_rows(), _v5_running()
        if n >= 1000 and not running:
            print(f"auto_gold_v5.csv ready: {n} rows, no autolabel.py running", flush=True)
            return
        print(f"waiting: auto_gold_v5.csv rows={n} autolabel_running={running}", flush=True)
        time.sleep(60)


# --- 메인 --------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=sorted(POLICIES))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    wait_for_v5()
    ocr.hybrid_rec = POLICIES[args.mode]

    ids = [l.strip() for l in open(IDS_PATH, encoding="utf-8") if l.strip()]
    paths = {os.path.splitext(os.path.basename(p))[0]: p for p in list_images(IMAGES_DIR)}
    todo = [(iid, paths[iid]) for iid in ids if iid in paths]

    out_path = os.path.join(ROOT, args.out) if not os.path.isabs(args.out) else args.out
    done = set()
    if os.path.exists(out_path):
        done = {r["image_id"] for r in csv.DictReader(open(out_path, encoding="utf-8"))}
        todo = [(iid, p) for iid, p in todo if iid not in done]
        print(f"resume: {len(done)} done, {len(todo)} left", flush=True)

    t0 = time.time()
    with open(out_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not done:
            w.writerow(["image_id", "year", "month", "day", "final_date", "stage", "texts", "raw", "sec"])
        for i, (iid, p) in enumerate(todo, 1):
            t1 = time.time()
            r = predict_one(p, strict=True, retry_upscale=True)
            sec = time.time() - t1
            w.writerow([r["image_id"], r["year"], r["month"], r["day"], r["final_date"], r["stage"],
                        " | ".join(r["texts"]), r["raw"], f"{sec:.3f}"])
            f.flush()
            if i % 50 == 0 or i == len(todo):
                print(f"{i}/{len(todo)}  {(time.time() - t0) / i:.2f}s/img", flush=True)
    print(f"[{args.mode}] done: {len(todo)} images in {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
