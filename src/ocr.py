# -*- coding: utf-8 -*-
"""이미지 한 장에서 날짜 후보 텍스트를 뽑는 하이브리드 OCR 래퍼.

det 은 rapidocr 번들 모델, rec 은 한국어 v5 를 기본으로 쓰고 숫자 덩어리가
날짜로 안 풀리는 조각만 중국어 v3 로 다시 읽습니다. 단계는 싼 것부터 순서대로
밟고, 날짜가 잡히는 순간 멈춰요.
"""
from __future__ import annotations

import os

import cv2
import numpy as np

import dateparse

__all__ = ["STAGES", "read", "read_raw", "hybrid_rec", "group_lines"]

STAGES = ("s1", "s2", "det5", "rot90", "rot270", "rot180", "clahe", "up2x", "fail")

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


def hybrid_rec(items: list) -> list:
    """items = [(crop, box)]. ko 로 전부 읽고, 숫자 3개 이상인데 날짜가 안 되는 조각만
    ch 로 다시 읽는다. 반환 [(text, box)] (conf 기준 통과분)."""
    if not items:
        return []
    crops = [c for c, _ in items]
    res = list(_rec("ko")(crops)[0])
    # 숫자 조각은 ch 로도 읽는다. ko 는 한글에 강하지만 숫자 한 자리를 자신 있게 틀리는 일이 잦다
    # (골드 1,000장: ko 우선 738 vs ch 우선 749, 09-09 bench_policy). ch 가 완전 날짜를 내면 ch 채택.
    redo = [i for i, (t, _) in enumerate(res) if sum(c.isdigit() for c in t) >= 3]
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


def group_lines(items: list) -> list[str]:
    """[(text, box)] 를 같은 줄끼리 묶어 문자열 리스트로. 라벨 기울기를 보정한 좌표계에서
    세로 위치가 같은 조각을 한 줄로 본다. '부터/까지'가 엉뚱한 날짜 옆에 놓이는 문제를 좌표로 푼다."""
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
    rows.sort(key=lambda r: r[1])
    lines: list[list] = []          # 각 줄: [cy_sum, h_sum, n, [(cx, text)]]
    for t, cy, h, cx in rows:
        if lines:
            L = lines[-1]
            lcy, lh = L[0] / L[2], L[1] / L[2]
            if abs(cy - lcy) <= 0.5 * max(h, lh):
                L[0] += cy; L[1] += h; L[2] += 1; L[3].append((cx, t))
                continue
        lines.append([cy, h, 1, [(cx, t)]])
    return [" ".join(t for _, t in sorted(L[3])) for L in lines]


def _crops(img, loose: bool = False, v5: bool = False) -> list:
    eng = _det(loose, v5)
    boxes, _ = eng.text_det(img)
    if boxes is None or len(boxes) < 1:
        return []
    boxes = eng.sorted_boxes(boxes)
    return list(zip(eng.get_crop_img_list(img, boxes), boxes))


def _load(path: str):
    # cv2.imread 는 윈도우 비ASCII 경로에서 None 을 준다. imdecode 로 우회.
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(path)
    scale = _MAX_SIDE / max(img.shape[:2])
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return img


def _ok(items) -> bool:
    return dateparse.extract_date(group_lines(items)) is not None


def read_raw(path: str, retry_upscale: bool = False) -> tuple[list, str]:
    """([(text, box)], stage) 반환. stage 는 날짜 후보를 만들어낸 단계, 못 찾으면 'fail'."""
    img = _load(path)
    items = _crops(img)
    keep = lambda c: c.shape[0] >= 20 and c.shape[1] / c.shape[0] <= 12
    big = [it for it in items if keep(it[0])]
    small = [it for it in items if not keep(it[0])]

    out = hybrid_rec(big)
    if _ok(out):
        return out, "s1"
    out = out + hybrid_rec(small)
    if _ok(out):
        return out, "s2"

    # v5 det 로 다시 검출: v4 가 놓치는 도트 프린팅, 저대비 글자
    d5 = hybrid_rec(_crops(img, v5=True))
    if _ok(d5):
        return d5, "det5"
    out += d5

    for code, stage in ((cv2.ROTATE_90_CLOCKWISE, "rot90"),
                        (cv2.ROTATE_90_COUNTERCLOCKWISE, "rot270"),
                        (cv2.ROTATE_180, "rot180")):
        rot = hybrid_rec(_crops(cv2.rotate(img, code)))
        if _ok(rot):
            return rot, stage
        out += rot

    if retry_upscale:
        # 금속면, 저대비 인쇄: 대비 강화만으로 잡히는 경우 (확대는 오히려 방해)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        eq = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
        cl = hybrid_rec(_crops(cv2.cvtColor(eq, cv2.COLOR_GRAY2BGR), loose=True))
        if _ok(cl):
            return cl, "clahe"
        out += cl
        # 작은 글씨: 2배 확대
        up = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        big2x = hybrid_rec(_crops(up, loose=True))
        if _ok(big2x):
            return big2x, "up2x"
        out += big2x

    return out, "fail"


def read(path: str, retry_upscale: bool = False) -> tuple[list[str], str]:
    """(줄 문자열 리스트, stage). 같은 줄 조각은 공백으로 이어 붙인다."""
    items, stage = read_raw(path, retry_upscale)
    return group_lines(items), stage
