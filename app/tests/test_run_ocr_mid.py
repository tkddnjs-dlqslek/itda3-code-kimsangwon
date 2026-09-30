# -*- coding: utf-8 -*-
"""run_ocr(mode="mid") 가 read_raw 를 어떤 인자로 부르는지만 확인한다.
predict_one/read_raw 는 무거우니 실제 OCR 은 돌리지 않고 monkeypatch 로 인자만 가로챈다."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import server  # noqa: E402  (임포트 시 src/ 를 sys.path 에 넣어 준다)
import ocr  # noqa: E402


def test_run_ocr_mid_enables_retry_upscale_with_a_deadline(monkeypatch):
    seen = {}

    def fake_read_raw(path, retry_upscale, stage_cap, deadline):
        seen["args"] = (retry_upscale, stage_cap, deadline)
        return [], "erode5"

    monkeypatch.setattr(ocr, "read_raw", fake_read_raw)
    row = server.run_ocr("frame.jpg", "mid")

    retry_upscale, stage_cap, deadline = seen["args"]
    assert retry_upscale is True   # erode5 는 retry_upscale=True 인 블록 안에서만 돈다
    assert deadline is not None    # stage_cap 이름으로는 못 자르니 시간 상한으로 근사한다
    assert row["stage"] == "erode5"


def test_run_ocr_cheap_still_uses_cheap_stage_cap(monkeypatch):
    seen = {}

    def fake_read_raw(path, retry_upscale, stage_cap, deadline):
        seen["args"] = (retry_upscale, stage_cap, deadline)
        return [], "fail"

    monkeypatch.setattr(ocr, "read_raw", fake_read_raw)
    server.run_ocr("frame.jpg", "cheap")

    retry_upscale, stage_cap, _ = seen["args"]
    assert (retry_upscale, stage_cap) == (False, "cheap")
