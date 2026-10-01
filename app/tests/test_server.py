# -*- coding: utf-8 -*-
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import server

STUB = {"image_id": "frame", "year": "2026", "month": "09", "day": "25", "final_date": "2026-09-25",
        "stage": "s1", "texts": ["소비기한 2026.09.25 까지", "LOT 543123"], "raw": "[]"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "run_ocr", lambda path, mode="full": dict(STUB))
    return TestClient(server.create_app(str(tmp_path / "items.db")))


def test_scan_returns_date_confidence_and_product(client):
    r = client.post("/api/scan", files={"image": ("frame.jpg", b"fake", "image/jpeg")},
                    data={"barcode": "8800000000011"})
    assert r.status_code == 200
    body = r.json()
    assert body["final_date"] == "2026-09-25" and body["stage"] == "s1"
    assert body["bucket"] == "first|full|kw|clear"
    assert 0.0 < body["confidence"] <= 1.0 and isinstance(body["needs_review"], bool)
    assert body["evidence"] == STUB["texts"]
    assert body["product"]["name"] == "시연용 우유 900ml"
    assert body["elapsed_ms"] >= 0


def test_scan_first_shot_uses_cheap_mode(client, monkeypatch):
    seen = {}

    def fake(path, mode="full"):
        seen["mode"] = mode
        return dict(STUB, year="NONE", month="NONE", day="NONE", final_date="NONE", stage="fail", texts=[])

    monkeypatch.setattr(server, "run_ocr", fake)
    r = client.post("/api/scan", files={"image": ("frame.jpg", b"fake", "image/jpeg")}, data={"shot": "first"})
    assert seen["mode"] == "cheap" and r.json()["final_date"] == "NONE" and r.json()["shot"] == "first"
    client.post("/api/scan", files={"image": ("frame.jpg", b"fake", "image/jpeg")}, data={"shot": "mid"})
    assert seen["mode"] == "mid"
    client.post("/api/scan", files={"image": ("frame.jpg", b"fake", "image/jpeg")}, data={"shot": "second"})
    assert seen["mode"] == "full"


def test_scan_without_barcode_has_no_product(client):
    r = client.post("/api/scan", files={"image": ("frame.jpg", b"fake", "image/jpeg")})
    assert r.json()["product"] is None


def test_scan_removes_temp_file(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(server, "run_ocr", lambda path, mode="full": seen.setdefault("path", path) and dict(STUB))
    client.post("/api/scan", files={"image": ("frame.jpg", b"fake", "image/jpeg")})
    assert not os.path.exists(seen["path"])


def test_save_then_list_and_csv_and_stats(client):
    item = {"barcode": "8800000000011", "product_name": "시연용 우유 900ml", "year": "2026", "month": "09",
            "day": "25", "confidence": 0.97, "needs_review": False, "edited": False, "stage": "s1",
            "evidence": ["소비기한 2026.09.25 까지"], "mode": "scan", "seconds": 4.5}
    assert client.post("/api/items", json=item).json() == {"id": 1}
    rows = client.get("/api/items").json()
    assert rows[0]["final_date"] == "2026-09-25" and rows[0]["status"] in {"expired", "imminent", "ok"}
    csv_resp = client.get("/api/items.csv")
    assert csv_resp.text.startswith("﻿")
    assert csv_resp.headers["content-disposition"] == "attachment; filename=items.csv"
    assert "시연용 우유 900ml" in csv_resp.text
    assert client.get("/api/stats").json()["modes"]["scan"] == {"n": 1, "avg_seconds": 4.5}


def test_save_rejects_malformed_date_parts(client):
    bad = {"year": "2026", "month": "9", "day": "25"}          # month 는 2자리여야 함
    assert client.post("/api/items", json=bad).status_code == 422
    assert client.post("/api/items", json={"year": "NONE", "month": "NONE", "day": "NONE"}).status_code == 200


def test_product_endpoint(client):
    assert client.get("/api/product/8800000000028").json()["name"] == "시연용 두부 300g"
    assert client.get("/api/product/1234567890123").status_code == 404


def test_discount_list_and_moved(client):
    import datetime
    soon = datetime.date.today() + datetime.timedelta(days=2)
    item = {"barcode": "8800000000011", "year": str(soon.year), "month": f"{soon.month:02d}", "day": f"{soon.day:02d}"}
    far = dict(item, year=str(soon.year + 1))
    i1 = client.post("/api/items", json=item).json()["id"]
    client.post("/api/items", json=far)
    targets = client.get("/api/items?discount=1").json()
    assert [t["id"] for t in targets] == [i1] and targets[0]["discount_days"] == 5
    assert "discount_targets.csv" in client.get("/api/items.csv?discount=1").headers["content-disposition"]
    assert client.post(f"/api/items/{i1}/moved").json() == {"id": i1, "moved": True}
    assert client.get("/api/items?discount=1").json() == []
    assert client.post("/api/items/999/moved").status_code == 404


def test_verify_allows_when_enough_months(client, monkeypatch):
    monkeypatch.setattr(server, "run_ocr", lambda path, mode="full": dict(STUB, year="2099", month="12", day="31", final_date="2099-12-31"))
    r = client.post("/api/verify", files={"image": ("a.jpg", b"fake", "image/jpeg")},
                    data={"min_months": "6", "product_name": "비타민C"})
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "allow" and body["deadline"] == "2099-12-31"
    assert body["months_left"] >= 6 and body["min_months"] == 6 and body["product_name"] == "비타민C"
    assert body["evidence"] == STUB["texts"] and body["elapsed_ms"] >= 0


def test_verify_blocks_expired(client):
    # STUB 은 2026-09-25. 테스트 실행일이 그 이후이므로 block
    r = client.post("/api/verify", files={"image": ("a.jpg", b"fake", "image/jpeg")})
    assert r.status_code == 200 and r.json()["verdict"] == "block"


def test_verify_defaults_min_months_to_0(client, monkeypatch):
    monkeypatch.setattr(server, "run_ocr", lambda path, mode="full": dict(STUB, year="2099", month="12", day="31", final_date="2099-12-31"))
    r = client.post("/api/verify", files={"image": ("a.jpg", b"fake", "image/jpeg")})
    assert r.json()["min_months"] == 0 and r.json()["verdict"] == "allow"


def test_verify_rejects_bad_min_months(client):
    for bad in ("-1", "61", "abc"):
        r = client.post("/api/verify", files={"image": ("a.jpg", b"fake", "image/jpeg")}, data={"min_months": bad})
        assert r.status_code == 422, bad


def test_verify_none_date_is_review(client, monkeypatch):
    monkeypatch.setattr(server, "run_ocr", lambda path, mode="full": dict(STUB, year="NONE", month="NONE", day="NONE", final_date="NONE", stage="fail", texts=[]))
    r = client.post("/api/verify", files={"image": ("a.jpg", b"fake", "image/jpeg")})
    body = r.json()
    assert body["verdict"] == "review" and body["months_left"] is None


def test_verify_ocr_exception_becomes_review(client, monkeypatch):
    def boom(path, mode="full"):
        raise RuntimeError("cv2.imread failed")
    monkeypatch.setattr(server, "run_ocr", boom)
    r = client.post("/api/verify", files={"image": ("a.txt", b"not an image", "text/plain")})
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "review" and "판독하지 못했습니다" in body["reason"]
    assert body["final_date"] == "NONE" and body["confidence"] is None


def test_verify_uses_listing_mode(client, monkeypatch):
    seen = {}
    def fake(path, mode="full"):
        seen["mode"] = mode
        return dict(STUB)
    monkeypatch.setattr(server, "run_ocr", fake)
    client.post("/api/verify", files={"image": ("a.jpg", b"fake", "image/jpeg")})
    assert seen["mode"] == "listing"


def _photos(n, name="a.jpg"):
    return [("images", (f"{name[:-4]}{i}.jpg", b"fake", "image/jpeg")) for i in range(n)]


def test_verify_listing_allows_with_two_good_photos(client, monkeypatch):
    monkeypatch.setattr(server, "run_ocr", lambda path, mode="full": dict(STUB, year="2099", month="12", day="31", final_date="2099-12-31"))
    r = client.post("/api/verify_listing", files=_photos(2), data={"product_name": "비타민C"})
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "allow" and body["min_months"] == 6 and body["product_name"] == "비타민C"
    assert len(body["photos"]) == 2 and body["min_photo"] in (0, 1)


def test_verify_listing_blocks_on_shortest_photo(client, monkeypatch):
    calls = []

    def fake(path, mode="full"):
        calls.append(path)
        if len(calls) == 1:
            return dict(STUB)   # 2026-09-25, 오늘(테스트 실행일) 기준 이미 지남
        return dict(STUB, year="2099", month="12", day="31", final_date="2099-12-31")

    monkeypatch.setattr(server, "run_ocr", fake)
    r = client.post("/api/verify_listing", files=_photos(2))
    body = r.json()
    assert body["verdict"] == "block" and body["min_photo"] == 0
    assert "6개월" in body["reason"]
    assert len(calls) == 2


def test_verify_listing_review_when_all_none(client, monkeypatch):
    monkeypatch.setattr(server, "run_ocr", lambda path, mode="full": dict(STUB, year="NONE", month="NONE", day="NONE", final_date="NONE", stage="fail", texts=[]))
    r = client.post("/api/verify_listing", files=_photos(3))
    body = r.json()
    assert body["verdict"] == "review" and body["min_photo"] is None
    assert "사진을 추가" in body["reason"]


def test_verify_listing_rejects_more_than_five(client):
    r = client.post("/api/verify_listing", files=_photos(6))
    assert r.status_code == 422


def test_verify_listing_full_pass_only_for_none_photos(client, monkeypatch):
    calls = []
    cheap_n = {"n": 0}

    def fake(path, mode="full"):
        calls.append((os.path.basename(path), mode))
        if mode == "cheap":
            i = cheap_n["n"]
            cheap_n["n"] += 1
            if i == 0:
                return dict(STUB, year="2099", month="12", day="31", final_date="2099-12-31")
            return dict(STUB, year="NONE", month="NONE", day="NONE", final_date="NONE", stage="fail", texts=[])
        return dict(STUB, year="2030", month="05", day="10", final_date="2030-05-10")

    monkeypatch.setattr(server, "run_ocr", fake)
    r = client.post("/api/verify_listing", files=_photos(2))
    body = r.json()
    assert sum(1 for _, mode in calls if mode == "listing") == 1
    assert body["passes"] == 2
    assert body["photos"][0]["final_date"] == "2099-12-31" and body["photos"][0]["mode"] == "cheap"
    assert body["photos"][1]["final_date"] == "2030-05-10" and body["photos"][1]["mode"] == "listing"


def test_verify_listing_block_in_cheap_pass_skips_full(client, monkeypatch):
    calls = []

    def fake(path, mode="full"):
        calls.append(mode)
        return dict(STUB)   # 2026-09-25, cheap 모드에서도 이미 지난 날짜

    monkeypatch.setattr(server, "run_ocr", fake)
    r = client.post("/api/verify_listing", files=_photos(1))
    body = r.json()
    assert "full" not in calls
    assert body["verdict"] == "block" and body["passes"] == 1


def test_verify_listing_all_none_tries_full_then_reviews(client, monkeypatch):
    calls = []

    def fake(path, mode="full"):
        calls.append(mode)
        return dict(STUB, year="NONE", month="NONE", day="NONE", final_date="NONE", stage="fail", texts=[])

    monkeypatch.setattr(server, "run_ocr", fake)
    r = client.post("/api/verify_listing", files=_photos(2))
    body = r.json()
    assert calls.count("listing") == 2
    assert body["verdict"] == "review" and body["passes"] == 2


def test_scan_vs_verify_threshold_difference(client, monkeypatch):
    """scan은 0.90, verify는 0.80 임계값을 사용해야 함.
    retry|full|nokw|clear 버킷값이 0.8133인 경우:
    - scan은 0.8133 < 0.90 → needs_review=True
    - verify는 0.8133 >= 0.80 → needs_review=False
    """
    stub_retry = dict(STUB, stage="erode5", year="2099", month="12", day="31", final_date="2099-12-31", texts=["2099.12.31"])

    def fake(path, mode="full"):
        return stub_retry

    monkeypatch.setattr(server, "run_ocr", fake)

    # scan: 기본값 0.90 사용, bucket retry|full|nokw|clear에서 needs_review 판정 차이 확인
    r_scan = client.post("/api/scan", files={"image": ("frame.jpg", b"fake", "image/jpeg")})
    scan_body = r_scan.json()
    # 테이블의 retry|full|nokw|clear 값이 0.8133이면 0.90 미만이므로 needs_review=True
    assert scan_body["bucket"] == "retry|full|nokw|clear"

    # verify: 0.80 사용, 같은 bucket에서 verdict="allow"
    r_verify = client.post("/api/verify", files={"image": ("a.jpg", b"fake", "image/jpeg")})
    verify_body = r_verify.json()
    # 0.80 이상이면 needs_review=False, verdict="allow"
    assert verify_body["verdict"] == "allow"
