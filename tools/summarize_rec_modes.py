# -*- coding: utf-8 -*-
"""rec merge 정책 3종(hybrid/ko/merge) 비교 요약.
python tools/summarize_rec_modes.py
"""
from __future__ import annotations

import csv
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import dateparse

ROOT = os.path.join(os.path.dirname(__file__), "..")
LABELS = os.path.join(ROOT, "labels")
GOLD = os.path.join(LABELS, "gold.csv")
FILES = {
    "hybrid": os.path.join(LABELS, "auto_gold_v5.csv"),
    "ko": os.path.join(LABELS, "auto_gold_v5_ko.csv"),
    "merge": os.path.join(LABELS, "auto_gold_v5_merge.csv"),
}

HANJA_RE = re.compile(r"[一-鿿]")
KEYWORD_RE = re.compile(r"소비기한|유통기한|품질유지기한|제조일|까지|부터|EXP|BEST", re.I)


def load_csv(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {r["image_id"]: r for r in csv.DictReader(f)}


def field_ok(pred, gold):
    return [pred[k] == gold[k] for k in ("year", "month", "day")]


def avg_sec(rows):
    secs = [float(r["sec"]) for r in rows.values() if r.get("sec")]
    return sum(secs) / len(secs) if secs else None


def main():
    gold = load_csv(GOLD)
    modes = {name: load_csv(path) for name, path in FILES.items()}

    lines = [f"gold rows = {len(gold)}"]
    for name in modes:
        lines.append(f"{name}: {len(modes[name])} rows loaded from {FILES[name]}")
        print(f"{name}: {len(modes[name])} rows", flush=True)

    common_ids = [iid for iid in gold if all(iid in modes[m] for m in modes)]
    lines.append(f"common ids (gold + all 3 modes present) = {len(common_ids)}")
    lines.append("")
    print(f"common ids = {len(common_ids)}", flush=True)

    # --- exact / field / stage --------------------------------------------
    correctness = {}   # mode -> {image_id: bool}
    stats = {}         # mode -> (exact, field_sum, stage_counts)
    for name, rows in modes.items():
        exact, field_sum, stages = 0, 0.0, {}
        correctness[name] = {}
        for iid in common_ids:
            ok3 = field_ok(rows[iid], gold[iid])
            is_exact = all(ok3)
            exact += int(is_exact)
            field_sum += sum(ok3) / 3.0
            correctness[name][iid] = is_exact
            st = rows[iid].get("stage", "")
            stages[st] = stages.get(st, 0) + 1
        stats[name] = (exact, field_sum, stages)

    n = len(common_ids) or 1
    lines.append(f"{'mode':<10}{'exact':>8}{'exact%':>10}{'field_avg':>12}")
    for name in modes:
        exact, field_sum, _ = stats[name]
        lines.append(f"{name:<10}{exact:>8}{exact / n * 100:>9.1f}%{field_sum / n:>12.4f}")
    lines.append("")
    for name in modes:
        _, _, stages = stats[name]
        top = ", ".join(f"{k}={v}" for k, v in sorted(stages.items(), key=lambda kv: -kv[1]))
        lines.append(f"{name} stage counts: {top}")
    lines.append("")

    # --- pairwise diffs -----------------------------------------------------
    def pairwise(a, b):
        a_r_b_w = [iid for iid in common_ids if correctness[a][iid] and not correctness[b][iid]]
        b_r_a_w = [iid for iid in common_ids if correctness[b][iid] and not correctness[a][iid]]
        return a_r_b_w, b_r_a_w

    for a, b in (("ko", "hybrid"), ("merge", "hybrid"), ("ko", "merge")):
        a_r_b_w, b_r_a_w = pairwise(a, b)
        lines.append(f"{a} correct & {b} wrong ({len(a_r_b_w)}): {', '.join(a_r_b_w)}")
        lines.append(f"{b} correct & {a} wrong ({len(b_r_a_w)}): {', '.join(b_r_a_w)}")
        lines.append("")

    # --- hanja + keyword-date lines ------------------------------------------
    for name, rows in modes.items():
        n_imgs, n_lines, n_kwdate = 0, 0, 0
        for iid in common_ids:
            text_lines = (rows[iid].get("texts") or "").split(" | ") if rows[iid].get("texts") else []
            has_hanja = False
            for line in text_lines:
                if HANJA_RE.search(line):
                    n_lines += 1
                    has_hanja = True
                if KEYWORD_RE.search(line) and any(
                    None not in (c.y, c.m, c.d) for c in dateparse.find_candidates(line)
                ):
                    n_kwdate += 1
            n_imgs += int(has_hanja)
        lines.append(f"{name}: hanja images={n_imgs} hanja lines={n_lines} keyword+date lines={n_kwdate}")
    lines.append("")

    # --- timing ---------------------------------------------------------------
    for name in ("ko", "merge"):
        a = avg_sec(modes[name])
        if a is not None:
            lines.append(f"{name}: avg {a:.2f} s/img over {len(modes[name])} rows "
                          f"(CPU shared with other jobs, rough)")

    hybrid_log = os.path.join(LABELS, "autolabel_gold_v5.log")
    if os.path.exists(hybrid_log):
        with open(hybrid_log, encoding="utf-8") as f:
            spi_lines = [l for l in f if "s/img" in l]
        if spi_lines:
            m = re.search(r"([\d.]+)s/img", spi_lines[-1])
            if m:
                lines.append(f"hybrid: {float(m.group(1)):.2f} s/img (from {hybrid_log}, "
                              f"CPU shared with other jobs, rough)")

    text = "\n".join(lines) + "\n"
    print(text, flush=True)
    out_path = os.path.join(LABELS, "rec_modes_summary.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
