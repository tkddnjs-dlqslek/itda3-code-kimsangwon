# -*- coding: utf-8 -*-
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import verify

D = datetime.date


def test_months_between_basic():
    assert verify.months_between(D(2026, 10, 1), D(2027, 3, 1)) == 5
    assert verify.months_between(D(2026, 10, 1), D(2027, 4, 1)) == 6
    assert verify.months_between(D(2026, 10, 15), D(2027, 4, 1)) == 5   # 일이 모자라면 1 빼기
    assert verify.months_between(D(2026, 10, 1), D(2026, 9, 1)) == -1


def test_month_end_rounding():
    assert verify.months_between(D(2026, 1, 31), D(2026, 2, 28)) == 0


def test_allow_when_enough_months():
    v = verify.verdict("2027", "06", "01", D(2026, 10, 1), 6, False)
    assert v["verdict"] == "allow" and v["months_left"] == 8 and v["deadline"] == "2027-06-01"


def test_block_when_short():
    v = verify.verdict("2027", "03", "01", D(2026, 10, 1), 6, False)
    assert v["verdict"] == "block" and v["months_left"] == 5
    assert "6개월" in v["reason"]


def test_block_when_expired():
    v = verify.verdict("2026", "09", "30", D(2026, 10, 1), 6, False)
    assert v["verdict"] == "block" and "지났" in v["reason"]


def test_today_is_not_expired():
    v = verify.verdict("2026", "10", "01", D(2026, 10, 1), 0, False)
    assert v["verdict"] == "allow" and v["months_left"] == 0


def test_partial_day_uses_first_of_month():
    v = verify.verdict("2027", "03", "NONE", D(2026, 10, 1), 6, False)
    assert v["deadline"] == "2027-03-01" and v["verdict"] == "block"


def test_review_when_year_or_month_missing():
    assert verify.verdict("NONE", "03", "13", D(2026, 10, 1), 6, False)["verdict"] == "review"
    assert verify.verdict("2027", "NONE", "13", D(2026, 10, 1), 6, False)["verdict"] == "review"
    assert verify.verdict("NONE", "NONE", "NONE", D(2026, 10, 1), 6, False)["months_left"] is None


def test_review_when_low_confidence_even_if_enough():
    v = verify.verdict("2027", "06", "01", D(2026, 10, 1), 6, True)
    assert v["verdict"] == "review" and v["months_left"] == 8 and "신뢰도" in v["reason"]


def photo(index, year="NONE", month="NONE", day="NONE", needs_review=False, confidence=0.95):
    return {"index": index, "year": year, "month": month, "day": day,
            "needs_review": needs_review, "confidence": confidence}


def test_listing_review_when_none_dated():
    results = [photo(0), photo(1)]
    v = verify.listing_verdict(results, D(2026, 10, 1), 6)
    assert v["verdict"] == "review" and v["min_photo"] is None
    assert "사진을 추가" in v["reason"]


def test_listing_allow_when_one_dated_enough():
    results = [photo(0), photo(1, "2027", "06", "01")]
    v = verify.listing_verdict(results, D(2026, 10, 1), 6)
    assert v["verdict"] == "allow" and v["min_photo"] == 1 and v["months_left"] == 8


def test_listing_blocks_on_shortest_deadline():
    results = [photo(0, "2099", "12", "31"), photo(1, "2027", "01", "01")]
    v = verify.listing_verdict(results, D(2026, 10, 1), 6)
    assert v["verdict"] == "block" and v["min_photo"] == 1
    assert "6개월" in v["reason"]
    assert [d["index"] for d in v["dates"]] == [1, 0]


def test_listing_review_when_min_photo_low_confidence():
    results = [photo(0, "2099", "12", "31"), photo(1, "2027", "01", "01", needs_review=True)]
    v = verify.listing_verdict(results, D(2026, 10, 1), 6)
    assert v["verdict"] == "review" and v["min_photo"] == 1 and "신뢰도" in v["reason"]


def test_listing_five_photos_mixed():
    results = [photo(0), photo(1, "2099", "01", "01"), photo(2, "2027", "02", "NONE"),
               photo(3, "2026", "11", "01"), photo(4)]
    v = verify.listing_verdict(results, D(2026, 10, 1), 6)
    assert v["min_photo"] == 3 and v["verdict"] == "block"
    assert sorted(d["index"] for d in v["dates"]) == [1, 2, 3]
