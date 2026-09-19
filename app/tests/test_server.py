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
    monkeypatch.setattr(server, "run_ocr", lambda path: dict(STUB))
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


def test_scan_without_barcode_has_no_product(client):
    r = client.post("/api/scan", files={"image": ("frame.jpg", b"fake", "image/jpeg")})
    assert r.json()["product"] is None


def test_scan_removes_temp_file(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(server, "run_ocr", lambda path: seen.setdefault("path", path) and dict(STUB))
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
