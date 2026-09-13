# -*- coding: utf-8 -*-
"""세 가지 rec merge 정책 벤치: A ko_only, B v4_current, C merge_digits.
python tools/bench_merge.py
"""
import sys, os, csv, re, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import ocr, dateparse

ROOT = os.path.join(os.path.dirname(__file__), "..")
GOLD_PATH = os.path.join(ROOT, "labels", "gold.csv")
IMAGES_DIR = os.path.join(ROOT, "..", "images")
OUT_PATH = os.path.join(ROOT, "..", "figures", "bench_merge.txt")

# --- merge_digits (정책 C) ---------------------------------------------------
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

# --- 벤치 --------------------------------------------------------------------
KEYWORD_RE = re.compile(r"까지|부터|소비기한|유통기한|제조|exp|best", re.I)
HANJA_RE = re.compile(r"[一-鿿]")


def _redo_idx(ko_texts):
    return [i for i, t in enumerate(ko_texts)
            if sum(c.isdigit() for c in t) >= 3 or dateparse.find_candidates(t)]


def build_A(ko_res, ch_res, redo, boxes):
    return [(t, b) for (t, conf), b in zip(ko_res, boxes) if conf >= ocr._MIN_CONF]


def build_B(ko_res, ch_res, redo, boxes):
    res = list(ko_res)
    for i in redo:
        if i in ch_res:
            t, conf = ch_res[i]
            if ocr._has_complete_date(t) or not ocr._has_complete_date(res[i][0]):
                res[i] = (t, conf)
    return [(t, b) for (t, conf), b in zip(res, boxes) if conf >= ocr._MIN_CONF]


def build_C(ko_res, ch_res, redo, boxes):
    res = list(ko_res)
    for i in redo:
        if i in ch_res:
            t_ch, conf_ch = ch_res[i]
            t_ko, conf_ko = res[i]
            merged = merge_digits(t_ko, t_ch)
            # ponytail: 병합 텍스트에 딱 맞는 conf 모델이 없다. 두 엔진 conf의 max 로 근사.
            res[i] = (merged, max(conf_ko, conf_ch))
    return [(t, b) for (t, conf), b in zip(res, boxes) if conf >= ocr._MIN_CONF]


POLICIES = {"A_ko_only": build_A, "B_v4_current": build_B, "C_merge_digits": build_C}


def pred_str(lines):
    d = dateparse.extract_date(lines)
    return "-".join(d) if d else "NONE-NONE-NONE"


def main():
    gold_rows = list(csv.DictReader(open(GOLD_PATH, encoding="utf-8")))
    files = {}
    for f in os.listdir(IMAGES_DIR):
        stem, ext = os.path.splitext(f)
        if ext.lower() in (".jpg", ".jpeg", ".png"):
            files[stem] = os.path.join(IMAGES_DIR, f)

    exact = {k: 0 for k in POLICIES}
    field_sum = {k: 0.0 for k in POLICIES}
    kw_date_lines = {k: 0 for k in POLICIES}
    hanja_lines = {k: 0 for k in POLICIES}
    n = 0
    diffs = []  # (image_id, gold, predB, predC)

    t0 = time.time()
    for row in gold_rows:
        iid = row["image_id"]
        path = files.get(iid)
        gold_str = f'{row["year"]}-{row["month"]}-{row["day"]}'
        if path is None:
            continue
        n += 1

        img = ocr._load(path)
        items = ocr._crops(img)
        keep = [(c, b) for c, b in items if c.shape[0] >= 20 and c.shape[1] / c.shape[0] <= 12]
        preds = {}
        if keep:
            crops = [c for c, _ in keep]
            boxes = [b for _, b in keep]
            ko_res = list(ocr._rec("ko")(crops)[0])
            redo = _redo_idx([t for t, _ in ko_res])
            ch_res = {}
            if redo:
                for i, (t, conf) in zip(redo, ocr._rec("ch")([crops[i] for i in redo])[0]):
                    ch_res[i] = (t, conf)

            for name, build in POLICIES.items():
                texts = build(ko_res, ch_res, redo, boxes)
                lines = ocr.group_lines(texts)
                preds[name] = pred_str(lines)
                for line in lines:
                    if HANJA_RE.search(line):
                        hanja_lines[name] += 1
                    if KEYWORD_RE.search(line) and any(
                        None not in (c.y, c.m, c.d) for c in dateparse.find_candidates(line)
                    ):
                        kw_date_lines[name] += 1
        else:
            for name in POLICIES:
                preds[name] = "NONE-NONE-NONE"

        gold_fields = row["year"], row["month"], row["day"]
        for name in POLICIES:
            p = preds[name]
            exact[name] += int(p == gold_str)
            pf = p.split("-")
            field_sum[name] += sum(a == b for a, b in zip(pf, gold_fields)) / 3.0

        if preds["B_v4_current"] != preds["C_merge_digits"] and len(diffs) < 15:
            diffs.append((iid, gold_str, preds["B_v4_current"], preds["C_merge_digits"]))

        if n % 100 == 0:
            print(f"{n} images, {time.time() - t0:.0f}s elapsed, exact={exact}", flush=True)

    lines_out = []
    lines_out.append(f"n images = {n}")
    lines_out.append(f"{'policy':<16}{'exact':>8}{'field_score':>14}{'kw_date_lines':>16}{'hanja_lines':>14}")
    for name in POLICIES:
        lines_out.append(
            f"{name:<16}{exact[name]:>8}{field_sum[name] / n:>14.4f}{kw_date_lines[name]:>16}{hanja_lines[name]:>14}"
        )
    lines_out.append("")
    lines_out.append("B vs C differing image_ids (up to 15): image_id, gold, B, C")
    for iid, g, b, c in diffs:
        lines_out.append(f"{iid}, {g}, {b}, {c}")

    text = "\n".join(lines_out) + "\n"
    print(text, flush=True)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    main()
