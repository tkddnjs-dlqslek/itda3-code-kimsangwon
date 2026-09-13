"""단계 교차검증 실험: s1, s2 에서 찾은 날짜가 '약한 후보'면 뒤 단계를 최대 2개 더 돌려 비교한다.
- 약한 후보: 접두 만료 키워드 점수(+2)를 못 받은 후보
- 추가로 돌릴 조건: 2자리 연도로 읽혔거나, 동점 2순위가 있거나, 부분 날짜일 때만 (골드 기준 215장)
- 선택: 두 단계 이상에서 같은 날짜가 나오면 그 날짜, 아니면 규칙 점수가 높은 쪽
"""
import os, sys, csv, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import cv2, numpy as np
import dateparse as D, ocr
from pipeline import list_images

def best_of(lines):
    pool = D._rank(lines)
    return (pool[0], pool) if pool else (None, [])

def needs_more(b, pool) -> bool:
    if b is None or b.score >= 2.0:
        return False
    two_digit = b.y is not None and str(b.y) not in b.text
    tie = len(pool) > 1 and abs(pool[1].score - b.score) < 1e-9
    partial = None in (b.y, b.m, b.d)
    return two_digit or tie or partial

def key(c):
    f = lambda v, w: "NONE" if v is None else str(v).zfill(w)
    return (f(c.y, 4), f(c.m, 2), f(c.d, 2))

def read_cross(path):
    img = ocr._load(path)
    keep = lambda c: c.shape[0] >= 20 and c.shape[1] / c.shape[0] <= 12
    items = ocr._crops(img)
    big = [it for it in items if keep(it[0])]
    small = [it for it in items if not keep(it[0])]
    acc, stage = [], "fail"
    out = ocr.hybrid_rec(big)
    acc += out
    b, pool = best_of(ocr.group_lines(out))
    if b is not None:
        stage = "s1"
    else:
        out2 = ocr.hybrid_rec(small); acc += out2
        b, pool = best_of(ocr.group_lines(acc))
        if b is not None:
            stage = "s2"
    if b is None:                       # 날짜 자체가 없으면 기존 파이프라인에 맡긴다
        items, st = ocr.read_raw(path, retry_upscale=True)
        r = D.extract_date(ocr.group_lines(items))
        return (key(r and type("C",(object,),{"y":int(r[0]) if r[0]!="NONE" else None,
                                              "m":int(r[1]) if r[1]!="NONE" else None,
                                              "d":int(r[2]) if r[2]!="NONE" else None})()) if r else ("NONE",)*3), st, 0
    if not needs_more(b, pool):
        return key(b), stage, 0
    # 추가 단계 최대 2개: det5, clahe (재시도용 rec 사용)
    votes = {key(b): b.score}
    extra = 0
    for name, fn in (("det5", lambda: ocr.hybrid_rec(ocr._crops(img, v5=True), retry=True)),
                     ("clahe", lambda: ocr.hybrid_rec(ocr._crops(ocr._clahe(img), loose=True), retry=True))):
        got = fn(); extra += 1
        b2, _ = best_of(ocr.group_lines(got))
        if b2 is None:
            continue
        k2 = key(b2)
        if k2 in votes:                 # 두 단계가 같은 날짜 -> 확정
            return k2, f"{stage}+{name}(동의)", extra
        votes[k2] = max(votes.get(k2, -99), b2.score)
    best_key = max(votes.items(), key=lambda kv: kv[1])[0]
    return best_key, f"{stage}+교차{extra}", extra

ids = {l.strip() for l in open("labels/gold_ids.txt", encoding="utf-8") if l.strip()}
out_csv = "labels/auto_gold_crosscheck.csv"
done = set()
if os.path.exists(out_csv):
    done = {r["image_id"] for r in csv.DictReader(open(out_csv, encoding="utf-8"))}
paths = [p for p in list_images("../images") if os.path.splitext(os.path.basename(p))[0] in ids
         and os.path.splitext(os.path.basename(p))[0] not in done]
t0 = time.time()
with open(out_csv, "a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    if not done:
        w.writerow(["image_id", "year", "month", "day", "final_date", "stage", "extra", "sec"])
    for i, p in enumerate(paths, 1):
        s = time.time()
        try:
            (y, m, d), st, ex = read_cross(p)
        except Exception as e:
            y = m = d = "NONE"; st = f"error:{type(e).__name__}"; ex = 0
        final = "NONE" if (y, m, d) == ("NONE", "NONE", "NONE") else f"{y}-{m}-{d}"
        w.writerow([os.path.splitext(os.path.basename(p))[0], y, m, d, final, st, ex, round(time.time()-s, 2)])
        f.flush()
        if i % 100 == 0:
            print(f"{i}/{len(paths)} {(time.time()-t0)/i:.2f}s/img", flush=True)
print("DONE", flush=True)
