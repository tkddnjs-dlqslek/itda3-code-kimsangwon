# -*- coding: utf-8 -*-
"""파인튜닝 목적에 맞게 rec 데이터셋을 다시 뽑는다 (v2).

목적: korean_PP-OCRv5_mobile_rec 이 소비기한 날짜 숫자와 곁에 붙은 한글 키워드
(소비기한/유통기한/제조일자/까지/부터)를 스스로 읽게 만드는 것. 그래서 유효한
학습 데이터는 "날짜/키워드 크롭 + 정답 라벨"뿐이다. 영양정보·전화번호·바코드·
LOT 단독·상품명은 제외한다.

2-fold 교차검증: fold A 는 000001~000500 만 학습해 000501~001000 을 채점하고,
fold B 는 그 반대다. 그래서 골드 1,000장 전부가 자신을 학습에 쓰지 않은 모델로
채점된다 (leakage 없음). finetune/data_v2/foldA/, foldB/ 에 각각 독립된
imgs/train_label.txt/val_label.txt/manual/manual_labels.xlsx 를 만든다.

python finetune/prep_rec_data_v2.py
"""
from __future__ import annotations

import csv
import os
import random
import re
import shutil
import sys

import cv2
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_REPO, "src"))

import dateparse  # noqa: E402
import ocr  # noqa: E402

from build_labels import _load_dict_chars  # noqa: E402 (같은 finetune/ 안, dict 문자 검증 재사용)

_LABELS_DIR = os.path.join(_REPO, "labels")
_GOLD_CSV = os.path.join(_LABELS_DIR, "gold.csv")
_REC_ONNX = os.path.join(_REPO, "weights", "korean_PP-OCRv5_rec_mobile.onnx")
_DATA_DIR = os.path.join(_HERE, "data")
_OUT_DIR = os.path.join(_HERE, "data_v2")
_AUTO_LABEL = os.path.join(_DATA_DIR, "rec", "auto_label.txt")
_AUTO_DIR = os.path.join(_DATA_DIR, "rec", "auto")
_HARD_DIR = os.path.join(_DATA_DIR, "rec", "hard")
_HARD_XLSX = os.path.join(_DATA_DIR, "rec", "hard_labels.xlsx")

HANJA_RE = re.compile(r"[一-鿿]")
_PHONE_BARCODE_RE = re.compile(r"\d{10,}|080-|1588|1399|-\d{4}-\d{4}")

# --- clean label 필터 -------------------------------------------------------
KW = r"소비기한|유통기한|품질유지기한|제조일자|제조일|까지|부터|EXP|EXPIRY|BEST\s*BEFORE|BEST\s*BY|BBE|USE\s*BY|PROD|LOT|JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC"

def is_clean_label(lab: str) -> bool:
    rest = re.sub(KW, "", lab, flags=re.I)
    rest = re.sub(r"[0-9.\-/:,\s()]", "", rest)
    return rest == "" or re.fullmatch(r"[A-Za-z0-9]{1,3}", rest) is not None

# --- merge_digits: tools/bench_merge.py 정책 C 를 그대로 복사 (import 시 assert/print 부작용 피함) ---
_DIGITS_SEP_RE = re.compile(r"[0-9OoIl|.\-/:,\s]+")


def _complete_cands(text: str) -> list:
    return [c for c in dateparse.find_candidates(text) if None not in (c.y, c.m, c.d)]


def merge_digits(K: str, C: str) -> str:
    """K(ko) 텍스트에 C 가 읽어낸 완전 날짜만 이식한다."""
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


# --- 골드/ID ------------------------------------------------------------

def _load_gold() -> dict:
    return {r["image_id"]: r for r in csv.DictReader(open(_GOLD_CSV, encoding="utf-8"))}


def _gold_tuple(row: dict) -> tuple:
    return (row["year"], row["month"], row["day"])


def _fmt_cand(c: dateparse.Candidate) -> tuple:
    y = "NONE" if c.y is None else str(c.y).zfill(4)
    m = "NONE" if c.m is None else str(c.m).zfill(2)
    d = "NONE" if c.d is None else str(c.d).zfill(2)
    return y, m, d


def _complete_tuples(text: str) -> set:
    return {_fmt_cand(c) for c in _complete_cands(text)}


def _write_fold_ids(fold: str, train_ids: list, eval_ids: list) -> None:
    with open(os.path.join(_LABELS_DIR, f"fold_{fold}_train_ids.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(train_ids) + "\n")
    with open(os.path.join(_LABELS_DIR, f"fold_{fold}_eval_ids.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(eval_ids) + "\n")


def _read_png(path: str):
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(path)
    return img


def _digits(text: str) -> int:
    return sum(ch.isdigit() for ch in text or "")


# --- step 1: auto 세트에서 ERROR / CORRECT 분류 ----------------------------

def _parse_auto_label(path: str) -> list:
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line:
            continue
        relpath, label = line.split("\t", 1)
        fname = relpath.split("/")[-1]
        image_id = fname.split("_", 1)[0]
        rows.append((relpath, label, image_id, fname))
    return rows


def build_from_auto(gold: dict, train_ids: set, dict_chars: set) -> dict:
    rows = _parse_auto_label(_AUTO_LABEL)
    rows = [r for r in rows if r[2] in train_ids]
    # 골드가 부분(NONE 포함)인 이미지는 complete 후보와 절대 못 맞으므로 미리 뺀다
    rows = [r for r in rows if "NONE" not in _gold_tuple(gold[r[2]])]

    crops = [_read_png(os.path.join(_DATA_DIR, r[0])) for r in rows]
    ko_texts = [t for t, _ in ocr._rec("ko")(crops)[0]] if crops else []

    accepted_error, manual_error, dirty_auto, correct_pool = [], [], [], []
    reasons = {"no_gold_in_clean": 0, "bad_char": 0, "hanja": 0, "correct_oov": 0, "dirty_label": 0}

    for (relpath, label, image_id, fname), ko_text, crop in zip(rows, ko_texts, crops):
        g = gold[image_id]
        gold_t = _gold_tuple(g)
        gold_date = f"{g['year']}-{g['month']}-{g['day']}"
        ld = _complete_tuples(label)
        kd = _complete_tuples(ko_text)

        if gold_t in kd:
            # CORRECT crop: check if ko_text is clean
            if not is_clean_label(ko_text):
                ch_text = ocr._rec("ch")([crop])[0][0][0]
                dirty_auto.append(dict(image_id=image_id, ko_text=ko_text, ch_text=ch_text,
                                       gold_date=gold_date, proposed_label=ko_text,
                                       src_path=os.path.join(_DATA_DIR, relpath), fname=fname))
                reasons["dirty_label"] += 1
                continue
            if all(ch in dict_chars for ch in ko_text):
                correct_pool.append((relpath, ko_text, image_id))
            else:
                reasons["correct_oov"] += 1
            continue

        if gold_t in ld and gold_t not in kd:
            clean = merge_digits(ko_text, label)
            # Check if ERROR clean label is clean
            if not is_clean_label(clean):
                ch_text = ocr._rec("ch")([crop])[0][0][0]
                dirty_auto.append(dict(image_id=image_id, ko_text=ko_text, ch_text=ch_text,
                                       gold_date=gold_date, proposed_label=clean,
                                       src_path=os.path.join(_DATA_DIR, relpath), fname=fname))
                reasons["dirty_label"] += 1
                continue
            ok = (gold_t in _complete_tuples(clean)
                  and all(ch in dict_chars for ch in clean)
                  and not HANJA_RE.search(clean))
            if ok:
                accepted_error.append((relpath, clean, image_id, ko_text))
            else:
                if gold_t not in _complete_tuples(clean):
                    reasons["no_gold_in_clean"] += 1
                elif HANJA_RE.search(clean):
                    reasons["hanja"] += 1
                else:
                    reasons["bad_char"] += 1
                # 사람이 볼 수 있게 중국어 모델도 다시 돌려 참고 텍스트를 채운다
                ch_text = ocr._rec("ch")([crop])[0][0][0]
                manual_error.append(dict(image_id=image_id, ko_text=ko_text, ch_text=ch_text,
                                          gold_date=gold_date, note="자동 정답 생성 실패: " + (
                                              "정답 파싱 안 됨" if gold_t not in _complete_tuples(clean) else
                                              "한자 포함" if HANJA_RE.search(clean) else "사전에 없는 문자"),
                                          src_path=os.path.join(_DATA_DIR, relpath), fname=fname))

    return dict(accepted_error=accepted_error, manual_error=manual_error,
                dirty_auto=dirty_auto, correct_pool=correct_pool, reasons=reasons)


# --- step 2: hard 세트에서 후보만 걸러 manual 로 ----------------------------

def build_from_hard(train_ids: set) -> tuple:
    from openpyxl import load_workbook
    wb = load_workbook(_HARD_XLSX, data_only=True)
    ws = wb.active
    header = [c.value for c in ws[1]]
    idx = {name: i for i, name in enumerate(header)}
    kept = []
    excluded = {"no_digits": 0, "no_candidate": 0, "phone_barcode": 0, "not_train": 0}
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r is None or r[idx["file"]] is None:
            continue
        image_id = str(r[idx["image_id"]]).strip()
        if image_id not in train_ids:
            excluded["not_train"] += 1
            continue
        ko_text = str(r[idx["ko_text"]] or "")
        ch_text = str(r[idx["ch_text"]] or "")
        if _PHONE_BARCODE_RE.search(ko_text) or _PHONE_BARCODE_RE.search(ch_text):
            excluded["phone_barcode"] += 1
            continue
        if max(_digits(ko_text), _digits(ch_text)) < 4:
            excluded["no_digits"] += 1
            continue
        if not (dateparse.find_candidates(ko_text) or dateparse.find_candidates(ch_text)):
            excluded["no_candidate"] += 1
            continue
        kept.append(dict(image_id=image_id, ko_text=ko_text, ch_text=ch_text,
                          gold_date=str(r[idx["gold_date"]] or ""), note=str(r[idx["note"]] or ""),
                          src_path=os.path.join(_HARD_DIR, r[idx["file"]]), fname=r[idx["file"]]))
    return kept, excluded


# --- step 3/4: anchor 샘플링 + train/val 분할 -------------------------------

def build_train_val(accepted_error: list, correct_pool: list, out_dir: str) -> tuple:
    n_anchor = len(accepted_error)
    if n_anchor < 150 and correct_pool:
        n_anchor = min(150, len(correct_pool))

    rng = random.Random(42)
    anchor = correct_pool if len(correct_pool) <= n_anchor else rng.sample(correct_pool, n_anchor)

    imgs_dir = os.path.join(out_dir, "rec", "imgs")
    os.makedirs(imgs_dir, exist_ok=True)
    final_rows = []  # (fname, label, image_id)
    combined = [(r[0], r[1], r[2]) for r in accepted_error] + [(r[0], r[1], r[2]) for r in anchor]

    # Drop exact duplicates: same image_id and identical label
    seen = set()
    deduped_combined = []
    for relpath, label, image_id in combined:
        key = (image_id, label)
        if key not in seen:
            seen.add(key)
            deduped_combined.append((relpath, label, image_id))

    for relpath, label, image_id in deduped_combined:
        fname = relpath.split("/")[-1]
        shutil.copyfile(os.path.join(_DATA_DIR, relpath), os.path.join(imgs_dir, fname))
        final_rows.append((fname, label, image_id))

    ids = sorted({iid for _, _, iid in final_rows})
    rng2 = random.Random(42)
    rng2.shuffle(ids)
    n_val = max(1, round(len(ids) * 0.15)) if ids else 0
    val_ids = set(ids[:n_val])
    train_pairs = [(f, l) for f, l, iid in final_rows if iid not in val_ids]
    val_pairs = [(f, l) for f, l, iid in final_rows if iid in val_ids]

    rec_dir = os.path.join(out_dir, "rec")
    with open(os.path.join(rec_dir, "train_label.txt"), "w", encoding="utf-8") as f:
        for fn, l in train_pairs:
            f.write(f"rec/imgs/{fn}\t{l}\n")
    with open(os.path.join(rec_dir, "val_label.txt"), "w", encoding="utf-8") as f:
        for fn, l in val_pairs:
            f.write(f"rec/imgs/{fn}\t{l}\n")

    # Return deduped anchor for counting
    anchor_deduped = [(r[0], r[1], r[2]) for r in deduped_combined if any((r[0], r[1], r[2]) == (ra[0], ra[1], ra[2]) for ra in anchor)]
    return anchor_deduped, train_pairs, val_pairs


# --- step 5: manual xlsx ---------------------------------------------------

def write_manual_xlsx(manual_rows: list, out_dir: str) -> None:
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    from PIL import Image as PILImage

    manual_dir = os.path.join(out_dir, "rec", "manual")
    os.makedirs(manual_dir, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "manual"
    header = ["번호", "이미지 번호", "사진", "모델이 읽은 글자", "중국어 모델 글자", "골드 날짜", "제안 라벨", "출처", "정답", "메모", "file"]
    ws.append(header)
    for c in range(1, len(header) + 1):
        ws.cell(1, c).font = Font(bold=True)
        ws.cell(1, c).fill = PatternFill("solid", fgColor="DDDDDD")
    widths = [6, 12, 12, 26, 26, 12, 20, 16, 20, 30, 20]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"

    for i, r in enumerate(manual_rows, start=2):
        dst_fname = f"{'auto' if r['src_path'].replace(os.sep, '/').find('/auto/') >= 0 else 'hard'}_{r['fname']}"
        dst_path = os.path.join(manual_dir, dst_fname)
        shutil.copyfile(r["src_path"], dst_path)

        ws.cell(i, 1, i - 1)
        c_id = ws.cell(i, 2, r["image_id"])
        c_id.number_format = "@"
        ws.cell(i, 4, r["ko_text"])
        ws.cell(i, 5, r["ch_text"])
        ws.cell(i, 6, r["gold_date"])
        ws.cell(i, 7, r.get("proposed_label", ""))  # 제안 라벨
        ws.cell(i, 8, r.get("src", "정답 모름"))  # 출처: "자동 라벨 의심" or "정답 모름"
        ws.cell(i, 9, "")  # 정답 (사용자가 채움)
        ws.cell(i, 10, r.get("note", ""))  # 메모
        ws.cell(i, 11, dst_fname)
        try:
            w, h = PILImage.open(dst_path).size
            img = XLImage(dst_path)
            img.height = 40
            img.width = max(1, int(40 * w / h))
            ws.row_dimensions[i].height = 32
            img.anchor = f"C{i}"
            ws.add_image(img)
        except Exception as e:
            ws.cell(i, 3, f"(미리보기 실패: {e})")

    info = wb.create_sheet("안내")
    info["A1"] = "제안 라벨이 사진과 똑같으면 정답 칸에 그대로 복사하세요."
    info["A2"] = "다르면 사진에 인쇄된 그대로 고쳐 적으세요 (날짜, 키워드, 붙어 있는 LOT 문자 포함)."
    info["A3"] = "날짜가 없는 조각이면 정답 칸에 제외 라고 적으세요."
    wb.save(os.path.join(out_dir, "rec", "manual_labels.xlsx"))


# --- summary ---------------------------------------------------------------

def _fold_section(fold: str, counts: dict) -> list:
    lines = [f"## fold {fold} (train {counts['train_range']}, eval {counts['eval_range']})"]
    lines.append(f"- ERROR 크롭(자동 라벨 채택): {counts['error_accepted']}")
    lines.append(f"- ERROR 크롭(수동 시트로 이관): {counts['error_manual']}")
    lines.append(f"- 자동 라벨 의심(garbage 필터링): {counts['dirty_auto']}")
    lines.append(f"- CORRECT 크롭 중 anchor 샘플: {counts['anchor']}")
    lines.append(f"- hard 세트에서 수동 시트로 이관: {counts['hard_manual']}")
    lines.append(f"- 중복 제거됨: {counts['duplicates_dropped']}")
    lines.append(f"- train: {counts['train']}  val: {counts['val']}")
    lines.append("- 제외 사유: " + ", ".join(f"{k}={v}" for k, v in counts["reasons"].items()))
    return lines


def write_summary(out_dir: str, counts_a: dict, counts_b: dict) -> None:
    lines = [
        "# 파인튜닝 데이터셋 v2 요약 (2-fold 교차검증)",
        "",
        "목적: korean_PP-OCRv5_mobile_rec 이 소비기한 날짜 숫자와 곁의 한글 키워드",
        "(소비기한/유통기한/제조일자/까지/부터)를 직접 읽게 학습시킨다.",
        "성공하면 한자로 키워드를 깨뜨리는 중국어 교차검증 모델을 뺄 수 있다.",
        "",
        "골드 1,000장 전부를 채점하면서도 leakage 를 없애려고 2-fold 로 나눴다.",
        "fold A 는 000001~000500 만 학습해 000501~001000 을 채점하고, fold B 는 그 반대다.",
        "각 이미지는 항상 자신을 학습에 쓰지 않은 모델이 채점하므로 1,000장 전부 정직하게 검증된다.",
        "",
        "## Clean Label 필터",
        "자동 라벨 (~23%)에서 인쇄되지 않은 garbage 텍스트(e.g. 'E월E2027.06.29', '2026.05.26 그교·D트')를",
        "정규식으로 필터링. 소비기한 키워드와 숫자/구분자를 제거한 후 남은 문자가 없거나",
        "알파벳/숫자 1-3자 이하면 clean으로 판정. 의심 라벨은 manual 시트로 이관해 사용자 검수.",
        "",
    ]
    lines += _fold_section("A", counts_a)
    lines.append("")
    lines += _fold_section("B", counts_b)
    lines += [
        "",
        "## 참고 파일",
        "- repo/labels/fold_A_train_ids.txt, fold_A_eval_ids.txt",
        "- repo/labels/fold_B_train_ids.txt, fold_B_eval_ids.txt",
    ]
    with open(os.path.join(out_dir, "SUMMARY.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# --- fold 처리 --------------------------------------------------------

def process_fold(fold: str, train_ids: list, eval_ids: list, gold: dict, dict_chars: set) -> tuple:
    _write_fold_ids(fold, train_ids, eval_ids)
    train_id_set = set(train_ids)
    out_dir = os.path.join(_OUT_DIR, f"fold{fold}")
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(os.path.join(out_dir, "rec"), exist_ok=True)

    print(f"[fold {fold}] step1: auto 세트 처리 중...", flush=True)
    r1 = build_from_auto(gold, train_id_set, dict_chars)
    print(f"  ERROR 채택 {len(r1['accepted_error'])}, ERROR->manual {len(r1['manual_error'])}, "
          f"자동 라벨 의심 {len(r1['dirty_auto'])}, CORRECT pool {len(r1['correct_pool'])}", flush=True)

    print(f"[fold {fold}] step2: hard 세트 처리 중...", flush=True)
    hard_manual, hard_excluded = build_from_hard(train_id_set)
    print(f"  hard->manual {len(hard_manual)}", flush=True)

    print(f"[fold {fold}] step3/4: anchor 샘플링 + train/val 분할...", flush=True)
    anchor, train_pairs, val_pairs = build_train_val(r1["accepted_error"], r1["correct_pool"], out_dir)

    print(f"[fold {fold}] step5: manual xlsx 작성 중...", flush=True)
    # Add "src" field to dirty_auto rows
    for row in r1["dirty_auto"]:
        row["src"] = "자동 라벨 의심"
    manual_rows = r1["manual_error"] + r1["dirty_auto"] + hard_manual
    write_manual_xlsx(manual_rows, out_dir)

    reasons = dict(r1["reasons"])
    reasons.update({f"hard_{k}": v for k, v in hard_excluded.items()})
    counts = dict(error_accepted=len(r1["accepted_error"]), error_manual=len(r1["manual_error"]),
                  dirty_auto=len(r1["dirty_auto"]), anchor=len(anchor), hard_manual=len(hard_manual),
                  duplicates_dropped=len(r1["accepted_error"]) + len(anchor) - len(train_pairs) - len(val_pairs),
                  train=len(train_pairs), val=len(val_pairs), reasons=reasons,
                  train_range=f"{train_ids[0]}~{train_ids[-1]}", eval_range=f"{eval_ids[0]}~{eval_ids[-1]}")
    return counts, r1["accepted_error"]


# --- main --------------------------------------------------------------

def main() -> None:
    os.makedirs(_OUT_DIR, exist_ok=True)
    gold = _load_gold()
    dict_chars = _load_dict_chars(_REC_ONNX)

    ids_1_500 = [f"{i:06d}" for i in range(1, 501)]
    ids_501_1000 = [f"{i:06d}" for i in range(501, 1001)]

    counts_a, examples_a = process_fold("A", ids_1_500, ids_501_1000, gold, dict_chars)
    counts_b, examples_b = process_fold("B", ids_501_1000, ids_1_500, gold, dict_chars)

    write_summary(_OUT_DIR, counts_a, counts_b)

    print("\n===== 완료 =====")
    for name, counts in (("fold A", counts_a), ("fold B", counts_b)):
        print(f"-- {name} (train {counts['train_range']}, eval {counts['eval_range']}) --")
        for k, v in counts.items():
            if k not in ("reasons", "train_range", "eval_range"):
                print(f"  {k}: {v}")
        print(f"  reasons: {counts['reasons']}")

    print("\n6개 clean ERROR 예시 (korean 읽기 -> 정답 라벨):")
    for relpath, label, image_id, ko_text in (examples_a + examples_b)[:6]:
        if is_clean_label(label):
            g = gold[image_id]
            print(f"  {image_id}: '{ko_text}' -> '{label}'")

    print("\n6개 자동 라벨 의심 예시 (korean 읽기):")
    # Re-run process to get dirty examples
    r1_a = build_from_auto(gold, set(ids_1_500), dict_chars)
    r1_b = build_from_auto(gold, set(ids_501_1000), dict_chars)
    for row in (r1_a["dirty_auto"] + r1_b["dirty_auto"])[:6]:
        print(f"  {row['image_id']}: '{row['proposed_label']}'  (korean 읽기)")


if __name__ == "__main__":
    main()
