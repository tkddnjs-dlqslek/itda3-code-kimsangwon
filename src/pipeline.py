# -*- coding: utf-8 -*-
"""이미지 폴더 -> submission 행. ocr.read 로 텍스트를 얻고 dateparse 로 날짜를 고른다."""
from __future__ import annotations

import os
import time

import pandas as pd

import ocr
from dateparse import extract_date

__all__ = ["COLS", "list_images", "predict_one", "predict_dir"]

COLS = ["image_id", "year", "month", "day", "final_date"]
EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
_NONE = ("NONE", "NONE", "NONE")


def list_images(input_dir: str) -> list[str]:
    return sorted(os.path.join(input_dir, f) for f in os.listdir(input_dir)
                  if f.lower().endswith(EXTS))


def predict_one(path: str, strict: bool = True, retry_upscale: bool = False) -> dict:
    image_id = os.path.splitext(os.path.basename(path))[0]
    try:
        texts, stage = ocr.read(path, retry_upscale)
        found = extract_date(texts)
        y, m, d = found or _NONE
        final = f"{y}-{m}-{d}" if found else "NONE"
    except Exception as e:
        if strict:
            raise
        print(f"[ERROR] {image_id}: {type(e).__name__}: {e}")
        texts, stage, (y, m, d) = [], "error", _NONE
        final = "NONE"
    return {"image_id": image_id, "year": y, "month": m, "day": d,
            "final_date": final, "stage": stage, "texts": texts}


def predict_dir(input_dir: str, strict: bool = True, retry_upscale: bool = False,
                log_every: int = 100) -> pd.DataFrame:
    paths = list_images(input_dir)
    n, t0, rows = len(paths), time.time(), []
    for i, p in enumerate(paths, 1):
        rows.append(predict_one(p, strict, retry_upscale))
        if log_every and (i % log_every == 0 or i == n):
            print(f"{i}/{n}  {(time.time() - t0) / i:.2f} s/img", flush=True)
    return pd.DataFrame(rows, columns=COLS)
