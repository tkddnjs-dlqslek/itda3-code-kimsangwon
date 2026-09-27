# -*- coding: utf-8 -*-
"""시간 예산(pipeline.set_budget) 단위 테스트. 가짜 시계만 쓰고 실제 OCR 은 호출하지 않는다."""
import pipeline


def teardown_function(_):
    pipeline.set_budget(None, 0)  # 다른 테스트로 예산 상태가 새지 않도록 항상 해제


def test_no_budget_keeps_default_behaviour():
    pipeline.set_budget(None, 0)
    assert pipeline._decide_stage(False) == (False, "full")
    assert pipeline._decide_stage(True) == (True, "full")


def test_ahead_of_schedule_stays_full(monkeypatch):
    monkeypatch.setattr(pipeline.time, "time", lambda: 1000.0)
    pipeline.set_budget(100.0, 10)  # deadline=1100, 장당 10초 여유
    assert pipeline._decide_stage(True) == (True, "full")


def test_behind_schedule_falls_to_cheap(monkeypatch):
    monkeypatch.setattr(pipeline.time, "time", lambda: 1000.0)
    pipeline.set_budget(20.0, 10)  # deadline=1020, 장당 2초 (FULL_MIN=3 미만, CHEAP_MIN=1 이상)
    assert pipeline._decide_stage(True) == (False, "cheap")


def test_critical_falls_to_s1_only(monkeypatch):
    monkeypatch.setattr(pipeline.time, "time", lambda: 1000.0)
    pipeline.set_budget(5.0, 10)  # 장당 0.5초 (CHEAP_MIN 미만)
    assert pipeline._decide_stage(True) == (False, "s1")


def test_remaining_count_never_goes_negative(monkeypatch):
    monkeypatch.setattr(pipeline.time, "time", lambda: 0.0)
    pipeline.set_budget(10.0, 0)
    assert pipeline._decide_stage(True)[1] in ("full", "cheap", "s1")  # 0으로 나누지 않음


def test_predict_one_uses_budget_and_decrements_remaining(monkeypatch):
    calls = []

    def fake_read_raw(path, retry, stage_cap, deadline=None):
        calls.append((retry, stage_cap))
        return [], "s1"

    monkeypatch.setattr(pipeline.ocr, "read_raw", fake_read_raw)
    t = [0.0]
    monkeypatch.setattr(pipeline.time, "time", lambda: t[0])

    pipeline.set_budget(20.0, 2)  # deadline=20, 장당 10초 -> full
    row = pipeline.predict_one("fake1.jpg", strict=False, retry_upscale=True)
    assert calls[-1] == (True, "full")
    assert row["final_date"] == "NONE"  # 후보 없음, 그래도 행은 씀
    assert list(row) == ["image_id", "year", "month", "day", "final_date", "stage", "texts", "raw"]
    assert pipeline._budget["remaining"] == 1

    t[0] = 18.0  # 남은 2초 / 남은 1장 -> cheap 대역, retry_upscale 요청해도 강제로 False
    pipeline.predict_one("fake2.jpg", strict=False, retry_upscale=True)
    assert calls[-1] == (False, "cheap")
    assert pipeline._budget["remaining"] == 0


def test_predict_one_exception_still_decrements_remaining(monkeypatch):
    def boom(path, retry, stage_cap):
        raise ValueError("stub failure")

    monkeypatch.setattr(pipeline.ocr, "read_raw", boom)
    monkeypatch.setattr(pipeline.time, "time", lambda: 0.0)
    pipeline.set_budget(20.0, 1)
    row = pipeline.predict_one("fake.jpg", strict=False, retry_upscale=False)
    assert row["stage"] == "error" and row["final_date"] == "NONE"
    assert pipeline._budget["remaining"] == 0


def test_read_raw_deadline_stops_between_stages(monkeypatch):
    """장당 상한(deadline)이 지나 있으면 s2 뒤에서 멈추고, 그 뒤 단계(det5 이후)는 호출하지 않는다."""
    import ocr

    calls = []
    monkeypatch.setattr(ocr, "_load", lambda path, side=960: "IMG")
    monkeypatch.setattr(ocr, "_crops", lambda img, loose=False, v5=False: calls.append(("crops", v5)) or [])
    monkeypatch.setattr(ocr, "hybrid_rec", lambda items, retry=False: [])
    monkeypatch.setattr(ocr, "_ok", lambda items: False)
    monkeypatch.setattr(ocr.time, "monotonic", lambda: 100.0)
    items, stage = ocr.read_raw("x.jpg", retry_upscale=True, deadline=99.0)   # 이미 지난 상한
    assert stage == "fail" and items == []
    assert calls == [("crops", False)]                                          # det5 (v5=True) 미호출


def test_read_raw_without_deadline_runs_all_stages(monkeypatch):
    import ocr

    calls = []
    monkeypatch.setattr(ocr, "_load", lambda path, side=960: "IMG")
    monkeypatch.setattr(ocr, "_crops", lambda img, loose=False, v5=False: calls.append(("crops", v5)) or [])
    monkeypatch.setattr(ocr, "_clahe", lambda img: img)
    monkeypatch.setattr(ocr, "_split_rec", lambda items, retry=False: [])
    monkeypatch.setattr(ocr, "hybrid_rec", lambda items, retry=False: [])
    monkeypatch.setattr(ocr, "_ok", lambda items: False)
    monkeypatch.setattr(ocr.cv2, "rotate", lambda img, code: img)
    monkeypatch.setattr(ocr.cv2, "resize", lambda img, dsize, fx=1, fy=1, interpolation=None: img)
    monkeypatch.setattr(ocr.cv2, "erode", lambda img, k: img)
    items, stage = ocr.read_raw("x.jpg", retry_upscale=True)
    assert stage == "fail"
    assert len(calls) == 8                                                      # s1, det5, erode 2, clahe, rot90, hires, up2x


def test_predict_one_passes_deadline(monkeypatch):
    seen = {}

    def fake_read_raw(path, retry, cap, deadline=None):
        seen["deadline"] = deadline
        return [], "fail"

    monkeypatch.setattr(pipeline.ocr, "read_raw", fake_read_raw)
    monkeypatch.setattr(pipeline.time, "monotonic", lambda: 50.0)
    pipeline.predict_one("a.jpg", strict=True, retry_upscale=True, max_seconds=8.0)
    assert seen["deadline"] == 58.0
    pipeline.predict_one("a.jpg", strict=True, retry_upscale=True)
    assert seen["deadline"] is None
