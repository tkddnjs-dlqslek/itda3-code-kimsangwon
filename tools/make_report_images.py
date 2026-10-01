# -*- coding: utf-8 -*-
"""요약서에 넣을 근거 이미지 8종 생성.

실행: C:/anaconda/envs/itda/python.exe tools/make_report_images.py
출력: ../보고서이미지/*.png

각 칸은 가로로 긴 띠를 목표로 한다. 한글 캡션은 넣지 않는다 (디자인 쪽에서 붙임).
"""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import dateparse
import ocr

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(REPO)
IMGS = os.path.join(ROOT, "images")
OUT = os.path.join(ROOT, "보고서이미지")
os.makedirs(OUT, exist_ok=True)

FONT = "C:/Windows/Fonts/malgun.ttf"
BLUE, GREY, RED, GREEN = (227, 113, 0), (170, 170, 170), (60, 60, 220), (90, 170, 60)  # BGR


def path_of(image_id):
    for ext in (".jpg", ".jpeg", ".png"):
        p = os.path.join(IMGS, image_id + ext)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(image_id)


def save(name, img):
    p = os.path.join(OUT, name)
    cv2.imencode(".png", img)[1].tofile(p)
    print(f"  saved {name}  {img.shape[1]}x{img.shape[0]}")


def draw_boxes(img, items, color=GREEN, th=2):
    out = img.copy()
    for _, box in items:
        cv2.polylines(out, [np.asarray(box, np.int32)], True, color, th)
    return out


def region(img, boxes, pad=0.12):
    """박스 여러 개를 감싸는 영역을 잘라낸다 (인쇄 시 글자가 보이게 확대용)."""
    if not boxes:
        return img
    pts = np.concatenate([np.asarray(b, dtype=float) for b in boxes])
    x0, x1 = pts[:, 0].min(), pts[:, 0].max()
    y0, y1 = pts[:, 1].min(), pts[:, 1].max()
    mx, my = (x1 - x0) * pad, (y1 - y0) * pad
    x0 = max(0, int(x0 - mx)); x1 = min(img.shape[1], int(x1 + mx))
    y0 = max(0, int(y0 - my)); y1 = min(img.shape[0], int(y1 + my))
    return img[y0:y1, x0:x1]


def band(img, box, pad=0.9):
    """박스가 든 가로 띠를 잘라낸다 (좌우는 전체 폭)."""
    b = np.asarray(box, dtype=float)
    y0, y1 = b[:, 1].min(), b[:, 1].max()
    h = y1 - y0
    y0 = max(0, int(y0 - h * pad))
    y1 = min(img.shape[0], int(y1 + h * pad))
    return img[y0:y1], y0


def stack(panels, gap=10, bg=255):
    """가로 폭을 맞춰 세로로 쌓는다."""
    w = max(p.shape[1] for p in panels)
    rows = []
    for i, p in enumerate(panels):
        if p.shape[1] != w:
            s = w / p.shape[1]
            p = cv2.resize(p, (w, int(p.shape[0] * s)), interpolation=cv2.INTER_AREA)
        rows.append(p)
        if i < len(panels) - 1:
            rows.append(np.full((gap, w, 3), bg, np.uint8))
    return np.vstack(rows)


def side(panels, gap=10, bg=255):
    """세로 높이를 맞춰 가로로 붙인다."""
    h = max(p.shape[0] for p in panels)
    cols = []
    for i, p in enumerate(panels):
        if p.shape[0] != h:
            s = h / p.shape[0]
            p = cv2.resize(p, (int(p.shape[1] * s), h), interpolation=cv2.INTER_AREA)
        cols.append(p)
        if i < len(panels) - 1:
            cols.append(np.full((h, gap, 3), bg, np.uint8))
    return np.hstack(cols)


def text_panel(lines, width, size=22, pad=10, lead=1.5):
    """한글 포함 텍스트 패널 (PIL). lead 는 줄 간격 배수."""
    fnt = ImageFont.truetype(FONT, size)
    step = int(size * lead)
    h = pad * 2 + len(lines) * step
    im = Image.new("RGB", (width, h), "white")
    d = ImageDraw.Draw(im)
    y = pad
    for t, col in lines:
        d.text((pad, y), t, font=fnt, fill=col)
        y += step
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)


def date_item(items):
    """조각 중 완전한 날짜가 읽히는 것 하나를 (text, box) 로 돌려준다."""
    for t, box in items:
        if ocr._has_complete_date(t):
            return t, box
    return None, None


# ---------------------------------------------------------------- 01 침식 전후
def img01(image_id="000122"):
    img = ocr._load(path_of(image_id))
    er = cv2.erode(img, np.ones((5, 5), np.uint8))
    raw0 = ocr._crops(img)
    raw1 = ocr._crops(er, loose=True)
    read1 = ocr.hybrid_rec(raw1, retry=True)
    _, box = date_item(read1)
    if box is None:
        print("  01: 날짜 박스 못 찾음"); return
    b0, y0 = band(draw_boxes(img, raw0, GREY), box)
    b1, _ = band(draw_boxes(er, raw1, GREEN), box)
    save("01_침식_전후.png", stack([b0, b1]))


# ---------------------------------------------------------------- 02 이음매 자르기
def img02(image_id="000255"):
    img = ocr._load(path_of(image_id))
    er = cv2.erode(img, np.ones((5, 5), np.uint8))
    items = ocr._crops(er, loose=True)
    if not items:
        print("  02: 조각 없음"); return
    med = float(np.median([c.shape[0] for c, _ in items]))
    tall = [it for it in items if it[0].shape[0] >= 1.5 * med]
    if not tall:
        tall = [max(items, key=lambda it: it[0].shape[0])]
    crop, box = tall[0]
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    h = g.shape[0]
    path = ocr._seam((g < 128).astype(float), h // 4, 3 * h // 4)
    marked = crop.copy()
    for x, y in enumerate(path):
        cv2.circle(marked, (x, int(y)), 1, RED, -1)
    halves = ocr._split2(crop, box)
    save("02_이음매_자르기.png",
         stack([crop, marked, halves[0][0], halves[1][0]], gap=6))


# ---------------------------------------------------------------- 03 노이즈 혼재
def img03(image_id="000327"):
    img = ocr._load(path_of(image_id))
    items = ocr.hybrid_rec(ocr._crops(img))
    gold = {r["image_id"]: r for r in
            csv.DictReader(open(os.path.join(REPO, "labels", "gold.csv"), encoding="utf-8"))}
    g = gold[image_id]
    want = f"{g['year']}-{g['month']}-{g['day']}"
    out = img.copy()
    hit, near = None, []
    for t, box in items:
        c = dateparse.extract_date([t])
        is_ans = c is not None and "-".join(c) == want
        cv2.polylines(out, [np.asarray(box, np.int32)], True,
                      BLUE if is_ans else GREY, 3 if is_ans else 1)
        if is_ans:
            hit = box
    if hit is None:
        print("  03: 정답 박스 못 찾음")
        save("03_노이즈_혼재.png", out)
        return
    # 정답 박스 주변만 크게 (인쇄에서 읽히도록)
    hb = np.asarray(hit, dtype=float)
    cy = hb[:, 1].mean()
    for t, box in items:
        b = np.asarray(box, dtype=float)
        if abs(b[:, 1].mean() - cy) < img.shape[0] * 0.22:
            near.append(box)
    save("03_노이즈_혼재.png", region(out, near, pad=0.1))


# ---------------------------------------------------------------- 04 인식기 이원화
def img04(candidates=("000008", "000034", "000039", "000032", "000035", "000010")):
    for image_id in candidates:
        img = ocr._load(path_of(image_id))
        er = cv2.erode(img, np.ones((5, 5), np.uint8))
        for items in (ocr._crops(img), ocr._crops(er, loose=True)):
            if not items:
                continue
            crops = [c for c, _ in items]
            ko = ocr._rec("ko")(crops)[0]
            ch = ocr._rec("ch")(crops)[0]
            for i, ((tk, _), (tc, _)) in enumerate(zip(ko, ch)):
                if tk == tc:
                    continue
                if ocr._has_complete_date(tc) and not ocr._has_complete_date(tk):
                    crop = crops[i]
                    s = max(1, 480 // max(1, crop.shape[1]))
                    big = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
                    panel = text_panel([(f"한국어 모델  {tk}", (0, 0, 0)),
                                        (f"중국어 숫자 모델  {tc}", (BLUE[2], BLUE[1], BLUE[0]))],
                                       width=big.shape[1], size=20)
                    save("04_인식기_이원화.png", stack([big, panel], gap=6))
                    print(f"  04: {image_id} 조각 {i}")
                    return
    print("  04: 사례 못 찾음")


# ---------------------------------------------------------------- 05 회전 전후
def img05(image_id="000416"):
    img = ocr._load(path_of(image_id))
    rot = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    ia, ib = ocr._crops(img), ocr._crops(rot)
    a = region(draw_boxes(img, ia, GREY, 2), [b for _, b in ia], pad=0.06)
    b = region(draw_boxes(rot, ib, GREEN, 2), [b for _, b in ib], pad=0.06)
    save("05_회전_전후.png", side([a, b]))


# ---------------------------------------------------------------- 06 실제 출력
def img06(image_id="000372"):
    """현재 제출 스키마 한 줄과, 바코드를 붙였을 때의 재고 DB 한 줄을 나란히 보여준다.
    확장 줄은 실제 출력이 아니라 예시이므로 라벨로 분명히 구분한다."""
    img = ocr._load(path_of(image_id), 300)
    pred = {r["image_id"]: r for r in
            csv.DictReader(open(os.path.join(REPO, "labels", "auto_gold_v5_mixed_v2.csv"),
                                encoding="utf-8"))}[image_id]
    line = f"{image_id},{pred['year']},{pred['month']},{pred['day']},{pred['final_date']}"
    BL, GY = (0, 0, 0), (145, 145, 145)
    panel = text_panel([
        ("현재 제출 스키마", (0, 113, 227)),
        ("image_id, year, month, day, final_date", GY),
        (line, BL),
        ("", GY),
        ("확장 시 재고 DB 한 줄 (바코드 결합, 예시)", (0, 113, 227)),
        ("촬영시각, 매장, 바코드, 상품명, 소비기한, 수량", GY),
        ("2026-09-13 18:20, ST-042, 880xxxxxxxxxx, 바코드로 조회한 상품명, 2026-09-15, 1", BL),
    ], width=1800, size=34, lead=1.22)
    save("06_실제_출력.png", side([img, panel]))


# ---------------------------------------------------------------- 07 라벨링 증빙
def img07(n=5):
    """검수 엑셀 화면처럼 보이게 그린다 (열 머리글, 행 번호, 격자)."""
    src = os.path.join(ROOT, "v3검수_결과.csv")
    rows = [r for r in csv.DictReader(open(src, encoding="utf-8-sig"))
            if r["확인"].strip() and r["확인"].strip() != "제외"][:n]
    cols = [("A", "이미지", 90), ("B", "조각 사진", 300), ("C", "모델이 읽은 글자", 330),
            ("D", "사람이 확인한 값", 300), ("E", "메모", 250)]
    RH, HDR, TOP, LEFT = 64, 34, 26, 44
    W = LEFT + sum(c[2] for c in cols) + 2
    H = TOP + HDR + RH * len(rows) + 2
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    f_hdr = ImageFont.truetype(FONT, 17)
    f_col = ImageFont.truetype(FONT, 15)
    f_body = ImageFont.truetype(FONT, 18)
    grid, head_bg, dim = (208, 211, 214), (242, 243, 245), (120, 124, 128)

    # 엑셀 열 문자 줄
    d.rectangle([0, 0, W, TOP], fill=head_bg)
    x = LEFT
    for letter, _, w in cols:
        d.text((x + w / 2 - 5, 5), letter, font=f_col, fill=dim)
        d.line([(x, 0), (x, H)], fill=grid)
        x += w
    d.rectangle([0, 0, LEFT, H], fill=head_bg)

    # 열 머리글
    y = TOP
    d.rectangle([LEFT, y, W, y + HDR], fill=head_bg)
    x = LEFT
    for _, name, w in cols:
        d.text((x + 10, y + 9), name, font=f_hdr, fill=(40, 42, 45))
        x += w
    d.line([(0, y + HDR), (W, y + HDR)], fill=grid)

    y += HDR
    for i, r in enumerate(rows):
        d.text((14, y + RH / 2 - 10), str(i + 2), font=f_col, fill=dim)
        x = LEFT
        vals = [r["image_id"], None, r["모델읽은"], r["확인"].strip(), r["메모"] or ""]
        for (letter, _name, w), v in zip(cols, vals):
            if v is None:
                p = os.path.join(ROOT, "rec_label_nongold", "crops", r["file"])
                crop = cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)
                if crop is not None:
                    s = min((RH - 16) / crop.shape[0], (w - 20) / crop.shape[1])
                    crop = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
                    im.paste(Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)),
                             (x + 10, y + (RH - crop.shape[0]) // 2))
            else:
                t = v if len(v) <= 22 else v[:21] + "…"
                col = (0, 113, 227) if letter == "D" else (30, 30, 32)
                d.text((x + 10, y + RH / 2 - 12), t, font=f_body, fill=col)
            x += w
        y += RH
        d.line([(0, y), (W, y)], fill=grid)
    d.rectangle([0, 0, W - 1, H - 1], outline=grid)
    save("07_라벨링_증빙.png", cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR))


# ---------------------------------------------------------------- 08 사다리 회복
def img08(image_id="000305"):
    img = ocr._load(path_of(image_id))
    cl = ocr._clahe(img)
    er = cv2.erode(img, np.ones((5, 5), np.uint8))
    bases = [img, cl, er]
    stages = [ocr._crops(img), ocr._crops(cl, loose=True), ocr._crops(er, loose=True)]
    read = ocr.hybrid_rec(stages[2], retry=True)
    _, hit = date_item(read)
    panels = []
    for i, (base, items) in enumerate(zip(bases, stages)):
        drawn = draw_boxes(base, items, GREEN if i == 2 else GREY, 2)
        panels.append(region(drawn, [hit], pad=1.1) if hit is not None else drawn)
    save("08_사다리_회복사례.png", side(panels))


if __name__ == "__main__":
    # img05(회전 전후)는 제외. 골드의 rot90 성공 사진이 전부 똑바로 찍힌 사진이라
    # "누운 사진을 세웠다"는 그림이 성립하지 않는다 (회전 이득은 검출 차이에서 옴).
    for fn in (img01, img02, img03, img04, img06, img07, img08):
        print(fn.__name__)
        try:
            fn()
        except Exception as e:
            print(f"  실패: {type(e).__name__}: {e}")
    print("완료:", OUT)
