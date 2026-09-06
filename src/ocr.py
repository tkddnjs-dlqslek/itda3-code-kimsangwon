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

__all__ = ["STAGES", "read", "hybrid_rec"]

STAGES = ("s1", "s2", "rot90", "rot270", "rot180", "clahe", "up2x", "fail")

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


def _det(loose: bool = False):
    return _engine("det_loose", det_box_thresh=0.3) if loose else _engine("det")


def _rec(name: str):
    return _engine(name, rec_model_path=os.path.join(_WEIGHTS, _REC_FILES[name])).text_rec


_REC_FILES = {"ko": "korean_PP-OCRv5_rec_mobile.onnx", "ch": "ch_PP-OCRv3_rec_infer.onnx"}


def _has_complete_date(text: str) -> bool:
    return any(None not in (c.y, c.m, c.d) for c in dateparse.find_candidates(text))


def hybrid_rec(crops: list) -> list[str]:
    """ko 로 전부 읽고, 숫자 3개 이상인데 날짜가 안 되는 조각만 ch 로 다시 읽는다."""
    if not crops:
        return []
    res = list(_rec("ko")(crops)[0])
    redo = [i for i, (t, _) in enumerate(res)
            if sum(c.isdigit() for c in t) >= 3 and not _has_complete_date(t)]
    if redo:
        for i, r in zip(redo, _rec("ch")([crops[i] for i in redo])[0]):
            res[i] = r
    return [t for t, conf in res if conf >= _MIN_CONF]


def _crops(img, loose: bool = False) -> list:
    eng = _det(loose)
    boxes, _ = eng.text_det(img)
    if boxes is None or len(boxes) < 1:
        return []
    # 읽는 순서(위->아래, 왼->오른쪽)로 맞춘다. extract_date 가 앞 조각의 키워드를 본다.
    return list(eng.get_crop_img_list(img, eng.sorted_boxes(boxes)))


def _load(path: str):
    # cv2.imread 는 윈도우 비ASCII 경로에서 None 을 준다. imdecode 로 우회.
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(path)
    scale = _MAX_SIDE / max(img.shape[:2])
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return img


def read(path: str, retry_upscale: bool = False) -> tuple[list[str], str]:
    """(texts, stage) 반환. stage 는 날짜 후보를 만들어낸 단계, 못 찾으면 'fail'."""
    img = _load(path)
    crops = _crops(img)
    big = [c for c in crops if c.shape[0] >= 20 and c.shape[1] / c.shape[0] <= 12]
    small = [c for c in crops if not (c.shape[0] >= 20 and c.shape[1] / c.shape[0] <= 12)]

    texts = hybrid_rec(big)
    if dateparse.extract_date(texts):
        return texts, "s1"
    texts = texts + hybrid_rec(small)
    if dateparse.extract_date(texts):
        return texts, "s2"

    for code, stage in ((cv2.ROTATE_90_CLOCKWISE, "rot90"),
                        (cv2.ROTATE_90_COUNTERCLOCKWISE, "rot270"),
                        (cv2.ROTATE_180, "rot180")):
        rot = hybrid_rec(_crops(cv2.rotate(img, code)))
        if dateparse.extract_date(rot):
            return rot, stage
        texts += rot

    if retry_upscale:
        # 금속면, 저대비 인쇄: 대비 강화만으로 잡히는 경우 (확대는 오히려 방해)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        eq = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
        cl = hybrid_rec(_crops(cv2.cvtColor(eq, cv2.COLOR_GRAY2BGR), loose=True))
        if dateparse.extract_date(cl):
            return cl, "clahe"
        texts += cl
        # 작은 글씨: 2배 확대
        up = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        big2x = hybrid_rec(_crops(up, loose=True))
        if dateparse.extract_date(big2x):
            return big2x, "up2x"
        texts += big2x

    return texts, "fail"
