# -*- coding: utf-8 -*-
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import products
import store

TODAY = datetime.date(2026, 9, 19)


def _item(**kw):
    base = dict(barcode="", product_name="", year="2026", month="09", day="25", confidence=0.97,
                needs_review=False, edited=False, stage="s1", evidence=["2026.09.25 까지"],
                mode="scan", seconds=4.2)
    base.update(kw)
    return base


def test_product_lookup_strips_spaces_and_misses_return_none():
    table = products.load()
    assert products.lookup(" 8800000000011 ", table) == {
        "barcode": "8800000000011", "name": "시연용 우유 900ml", "category": "유제품"}
    assert products.lookup("0000000000000", table) is None
    assert products.lookup("", table) is None


def test_final_date_follows_contest_schema():
    assert store.final_date_of("2026", "05", "29") == "2026-05-29"
    assert store.final_date_of("NONE", "08", "25") == "NONE-08-25"
    assert store.final_date_of("NONE", "NONE", "NONE") == "NONE"


def test_status_of():
    assert store.status_of("2026-09-18", TODAY) == (-1, "expired")
    assert store.status_of("2026-09-19", TODAY) == (0, "imminent")
    assert store.status_of("2026-09-22", TODAY) == (3, "imminent")
    assert store.status_of("2026-09-23", TODAY) == (4, "ok")
    assert store.status_of("NONE-08-25", TODAY) == (None, "unknown")
    assert store.status_of("NONE", TODAY) == (None, "unknown")


def test_list_is_sorted_by_expiry_with_incomplete_dates_last():
    conn = store.connect(":memory:")
    store.add_item(conn, _item(product_name="늦음", day="30"))
    store.add_item(conn, _item(product_name="불완전", year="NONE"))
    store.add_item(conn, _item(product_name="지남", day="10"))
    names = [(i["product_name"], i["status"]) for i in store.list_items(conn, TODAY)]
    assert names == [("지남", "expired"), ("늦음", "ok"), ("불완전", "unknown")]


def test_add_item_roundtrips_fields():
    conn = store.connect(":memory:")
    new_id = store.add_item(conn, _item(barcode="8800000000011", product_name="우유", needs_review=True, edited=True))
    row = store.list_items(conn, TODAY)[0]
    assert row["id"] == new_id and row["final_date"] == "2026-09-25"
    assert row["needs_review"] is True and row["edited"] is True
    assert row["evidence"] == ["2026.09.25 까지"] and row["days_left"] == 6


def test_stats_compare_scan_and_manual():
    conn = store.connect(":memory:")
    store.add_item(conn, _item(seconds=4.0, needs_review=True, edited=True))
    store.add_item(conn, _item(seconds=6.0))
    store.add_item(conn, _item(mode="manual", seconds=20.0, confidence=None))
    s = store.stats(conn)
    assert s["modes"] == {"scan": {"n": 2, "avg_seconds": 5.0}, "manual": {"n": 1, "avg_seconds": 20.0}}
    assert s["review_rate"] == 0.5 and s["edit_rate"] == 0.5


def test_stats_on_empty_db():
    assert store.stats(store.connect(":memory:")) == {"modes": {}, "review_rate": None, "edit_rate": None}


def test_csv_has_header_and_rows():
    conn = store.connect(":memory:")
    store.add_item(conn, _item(product_name="우유"))
    lines = store.to_csv(conn).strip().splitlines()
    assert lines[0].startswith("id,created_at,barcode,product_name,final_date")
    assert "우유" in lines[1] and "2026-09-25" in lines[1]
