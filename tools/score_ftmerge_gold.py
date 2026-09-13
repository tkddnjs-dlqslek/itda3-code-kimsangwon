"""한국어 모델 결과는 그대로 두고 '날짜 숫자 구간'만 파인튜닝 모델 결과로 바꾸는 구성으로 골드 1,000장 채점.
- 조각 전체 교체(기존 방식)와 달리 단어가 보존된다.
- 숫자 판독은 파인튜닝 v1(korean_PP-OCRv5_rec_ft.onnx) 이 담당한다.
"""
import os, sys, csv, re, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import dateparse, ocr

_DIGITS_SEP_RE = re.compile(r"[0-9OoIl|.\-/:,\s]+")

def _complete(text):
    return [c for c in dateparse.find_candidates(text) if None not in (c.y, c.m, c.d)]

def merge_digits(K: str, C: str) -> str:
    """K(한국어 결과)에 C(파인튜닝 결과)의 완전한 날짜만 이식한다."""
    cc = _complete(C)
    if not cc:
        return K
    d = max(cc, key=lambda c: len(c.text))
    if any((c.y, c.m, c.d) == (d.y, d.m, d.d) for c in _complete(K)):
        return K
    best = None
    for m in _DIGITS_SEP_RE.finditer(K):
        s, e = m.span()
        while s < e and K[s].isspace():
            s += 1
        while e > s and K[e - 1].isspace():
            e -= 1
        if sum(ch.isdigit() for ch in K[s:e]) >= 4 and (best is None or (e - s) > (best[1] - best[0])):
            best = (s, e)
    if best is None:
        return d.text + " " + K
    return K[:best[0]] + d.text + K[best[1]:]

def hybrid_rec(items: list) -> list:
    if not items:
        return []
    crops = [c for c, _ in items]
    res = list(ocr._rec("ko")(crops)[0])
    redo = [i for i, (t, _) in enumerate(res)
            if sum(ch.isdigit() for ch in t) >= 3 or dateparse.find_candidates(t)]
    if redo:
        ft = ocr._rec("ft")([crops[i] for i in redo])[0]
        for i, (t, _) in zip(redo, ft):
            res[i] = (merge_digits(res[i][0], t), res[i][1])
    return [(t, box) for (t, conf), (_, box) in zip(res, items) if conf >= ocr._MIN_CONF]

ocr._REC_FILES["ft"] = "korean_PP-OCRv5_rec_ft.onnx"
ocr.hybrid_rec = hybrid_rec          # 파이프라인 전 단계가 이 함수를 통해 읽는다
from pipeline import predict_one, list_images
ids = {l.strip() for l in open("labels/gold_ids.txt", encoding="utf-8") if l.strip()}
out = "labels/auto_gold_v5_ftmerge.csv"
done = set()
if os.path.exists(out):
    done = {r["image_id"] for r in csv.DictReader(open(out, encoding="utf-8"))}
paths = [p for p in list_images("../images") if os.path.splitext(os.path.basename(p))[0] in ids
         and os.path.splitext(os.path.basename(p))[0] not in done]
t0 = time.time()
with open(out, "a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    if not done:
        w.writerow(["image_id", "year", "month", "day", "final_date", "stage", "texts", "raw"])
    for i, p in enumerate(paths, 1):
        r = predict_one(p, strict=False, retry_upscale=True)
        w.writerow([r["image_id"], r["year"], r["month"], r["day"], r["final_date"], r["stage"],
                    " | ".join(r["texts"]), r["raw"]])
        f.flush()
        if i % 50 == 0:
            print(f"{i}/{len(paths)} {(time.time()-t0)/i:.2f}s/img", flush=True)
print("DONE", flush=True)
