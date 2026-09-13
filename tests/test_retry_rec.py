# -*- coding: utf-8 -*-
"""재시도 단계(det5~erode3) 전용 rec 모델 선택(ocr.RETRY_REC) 단위 테스트.
_rec 을 몽키패치해서 실제 OCR 엔진은 절대 로드하지 않는다."""
import numpy as np
import ocr


def _fake_items():
    box = [[0, 0], [10, 0], [10, 10], [0, 10]]
    return [(np.zeros((10, 10, 3), np.uint8), box)]


def _patch_rec(monkeypatch):
    calls = []

    def fake_rec(name):
        calls.append(name)
        return lambda crops: ([("2026.01.01", 0.9) for _ in crops],)

    monkeypatch.setattr(ocr, "_rec", fake_rec)
    return calls


def test_retry_none_reproduces_old_single_model(monkeypatch):
    monkeypatch.setattr(ocr, "RETRY_REC", None)
    ocr._retry_key_cache.clear()
    calls = _patch_rec(monkeypatch)

    ocr.hybrid_rec(_fake_items(), retry=True)

    assert calls[0] == "ko"  # RETRY_REC=None -> retry=True 여도 기존 base 모델 그대로


def test_retry_true_selects_finetuned_model(monkeypatch):
    monkeypatch.setattr(ocr, "RETRY_REC", "korean_PP-OCRv5_rec_ft_v2.onnx")
    ocr._retry_key_cache.clear()
    calls = _patch_rec(monkeypatch)

    ocr.hybrid_rec(_fake_items(), retry=True)

    assert calls[0] == "ko_retry"
    assert ocr._REC_FILES["ko_retry"] == "korean_PP-OCRv5_rec_ft_v2.onnx"


def test_no_retry_flag_keeps_base_model_regardless(monkeypatch):
    monkeypatch.setattr(ocr, "RETRY_REC", "korean_PP-OCRv5_rec_ft_v2.onnx")
    ocr._retry_key_cache.clear()
    calls = _patch_rec(monkeypatch)

    ocr.hybrid_rec(_fake_items())  # retry 기본값 False -> s1/s2 와 동일한 옛 동작

    assert calls[0] == "ko"
