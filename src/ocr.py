# -*- coding: utf-8 -*-
"""이미지 한 장에서 날짜 후보 텍스트를 뽑는 하이브리드 OCR 래퍼.

det 은 rapidocr 번들 모델, rec 은 한국어 v5 를 기본으로 쓰고 숫자 덩어리가
날짜로 안 풀리는 조각만 중국어 v3 로 다시 읽습니다. 단계는 싼 것부터 순서대로
밟고, 날짜가 잡히는 순간 멈춰요.
"""
from __future__ import annotations

import os
import re

import cv2
import numpy as np

import dateparse

__all__ = ["STAGES", "read", "read_raw", "hybrid_rec", "group_lines", "group_lines_geo"]

STAGES = ("s1", "s2", "det5", "rot90", "rot270", "rot180", "clahe", "hires", "up2x",
          "erode5", "erode3", "fail")

# 벤치용 플래그: 침식/두줄 분리 단계를 끄고 gold 1,000장에서 효과를 분리 측정할 때 False 로 바꾼다
USE_ERODE = True
SPLIT_LINES = True

# 채점 서버는 repo 루트에서 노트북을 돌린다. cwd 가 아니라 이 파일 기준으로 찾는다.
_WEIGHTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "weights")
_THREADS = dict(intra_op_num_threads=4, inter_op_num_threads=1)
_MAX_SIDE = 960
_MIN_CONF = 0.5  # rapidocr 기본 text_score
_ENGINES: dict = {}


def _engine(key: str, **kwargs):
    if key not in _ENGINES:
        from rapidocr_onnxruntime import RapidOCR  # 임포트가 느려서 첫 호출까지 미룬다

        _ENGINES[key] = RapidOCR(**_THREADS, **kwargs)
    return _ENGINES[key]


DET_FILE: str | None = None   # None = rapidocr 동봉 det. 벤치에서 교체 가능


_DET5_FILE = "ch_PP-OCRv5_det_mobile.onnx"   # 재시도용 v5 det: 도트 프린팅 검출이 v4보다 좋음 (09-08 벤치)

# 재시도 단계(det5 부터: det5/rot90/rot270/rot180/clahe/hires/up2x/erode5/erode3, _split_rec 내부 포함)
# 에서 쓰는 파인튜닝 rec. 어려운 사진에서 base 보다 강함 (골드 1,000장: exact 892 -> 901, 09-12 벤치).
# None 이면 기존처럼 s1/s2/재시도 모두 base 모델을 쓴다.
RETRY_REC: str | None = "korean_PP-OCRv5_rec_ft_v2.onnx"
_retry_key_cache: dict = {}


def _retry_key() -> str:
    """재시도 단계에서 쓸 ko rec 엔진 키. RETRY_REC 가중치가 없으면 경고를 찍고 base 로 폴백."""
    rr = RETRY_REC
    if rr not in _retry_key_cache:
        if rr is not None and os.path.exists(os.path.join(_WEIGHTS, rr)):
            _REC_FILES["ko_retry"] = rr
            _retry_key_cache[rr] = "ko_retry"
        else:
            if rr is not None:
                print(f"[ocr] WARNING: retry rec 가중치를 찾을 수 없습니다 ({rr}). base 모델로 폴백합니다.")
            _retry_key_cache[rr] = "ko"
    return _retry_key_cache[rr]


def _det(loose: bool = False, v5: bool = False):
    if v5:
        return _engine("det5", det_model_path=os.path.join(_WEIGHTS, _DET5_FILE))
    kw = {"det_model_path": os.path.join(_WEIGHTS, DET_FILE)} if DET_FILE else {}
    if loose:
        return _engine("det_loose", det_box_thresh=0.3, **kw)
    return _engine("det", **kw)


def _rec(name: str):
    return _engine(name, rec_model_path=os.path.join(_WEIGHTS, _REC_FILES[name])).text_rec


_REC_FILES = {"ko": "korean_PP-OCRv5_rec_mobile.onnx", "ch": "ch_PP-OCRv3_rec_infer.onnx"}


def _has_complete_date(text: str) -> bool:
    return any(None not in (c.y, c.m, c.d) for c in dateparse.find_candidates(text))


def hybrid_rec(items: list, retry: bool = False) -> list:
    """items = [(crop, box)]. ko(또는 retry=True 면 RETRY_REC)로 전부 읽고, 숫자 3개 이상인데
    날짜가 안 되는 조각만 ch 로 다시 읽는다. 반환 [(text, box)] (conf 기준 통과분)."""
    if not items:
        return []
    crops = [c for c, _ in items]
    ko_key = _retry_key() if retry else "ko"
    res = list(_rec(ko_key)(crops)[0])
    # 숫자 조각은 ch 로도 읽는다. ko 는 한글에 강하지만 숫자 한 자리를 자신 있게 틀리는 일이 잦다
    # (골드 1,000장: ko 우선 738 vs ch 우선 749, 09-09 bench_policy). ch 가 완전 날짜를 내면 ch 채택.
    redo = [i for i, (t, _) in enumerate(res)
            if sum(c.isdigit() for c in t) >= 3 or dateparse.find_candidates(t)]
    if redo:
        for i, (t, conf) in zip(redo, _rec("ch")([crops[i] for i in redo])[0]):
            if _has_complete_date(t) or not _has_complete_date(res[i][0]):
                res[i] = (t, conf)
    return [(t, box) for (t, conf), (_, box) in zip(res, items) if conf >= _MIN_CONF]


def _geom(box):
    """(cy, h, cx). 축 정렬 근사. 기록용."""
    b = np.asarray(box, dtype=float)
    return float(b[:, 1].mean()), float(b[:, 1].max() - b[:, 1].min()), float(b[:, 0].min())


def _tilt(boxes) -> float:
    """라벨 전체 기울기(라디안). 가로로 긴 박스들의 윗변 각도 중앙값."""
    angs = []
    for b in boxes:
        b = np.asarray(b, dtype=float)
        w, h = np.linalg.norm(b[1] - b[0]), np.linalg.norm(b[3] - b[0])
        if w > 1.5 * h:
            angs.append(np.arctan2(b[1][1] - b[0][1], b[1][0] - b[0][0]))
    return float(np.median(angs)) if angs else 0.0


def _group_rows(rows: list) -> list:
    """rows = [(text, cy, h, cx)] (이미 일관된 좌표계). 세로 위치가 같은 조각을 한 줄로 묶어
    [(합친 문자열, cy 평균, h 평균)] 반환. group_lines 와 rescore 스크립트가 공유하는 클러스터링 본체."""
    rows = sorted(rows, key=lambda r: r[1])
    lines: list[list] = []          # 각 줄: [cy_sum, h_sum, n, [(cx, text)]]
    for t, cy, h, cx in rows:
        if lines:
            L = lines[-1]
            lcy, lh = L[0] / L[2], L[1] / L[2]
            if abs(cy - lcy) <= 0.5 * max(h, lh):
                L[0] += cy; L[1] += h; L[2] += 1; L[3].append((cx, t))
                continue
        lines.append([cy, h, 1, [(cx, t)]])
    return [(" ".join(t for _, t in sorted(L[3])), L[0] / L[2], L[1] / L[2]) for L in lines]


def group_lines_geo(items: list) -> list:
    """group_lines 와 같은 묶음이지만 줄마다 (cy, h) 도 함께 반환: [(text, cy, h)].
    라벨 기울기를 보정한 좌표계에서 묶는다."""
    if not items:
        return []
    a = _tilt([b for _, b in items])
    ca, sa = np.cos(-a), np.sin(-a)
    rows = []
    for t, b in items:
        b = np.asarray(b, dtype=float)
        c = b.mean(axis=0)
        cx, cy = c[0] * ca - c[1] * sa, c[0] * sa + c[1] * ca      # 기울기 보정 회전
        h = float(np.linalg.norm(b[3] - b[0]))                       # 실제 글자 높이
        rows.append((t, cy, h, cx))
    return _group_rows(rows)


def group_lines(items: list) -> list[str]:
    """[(text, box)] 를 같은 줄끼리 묶어 문자열 리스트로. 라벨 기울기를 보정한 좌표계에서
    세로 위치가 같은 조각을 한 줄로 본다. '부터/까지'가 엉뚱한 날짜 옆에 놓이는 문제를 좌표로 푼다."""
    return [t for t, _, _ in group_lines_geo(items)]


def _crops(img, loose: bool = False, v5: bool = False) -> list:
    eng = _det(loose, v5)
    boxes, _ = eng.text_det(img)
    if boxes is None or len(boxes) < 1:
        return []
    boxes = eng.sorted_boxes(boxes)
    return list(zip(eng.get_crop_img_list(img, boxes), boxes))


def _load(path: str, side: int = _MAX_SIDE):
    """긴 변이 side 가 되도록 축소 (작은 이미지는 그대로). 잘라내지 않는다."""
    # cv2.imread 는 윈도우 비ASCII 경로에서 None 을 준다. imdecode 로 우회.
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(path)
    scale = side / max(img.shape[:2])
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return img


def _clahe(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray), cv2.COLOR_GRAY2BGR)


def _ok(items) -> bool:
    return dateparse.extract_date(group_lines(items)) is not None


_TIME = re.compile(r"(?<!\d)\d{1,2}\s*[:：]\s*\d{2}(?!\d)")


def _features(text: str) -> set:
    """두 줄 자르기 채택 판정: 날짜 후보, 키워드, 시각이 보이는지."""
    f = set()
    if dateparse.find_candidates(text):
        f.add("date")
    if dateparse.EXPIRY.search(text) or dateparse.MFG.search(text):
        f.add("kw")
    if _TIME.search(text):
        f.add("time")
    return f


def _seam(dark, lo: int, hi: int, pen: float = 0.5):
    """[lo, hi) 행 안에서 어두운 픽셀을 가장 적게 지나는 좌에서 우 경로. 열마다 위아래 한 칸까지, 이동마다 pen 벌점."""
    h, w = dark.shape
    cost = np.full((h, w), np.inf)
    cost[lo:hi, 0] = dark[lo:hi, 0]
    back = np.zeros((h, w), dtype=int)
    rows = np.arange(h)
    for c in range(1, w):
        p = cost[:, c - 1]
        cand = np.stack([np.r_[np.inf, p[:-1]] + pen, p, np.r_[p[1:], np.inf] + pen])
        cost[lo:hi, c] = cand.min(0)[lo:hi] + dark[lo:hi, c]
        back[:, c] = rows + cand.argmin(0) - 1
    path = np.empty(w, dtype=int)
    path[-1] = lo + int(cost[lo:hi, -1].argmin())
    for c in range(w - 1, 0, -1):
        path[c - 1] = back[path[c], c]
    return path


def _split2(crop, box):
    """붙어버린 두 줄 조각을 흰 틈을 따라 위아래로 나눈다. [(top, box), (bottom, box)]"""
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    h = g.shape[0]
    path = _seam((g < 128).astype(float), h // 4, 3 * h // 4)
    light = crop[g >= 128]
    bg = np.median(light, axis=0).astype(np.uint8) if len(light) else np.array([255, 255, 255], np.uint8)
    rows = np.arange(h)[:, None]
    top, bot = crop.copy(), crop.copy()
    top[rows > path[None, :]] = bg
    bot[rows < path[None, :]] = bg
    b = np.asarray(box, dtype=np.float32)          # tl, tr, br, bl
    t1, t0 = (path.max() + 1) / h, path.min() / h
    top_box = np.array([b[0], b[1], b[1] + (b[2] - b[1]) * t1, b[0] + (b[3] - b[0]) * t1], np.float32)
    bot_box = np.array([b[0] + (b[3] - b[0]) * t0, b[1] + (b[2] - b[1]) * t0, b[2], b[3]], np.float32)
    return [(top[: path.max() + 1], top_box), (bot[path.min():], bot_box)]


def _split_rec(items: list, retry: bool = False) -> list:
    """침식 단계용 hybrid_rec. 박스 높이 중앙값의 1.5배 이상인 조각은 둘로 잘라 읽고,
    자르기 전에 없던 날짜 후보, 키워드, 시각이 새로 보일 때만 잘린 결과를 쓴다."""
    if not items or not SPLIT_LINES:
        return hybrid_rec(items, retry=retry)
    med = float(np.median([c.shape[0] for c, _ in items]))
    tall = {i for i, (c, _) in enumerate(items) if c.shape[0] >= 1.5 * med}
    out = hybrid_rec([it for i, it in enumerate(items) if i not in tall], retry=retry)
    for i in sorted(tall):
        whole = hybrid_rec([items[i]], retry=retry)
        halves = hybrid_rec(_split2(*items[i]), retry=retry)
        before = _features(" ".join(t for t, _ in whole))
        after = set().union(*[_features(t) for t, _ in halves]) if halves else set()
        out += halves if after - before else whole
    return out


def read_raw(path: str, retry_upscale: bool = False, stage_cap: str = "full") -> tuple[list, str]:
    """([(text, box)], stage) 반환. stage 는 날짜 후보를 만들어낸 단계, 못 찾으면 'fail'.

    stage_cap: 시간 예산이 빠듯할 때 얼마나 깊이 시도할지 제한한다 (pipeline.set_budget 용).
    "s1" = s1 조각만, "cheap" = s1/s2/det5 까지만 (회전·재시도 생략), "full" = 기존 동작 그대로."""
    img = _load(path)
    items = _crops(img)
    keep = lambda c: c.shape[0] >= 20 and c.shape[1] / c.shape[0] <= 12
    big = [it for it in items if keep(it[0])]
    small = [it for it in items if not keep(it[0])]

    out = hybrid_rec(big)
    if _ok(out):
        return out, "s1"
    if stage_cap == "s1":
        return out, "fail"
    out = out + hybrid_rec(small)
    if _ok(out):
        return out, "s2"

    # v5 det 로 다시 검출: v4 가 놓치는 도트 프린팅, 저대비 글자
    # 여기서부터 재시도 단계 (det5 ~ erode3): RETRY_REC 파인튜닝 모델을 쓴다
    d5 = hybrid_rec(_crops(img, v5=True), retry=True)
    if _ok(d5):
        return d5, "det5"
    out += d5
    if stage_cap == "cheap":
        return out, "fail"

    for code, stage in ((cv2.ROTATE_90_CLOCKWISE, "rot90"),
                        (cv2.ROTATE_90_COUNTERCLOCKWISE, "rot270"),
                        (cv2.ROTATE_180, "rot180")):
        rot = hybrid_rec(_crops(cv2.rotate(img, code)), retry=True)
        if _ok(rot):
            return rot, stage
        out += rot

    if retry_upscale:
        # 금속면, 저대비 인쇄: 대비 강화만으로 잡히는 경우 (확대는 오히려 방해)
        cl = hybrid_rec(_crops(_clahe(img), loose=True), retry=True)
        if _ok(cl):
            return cl, "clahe"
        out += cl
        # 원본 해상도(긴 변 1920) + 대비 강화: 골드 fail 103장 중 4장 회복 (09-11 bench_hires)
        hi = hybrid_rec(_crops(_clahe(_load(path, 1920)), loose=True), retry=True)
        if _ok(hi):
            return hi, "hires"
        out += hi
        # 작은 글씨: 2배 확대
        up = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        big2x = hybrid_rec(_crops(up, loose=True), retry=True)
        if _ok(big2x):
            return big2x, "up2x"
        out += big2x
        # 도트 프린팅: 점 사이가 벌어져 det 가 글자로 못 봄. 침식으로 점을 키워 다시 검출 (09-11 골드 fail 103장 중 31장 회복)
        # 침식으로 날짜 줄과 시각 줄이 붙으면 _split_rec 이 흰 틈을 따라 나눠 읽는다
        if USE_ERODE:
            for k in (5, 3):
                er = _split_rec(_crops(cv2.erode(img, np.ones((k, k), np.uint8)), loose=True), retry=True)
                if _ok(er):
                    return er, f"erode{k}"
                out += er

    return out, "fail"


def read(path: str, retry_upscale: bool = False) -> tuple[list[str], str]:
    """(줄 문자열 리스트, stage). 같은 줄 조각은 공백으로 이어 붙인다."""
    items, stage = read_raw(path, retry_upscale)
    return group_lines(items), stage
