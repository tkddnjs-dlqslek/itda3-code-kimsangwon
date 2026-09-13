"""bench_erode_split.csv 가 다 차면 3가지 변형(no_erode, erode_no_split, erode_split=v5)의
gold 1,000장 exact/field 총점과 서로 다른 방향 회귀(regression) 목록을 계산해
labels/erode_split_summary.txt 에 쓴다. 세션이 끊겨도 이 스크립트만 다시 돌리면 된다.

python tools/summarize_erode_split.py
"""
import csv

GOLD = "labels/gold.csv"
V5 = "labels/auto_gold_v5.csv"
BENCH = "labels/bench_erode_split.csv"
OUT = "labels/erode_split_summary.txt"

VARIANTS = ["no_erode", "erode_no_split", "erode_split"]


def load_dict(path, key="image_id"):
    with open(path, encoding="utf-8") as f:
        return {r[key]: r for r in csv.DictReader(f)}


def main():
    gold = load_dict(GOLD)
    v5 = load_dict(V5)
    bench = {}
    with open(BENCH, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            bench[(r["image_id"], r["variant"])] = r

    targets = sorted(iid for iid, r in v5.items() if r["stage"] in ("erode5", "erode3", "fail"))
    missing = [(iid, v) for iid in targets for v in ("no_erode", "erode_no_split")
               if (iid, v) not in bench]
    lines = []
    lines.append(f"gold n={len(gold)}  target images (v5 stage erode5/erode3/fail)={len(targets)}")
    if missing:
        lines.append(f"WARNING: bench_erode_split.csv incomplete, {len(missing)} pairs missing "
                      f"(e.g. {missing[:5]}) -- rerun tools/bench_erode_split.py first")

    # variant -> image_id -> (y, m, d)
    pred = {v: {} for v in VARIANTS}
    for iid in gold:
        v5r = v5.get(iid)
        base = (v5r["year"], v5r["month"], v5r["day"]) if v5r else ("NONE", "NONE", "NONE")
        pred["erode_split"][iid] = base
        for variant, key in (("no_erode", "no_erode"), ("erode_no_split", "erode_no_split")):
            if iid in targets and (iid, key) in bench:
                b = bench[(iid, key)]
                pred[variant][iid] = (b["year"], b["month"], b["day"])
            else:
                pred[variant][iid] = base  # 침식 단계까지 안 간 이미지는 세 변형이 동일

    def exact_field(variant):
        n_exact, field_sum = 0, 0.0
        for iid, g in gold.items():
            y, m, d = pred[variant][iid]
            gy, gm, gd = g["year"], g["month"], g["day"]
            ok = [y == gy, m == gm, d == gd]
            if all(ok):
                n_exact += 1
            field_sum += sum(ok) / 3
        n = len(gold)
        return n_exact / n, field_sum / n, n_exact

    lines.append("")
    lines.append(f"{'variant':<16}{'exact':>8}{'field':>8}{'n_exact':>10}")
    for v in VARIANTS:
        e, fs, ne = exact_field(v)
        lines.append(f"{v:<16}{e:>8.3f}{fs:>8.3f}{ne:>10d}")

    def is_exact(variant, iid):
        y, m, d = pred[variant][iid]
        g = gold[iid]
        return y == g["year"] and m == g["month"] and d == g["day"]

    lines.append("")
    lines.append("regressions among target images (correct in one variant, wrong in another):")
    pairs = [("no_erode", "erode_no_split"), ("erode_no_split", "erode_split"), ("no_erode", "erode_split")]
    for a, b in pairs:
        a_right_b_wrong = [iid for iid in targets if is_exact(a, iid) and not is_exact(b, iid)]
        b_right_a_wrong = [iid for iid in targets if is_exact(b, iid) and not is_exact(a, iid)]
        lines.append(f"  {a} right / {b} wrong ({len(a_right_b_wrong)}): {a_right_b_wrong}")
        lines.append(f"  {b} right / {a} wrong ({len(b_right_a_wrong)}): {b_right_a_wrong}")

    text = "\n".join(lines)
    print(text)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text + "\n")


if __name__ == "__main__":
    main()
