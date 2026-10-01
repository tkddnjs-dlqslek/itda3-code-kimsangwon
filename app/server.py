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
import verify  # noqa: E402

DB_PATH = os.path.join(HERE, ".data", "items.db")
STATIC = os.path.join(HERE, "static")
MAX_SECONDS = 8.0            # 장당 상한. 단계 사이에서만 확인하므로 실제로는 한 단계 길이만큼 넘을 수 있다
MID_SECONDS = 4.0            # 중간 재시도(mid) 상한. 아래 run_ocr 의 mode="mid" 설명 참고
# 플랫폼 설정값. 식약처 시범사업 초기 기준(2024-05) 6개월, 2025-05 부터 소비기한 내로 완화. 발표와 시연은 6 으로
MIN_MONTHS = 6
_ocr_lock = threading.Lock()     # predict_one 은 전역 상태를 쓰고 CPU 를 다 쓰므로 한 번에 하나만
_db_lock = threading.Lock()


def run_ocr(path: str, mode: str = "full") -> dict:
    """mode="full": 채점 노트북과 같은 전체 재시도 (장당 상한 8초).
    mode="cheap": 스캐너 직후 1차 촬영용. s1, s2, det5 까지만 보고 날짜가 없으면 바로 NONE 을 돌려준다.
    mode="mid": 1차와 전체 사이. det5 까지 보고도 없으면 침식(erode5) 한 번을 더 시도한다.
    회전, 침식, 확대는 "날짜가 화면에 있는데 안 읽힐 때" 쓰는 단계라, 날짜 면이 아예 안 보이는 1차 사진에
    돌리면 8초를 낭비한 뒤에야 "날짜 면을 보여 주세요"를 띄우게 된다 (09-28). src/ 는 그대로 두고 앱에서 조합한다.

    mid 를 위해 src/ocr.py 의 read_raw(stage_cap=...) 를 먼저 확인했다: stage_cap 은 "s1" 과 "cheap" 문자열만
    검사하고 그 외 값은 전부 "full" 과 같은 사다리를 탄다. 즉 이름으로 "erode5 까지만" 을 표현할 방법이 없다.
    게다가 erode5 는 retry_upscale=True 일 때만 도는 블록 안에 있어서, cheap 처럼 retry_upscale=False 로는
    아예 도달하지 못한다. 그래서 retry_upscale=True 로 켜고 read_raw 가 이미 노출하는 deadline(장당 시간
    상한, 단계 사이에서만 확인)만으로 근사한다: MID_SECONDS 를 넘기면 erode3 부터는 late() 가 끊는다.
    ponytail: 단계 하나(det5, erode5)는 끝까지 돌고 나서만 시간을 보므로 "정확히 erode5 에서 끊긴다"는
    보장은 아니고, 이미지마다 앞 단계 소요가 달라 근사다. MID_SECONDS 는 실측 전 값이라 조정 가능."""
    import pipeline              # 무거운 임포트는 첫 판독까지 미룬다. 테스트는 이 함수를 바꿔 끼운다
    with _ocr_lock:
        if mode == "full":
            return pipeline.predict_one(path, strict=False, retry_upscale=True, max_seconds=MAX_SECONDS)
        import ocr
        from dateparse import extract_date
        if mode == "mid":
            items, stage = ocr.read_raw(path, True, "mid", time.monotonic() + MID_SECONDS)
        else:
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
        """shot: "first" = 스캐너 직후 1차 촬영(싼 모드), "mid" = 중간 재시도(erode5 까지),
        "second" = 하위 호환으로 "full" 과 동일 취급, "full" = 그 외 (전체 재시도)."""
        t0 = time.time()
        suffix = os.path.splitext(image.filename or "")[1] or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(image.file.read())
            tmp = f.name
        mode = "cheap" if shot == "first" else "mid" if shot == "mid" else "full"
        try:
            row = run_ocr(tmp, mode)
        finally:
            os.unlink(tmp)
        verdict = confidence.assess(row["texts"], row["stage"], row["year"], row["month"], row["day"], table)
        return {"year": row["year"], "month": row["month"], "day": row["day"], "final_date": row["final_date"],
                **verdict, "stage": row["stage"], "evidence": row["texts"][:12], "shot": shot,
                "product": products.lookup(barcode, catalog), "elapsed_ms": int((time.time() - t0) * 1000)}

    @app.post("/api/verify")
    def verify_listing(image: UploadFile = File(...), min_months: int = Form(0, ge=0, le=60),
                       product_name: str = Form("")):
        """중고거래 게시글용: 소비기한 표시 사진 한 장으로 등록 가능(allow), 불가(block), 운영자 확인(review) 판정.
        저장하지 않는다. 게시글 등록은 플랫폼 몫이고 여기는 판정만 돌려준다."""
        t0 = time.time()
        suffix = os.path.splitext(image.filename or "")[1] or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(image.file.read())
            tmp = f.name
        try:
            row = run_ocr(tmp, "full")
            assessed = confidence.assess(row["texts"], row["stage"], row["year"], row["month"], row["day"], table)
        except Exception:                     # 이미지가 아니거나 디코딩 실패: 500 대신 운영자 확인으로
            row = {"year": "NONE", "month": "NONE", "day": "NONE", "final_date": "NONE", "stage": "error", "texts": []}
            assessed = {"confidence": None, "needs_review": True, "bucket": "error"}
        finally:
            os.unlink(tmp)
        v = verify.verdict(row["year"], row["month"], row["day"], datetime.date.today(), min_months, assessed["needs_review"])
        if row["stage"] == "error":
            v["reason"] = "이미지를 판독하지 못했습니다. 운영자 확인이 필요합니다"
        return {"year": row["year"], "month": row["month"], "day": row["day"], "final_date": row["final_date"],
                **v, **assessed, "stage": row["stage"], "evidence": row["texts"][:12],
                "min_months": min_months, "product_name": product_name, "elapsed_ms": int((time.time() - t0) * 1000)}

    @app.post("/api/verify_listing")
    def verify_listing_photos(images: list[UploadFile] = File(...), product_name: str = Form("")):
        """중고거래 게시글용: 사진 최대 5장(당근, 번개장터처럼 올리는 게시글 사진)으로 등록 가능 여부를 판정한다.
        날짜를 읽은 사진들 중 가장 빠른 소비기한을 기준으로 삼는다(최저 기한, verify.listing_verdict). 저장하지 않는다.

        2단계 판독으로 지연을 줄인다.
        1단계: 모든 사진을 싼 모드(cheap)로 먼저 읽고 그 결과로 listing_verdict 를 계산한다.
        이미 등록 불가(block)로 확정되면 여기서 끝낸다(passes=1). 더 읽어서 날짜를 더 찾아내도
        최저 기한은 내려갈 수만 있지 올라갈 수는 없으므로, block 이면 2단계를 돌릴 이유가 없다.
        block 이 아니면 1단계에서 연도나 월을 못 읽은(NONE) 사진만 전체 모드(full)로 다시 읽어
        그 사진의 결과만 교체한 뒤 최종 판정을 내린다(passes=2)."""
        if len(images) > 5:
            raise HTTPException(status_code=422, detail="사진은 최대 5장까지 올릴 수 있습니다")
        t0 = time.time()

        def read_one(tmp: str, mode: str) -> tuple[dict, dict]:
            try:
                row = run_ocr(tmp, mode)
                assessed = confidence.assess(row["texts"], row["stage"], row["year"], row["month"], row["day"], table)
            except Exception:             # 이미지가 아니거나 디코딩 실패: 500 대신 날짜 없음 + 운영자 확인으로
                row = {"year": "NONE", "month": "NONE", "day": "NONE", "final_date": "NONE", "stage": "error", "texts": []}
                assessed = {"confidence": None, "needs_review": True, "bucket": "error"}
            return row, assessed

        def to_photo(i: int, row: dict, assessed: dict, mode: str, elapsed_ms: int) -> dict:
            return {"index": i, "year": row["year"], "month": row["month"], "day": row["day"],
                    "final_date": row["final_date"], "confidence": assessed["confidence"],
                    "needs_review": assessed["needs_review"], "stage": row["stage"],
                    "evidence": row["texts"][:5], "elapsed_ms": elapsed_ms, "mode": mode}

        def to_result(i: int, row: dict, assessed: dict) -> dict:
            return {"index": i, "year": row["year"], "month": row["month"], "day": row["day"],
                    "needs_review": assessed["needs_review"], "confidence": assessed["confidence"]}

        tmps: list[str] = []
        try:
            for image in images:
                suffix = os.path.splitext(image.filename or "")[1] or ".jpg"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                    f.write(image.file.read())
                    tmps.append(f.name)

            photos = []
            results = []
            for i, tmp in enumerate(tmps):
                p0 = time.time()
                row, assessed = read_one(tmp, "cheap")
                photos.append(to_photo(i, row, assessed, "cheap", int((time.time() - p0) * 1000)))
                results.append(to_result(i, row, assessed))

            lv = verify.listing_verdict(results, datetime.date.today(), MIN_MONTHS)
            if lv["verdict"] == "block":
                return {**lv, "min_months": MIN_MONTHS, "product_name": product_name, "photos": photos,
                        "passes": 1, "elapsed_ms": int((time.time() - t0) * 1000)}

            for i, tmp in enumerate(tmps):
                if results[i]["year"] != "NONE" and results[i]["month"] != "NONE":
                    continue
                p0 = time.time()
                row, assessed = read_one(tmp, "full")
                photos[i] = to_photo(i, row, assessed, "full", int((time.time() - p0) * 1000))
                results[i] = to_result(i, row, assessed)

            lv = verify.listing_verdict(results, datetime.date.today(), MIN_MONTHS)
            return {**lv, "min_months": MIN_MONTHS, "product_name": product_name, "photos": photos,
                    "passes": 2, "elapsed_ms": int((time.time() - t0) * 1000)}
        finally:
            for tmp in tmps:
                os.unlink(tmp)

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

    days_for = lambda barcode: products.discount_days(barcode, catalog)

    def list_rows(discount: int) -> list[dict]:
        with _db_lock:
            rows = store.list_items(conn, datetime.date.today(), days_for)
        # 할인 대상: 남은 일수가 분류별 기준 이하(기한 지남 포함)이고 아직 옮기지 않은 것
        return [r for r in rows if r["status"] in ("imminent", "expired") and not r["moved"]] if discount else rows

    @app.get("/api/items")
    def items(discount: int = 0):
        return list_rows(discount)

    @app.post("/api/items/{item_id}/moved")
    def moved(item_id: int, value: int = 1):
        with _db_lock:
            if not store.set_moved(conn, item_id, bool(value)):
                raise HTTPException(status_code=404, detail="없는 항목")
        return {"id": item_id, "moved": bool(value)}

    @app.get("/api/items.csv", response_class=PlainTextResponse)
    def items_csv(discount: int = 0):
        rows = list_rows(1) if discount else None
        with _db_lock:
            csv_text = store.to_csv(conn, rows)
        name = "discount_targets.csv" if discount else "items.csv"
        return PlainTextResponse("﻿" + csv_text, media_type="text/csv; charset=utf-8",
                                  headers={"Content-Disposition": f"attachment; filename={name}"})

    @app.get("/api/stats")
    def stats():
        with _db_lock:
            return store.stats(conn)

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")   # API 라우트 뒤에 둬야 가로채지 않는다
    return app
