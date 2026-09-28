# -*- coding: utf-8 -*-
"""입고 검수 서버. 브라우저가 보낸 프레임 한 장을 기존 OCR 파이프라인으로 판독하고 신뢰도를 붙인다.

실행 (저장소 루트에서):
    python -m uvicorn server:create_app --factory --app-dir app --port 8000
"""
from __future__ import annotations

import datetime
import os
import sys
import tempfile
import threading
import time

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import confidence  # noqa: E402
import products  # noqa: E402
import store  # noqa: E402

DB_PATH = os.path.join(HERE, ".data", "items.db")
STATIC = os.path.join(HERE, "static")
MAX_SECONDS = 8.0            # 장당 상한. 단계 사이에서만 확인하므로 실제로는 한 단계 길이만큼 넘을 수 있다
_ocr_lock = threading.Lock()     # predict_one 은 전역 상태를 쓰고 CPU 를 다 쓰므로 한 번에 하나만
_db_lock = threading.Lock()


def run_ocr(path: str, mode: str = "full") -> dict:
    """mode="full": 채점 노트북과 같은 전체 재시도 (장당 상한 8초).
    mode="cheap": 스캐너 직후 1차 촬영용. s1, s2, det5 까지만 보고 날짜가 없으면 바로 NONE 을 돌려준다.
    회전, 침식, 확대는 "날짜가 화면에 있는데 안 읽힐 때" 쓰는 단계라, 날짜 면이 아예 안 보이는 1차 사진에
    돌리면 8초를 낭비한 뒤에야 "날짜 면을 보여 주세요"를 띄우게 된다 (09-28). src/ 는 그대로 두고 앱에서 조합한다."""
    import pipeline              # 무거운 임포트는 첫 판독까지 미룬다. 테스트는 이 함수를 바꿔 끼운다
    with _ocr_lock:
        if mode != "cheap":
            return pipeline.predict_one(path, strict=False, retry_upscale=True, max_seconds=MAX_SECONDS)
        import ocr
        from dateparse import extract_date
        items, stage = ocr.read_raw(path, False, "cheap", time.monotonic() + MAX_SECONDS)
        lines_geo = ocr.group_lines_geo(items)
        texts = [t for t, _, _ in lines_geo]
        found = extract_date(texts, [(cy, h) for _, cy, h in lines_geo])
        y, m, d = found or ("NONE", "NONE", "NONE")
        return {"image_id": os.path.splitext(os.path.basename(path))[0], "year": y, "month": m, "day": d,
                "final_date": f"{y}-{m}-{d}" if found else "NONE", "stage": stage, "texts": texts, "raw": "[]"}


class ItemIn(BaseModel):
    barcode: str = ""
    product_name: str = ""
    year: str = Field(pattern=r"^(\d{4}|NONE)$")
    month: str = Field(pattern=r"^(\d{2}|NONE)$")
    day: str = Field(pattern=r"^(\d{2}|NONE)$")
    confidence: float | None = None
    needs_review: bool = False
    edited: bool = False
    second_shot: bool = False    # 1차 촬영에 날짜가 없어 날짜 면을 다시 대고 찍은 건
    stage: str = ""
    evidence: list[str] = []
    mode: str = Field(default="scan", pattern=r"^(scan|manual)$")
    seconds: float | None = None


def create_app(db_path: str = DB_PATH) -> FastAPI:
    if os.path.dirname(db_path):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = store.connect(db_path)
    table = confidence.load_table()
    catalog = products.load()
    app = FastAPI(title="소비기한 입고 검수")

    @app.post("/api/scan")
    def scan(image: UploadFile = File(...), barcode: str = Form(""), shot: str = Form("full")):
        """shot: "first" = 스캐너 직후 1차 촬영(싼 모드), "second" = 날짜 면 재촬영, "full" = 그 외 (전체 재시도)."""
        t0 = time.time()
        suffix = os.path.splitext(image.filename or "")[1] or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(image.file.read())
            tmp = f.name
        try:
            row = run_ocr(tmp, "cheap" if shot == "first" else "full")
        finally:
            os.unlink(tmp)
        verdict = confidence.assess(row["texts"], row["stage"], row["year"], row["month"], row["day"], table)
        return {"year": row["year"], "month": row["month"], "day": row["day"], "final_date": row["final_date"],
                **verdict, "stage": row["stage"], "evidence": row["texts"][:12], "shot": shot,
                "product": products.lookup(barcode, catalog), "elapsed_ms": int((time.time() - t0) * 1000)}

    @app.get("/api/product/{barcode}")
    def product(barcode: str):
        found = products.lookup(barcode, catalog)
        if found is None:
            raise HTTPException(status_code=404, detail="등록되지 않은 바코드")
        return found

    @app.post("/api/items")
    def save(item: ItemIn):
        with _db_lock:
            return {"id": store.add_item(conn, item.model_dump())}

    @app.get("/api/items")
    def items():
        with _db_lock:
            return store.list_items(conn, datetime.date.today())

    @app.get("/api/items.csv", response_class=PlainTextResponse)
    def items_csv():
        with _db_lock:
            csv_text = store.to_csv(conn)
        return PlainTextResponse("﻿" + csv_text, media_type="text/csv; charset=utf-8",
                                  headers={"Content-Disposition": "attachment; filename=items.csv"})

    @app.get("/api/stats")
    def stats():
        with _db_lock:
            return store.stats(conn)

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")   # API 라우트 뒤에 둬야 가로채지 않는다
    return app
