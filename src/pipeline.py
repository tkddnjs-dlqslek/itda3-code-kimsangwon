# -*- coding: utf-8 -*-
"""이미지 폴더 -> submission 행. ocr.read 로 텍스트를 얻고 dateparse 로 날짜를 고른다."""
from __future__ import annotations

import json, os
import time

import pandas as pd

import ocr
from dateparse import extract_date

__all__ = ["COLS", "list_images", "predict_one", "predict_dir", "set_budget"]

COLS = ["image_id", "year", "month", "day", "final_date"]
EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
_NONE = ("NONE", "NONE", "NONE")

# 시간 예산 상태. set_budget() 이 안 불리면 기존 동작 그대로 (deadline=None -> 항상 "full").
_budget = {"deadline": None, "remaining": 0}

# 남은 장당 예산(초) 임계값. 500장/2280초 예산(장당 4.56초)에서 여유가 있을 때만 비싼 단계를
# 허용하고, 빠듯해지면 회전·재시도(clahe/hires/up2x/erode)부터, 더 빠듯하면 s2/det5까지 접는다.
# 09-15 재조정: 6.0/2.0 은 시작부터 장당 4.56초라 처음 150장을 축소 모드로 돌려 늦은 단계 정답을 잃었다.
# 리눅스 재현 실측 평균 1.5초/장의 2배인 3.0 을 full 기준으로 둔다. 채점 서버가 3배 느려도 2,400초 안.
# ponytail: 고정 휴리스틱 값. 실측 s/img 분포가 크게 달라지면 다시 캘리브레이션할 것.
_FULL_MIN_S = 3.0
_CHEAP_MIN_S = 1.0


def set_budget(total_seconds: float | None, n_images: int) -> None:
    """전체 예산(초)과 처리할 이미지 수를 설정. total_seconds=None 이면 예산 해제(기존 동작)."""
    _budget["deadline"] = None if total_seconds is None else time.time() + total_seconds
    _budget["remaining"] = max(n_images, 0)


def _decide_stage(retry_upscale: bool) -> tuple[bool, str]:
    """예산에 따라 (실제 retry_upscale, stage_cap) 결정. 예산 미설정 시 인자 그대로 "full"."""
    deadline = _budget["deadline"]
    if deadline is None:
        return retry_upscale, "full"
    per_image = (deadline - time.time()) / max(_budget["remaining"], 1)
    if per_image >= _FULL_MIN_S:
        return retry_upscale, "full"
    if per_image >= _CHEAP_MIN_S:
        return False, "cheap"
    return False, "s1"


def list_images(input_dir: str) -> list[str]:
    return sorted(os.path.join(input_dir, f) for f in os.listdir(input_dir)
                  if f.lower().endswith(EXTS))


def predict_one(path: str, strict: bool = True, retry_upscale: bool = False) -> dict:
    image_id = os.path.splitext(os.path.basename(path))[0]
    try:
        eff_retry, stage_cap = _decide_stage(retry_upscale)
        items, stage = ocr.read_raw(path, eff_retry, stage_cap)
        lines_geo = ocr.group_lines_geo(items)
        texts = [t for t, _, _ in lines_geo]
        geo = [(cy, h) for _, cy, h in lines_geo]
        raw = json.dumps([[t] + [round(v) for v in ocr._geom(b)] for t, b in items], ensure_ascii=False)
        found = extract_date(texts, geo)
        y, m, d = found or _NONE
        final = f"{y}-{m}-{d}" if found else "NONE"
    except Exception as e:
        if strict:
            raise
        print(f"[ERROR] {image_id}: {type(e).__name__}: {e}")
        texts, raw, stage, (y, m, d) = [], "[]", "error", _NONE
        final = "NONE"
    finally:
        # 예산이 걸려 있으면 성공/실패 무관하게 남은 이미지 수를 줄인다 (다음 장의 장당 예산 갱신용)
        if _budget["deadline"] is not None:
            _budget["remaining"] = max(_budget["remaining"] - 1, 0)
    return {"image_id": image_id, "year": y, "month": m, "day": d,
            "final_date": final, "stage": stage, "texts": texts, "raw": raw}


def predict_dir(input_dir: str, strict: bool = True, retry_upscale: bool = False,
                log_every: int = 100) -> pd.DataFrame:
    paths = list_images(input_dir)
    n, t0, rows = len(paths), time.time(), []
    for i, p in enumerate(paths, 1):
        rows.append(predict_one(p, strict, retry_upscale))
        if log_every and (i % log_every == 0 or i == n):
            print(f"{i}/{n}  {(time.time() - t0) / i:.2f} s/img", flush=True)
    return pd.DataFrame(rows, columns=COLS)
