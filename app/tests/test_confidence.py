# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import confidence


def test_keyword_full_date_first_stage():
    key = confidence.bucket_key(["소비기한 2026.05.29 까지"], "s1", "2026", "05", "29")
    assert key == "first|full|kw|clear"


def test_bare_date_in_retry_stage_has_no_keyword():
    key = confidence.bucket_key(["2026.05.29"], "erode5", "2026", "05", "29")
    assert key == "retry|full|nokw|clear"


def test_two_equal_candidates_are_contested():
    key = confidence.bucket_key(["2026.05.29", "2027.01.01"], "s2", "2027", "01", "01")
    assert key == "first|full|nokw|contested"


def test_manufacture_date_does_not_contest():
    # 제조 키워드 후보는 점수가 2점 낮아 경쟁 후보로 치지 않는다
    key = confidence.bucket_key(["제조 2025.01.02", "2026.05.29"], "s1", "2026", "05", "29")
    assert key == "first|full|nokw|clear"


def test_partial_and_none_and_fail():
    assert confidence.bucket_key([], "s1", "NONE", "10", "14") == "first|part|nokw|clear"
    assert confidence.bucket_key([], "fail", "NONE", "NONE", "NONE") == "none"
    assert confidence.bucket_key(["2026.05.29"], "fail", "2026", "05", "29") == "fail|full|nokw|clear"


def test_build_table_smooths_and_drops_small_buckets():
    rows = [("a|full|kw|clear", True)] * 20 + [("a|part|nokw|clear", False)] * 5
    table = confidence.build_table(rows)
    assert table["buckets"] == {"a|full|kw|clear": round(21 / 22, 4)}   # 5건짜리는 표본 부족으로 제외
    assert table["groups"] == {"a": round(21 / 27, 4)}
    assert table["global"] == round(21 / 27, 4)


def test_lookup_falls_back_bucket_then_group_then_global():
    table = {"global": 0.5, "groups": {"a": 0.7}, "buckets": {"a|full|kw|clear": 0.95}}
    assert confidence.lookup("a|full|kw|clear", table) == 0.95
    assert confidence.lookup("a|part|nokw|clear", table) == 0.7
    assert confidence.lookup("zzz|full|kw|clear", table) == 0.5


def test_assess_flags_low_confidence_for_review():
    table = {"global": 0.5, "groups": {"first": 0.97, "retry": 0.6}, "buckets": {}}
    hi = confidence.assess(["2026.05.29"], "s1", "2026", "05", "29", table)
    lo = confidence.assess(["2026.05.29"], "clahe", "2026", "05", "29", table)
    assert hi == {"confidence": 0.97, "needs_review": False, "bucket": "first|full|nokw|clear"}
    assert lo["needs_review"] is True and lo["confidence"] == 0.6


def test_needs_review_flags_partial_dates_regardless_of_confidence():
    assert confidence.needs_review("first|part|nokw|clear", 0.96) is True


def test_needs_review_flags_none_bucket():
    assert confidence.needs_review("none", 0.99) is True


def test_needs_review_passes_full_bucket_at_high_confidence():
    assert confidence.needs_review("first|full|kw|clear", 0.97) is False


def test_tool_replays_gold_predictions():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
    import build_confidence_table as tool
    rows = tool.load_rows()
    assert len(rows) == 1000
    assert sum(ok for _, _, ok in rows) == 919
