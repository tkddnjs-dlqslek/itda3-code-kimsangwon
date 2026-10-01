"""파이프라인 구조도 PNG 생성. matplotlib 있는 파이썬으로 실행한다.

    C:/Python313/python.exe tools/draw_pipeline.py
결과: 프로젝트 최상위의 파이프라인_구조도.png

상자 높이는 줄 수에서 자동으로 계산한다 (글이 상자 밖으로 넘치지 않게).
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib import font_manager

FONT = "C:/Windows/Fonts/malgun.ttf"
font_manager.fontManager.addfont(FONT)
plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT).get_name()
plt.rcParams["axes.unicode_minus"] = False

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   "파이프라인_구조도.png")

INK, GREY = "#1b1b1b", "#666666"
BLUE, GREEN, ORANGE, RED = "#2f6fb5", "#2e7d5b", "#c2701c", "#b23a3a"
PALE = "#f5f7fa"

TITLE_H = 3.4      # 제목이 차지하는 세로
LINE_H = 2.25      # 본문 한 줄
PAD = 1.6          # 아래 여백

W = 100.0
fig, ax = plt.subplots(figsize=(15, 22), dpi=130)
ax.axis("off")


def box(x, top, w, title, lines=(), edge=INK, face="white", tsize=12, lsize=9.5):
    """top 을 상자 윗변으로 삼아 그리고, 아랫변 y 를 돌려준다."""
    h = (TITLE_H if title else 0.6) + len(lines) * LINE_H + PAD
    y = top - h
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=0.7",
                                linewidth=1.4, edgecolor=edge, facecolor=face, zorder=2))
    cur = top - 1.9
    if title:
        ax.text(x + w / 2, cur, title, ha="center", va="center", fontsize=tsize,
                fontweight="bold", color=edge, zorder=3)
        cur = top - TITLE_H - 0.4
    for ln in lines:
        ax.text(x + 1.8, cur - LINE_H / 2, ln, ha="left", va="center", fontsize=lsize,
                color=INK, zorder=3)
        cur -= LINE_H
    return y


def arrow(x1, y1, x2, y2, color=INK, lw=1.5):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=14,
                                 linewidth=lw, color=color, zorder=1, shrinkA=0, shrinkB=0))


def note(x, y, text, color=GREY, size=9, ha="left", weight="normal"):
    ax.text(x, y, text, fontsize=size, color=color, ha=ha, va="center",
            style="italic", fontweight=weight, zorder=3)


TOP = 148.0
LX, LW = 2.5, 45.0          # 왼쪽 열
RX, RW = 52.5, 45.0         # 오른쪽 열
GAP = 3.2                   # 상자 사이 간격

# ---------------------------------------------------------------- 제목
ax.text(50, TOP, "소비기한 OCR 파이프라인", ha="center", va="top", fontsize=24,
        fontweight="bold", color=INK)
ax.text(50, TOP - 3.6, "ITDA 제3회 연합학술제 1차 예선  |  CODE 김상원  |  CPU 4코어, GPU 없음, 오프라인, Python 3.10",
        ha="center", va="top", fontsize=11, color=GREY)
ax.text(50, TOP - 6.4, "골드 1,000장 exact 0.901 (field 0.9347)   |   1.50초/장   |   500장 환산 750초 (한도 2,400초의 31%)",
        ha="center", va="top", fontsize=11.5, color=BLUE, fontweight="bold")

y = TOP - 10.5

# ---------------------------------------------------------------- 왼쪽 흐름
y = box(LX, y, LW, "입력: 상품 뒷면 사진",
        ["jpg 3,247 / jpeg 101 / png 4, 대부분 480x640 또는 640x640",
         "라벨 없음. EXIF 없이 90도 돌아간 사진이 섞여 있음"], edge=BLUE)
arrow(LX + LW / 2, y, LX + LW / 2, y - GAP)
y -= GAP

y = box(LX, y, LW, "1. 로드와 조각 검출",
        ["_load: 긴 변 기준 리사이즈 (기본 960)",
         "det = rapidocr 동봉 PP-OCRv4, 엔진은 한 번만 로드",
         "조각 분리: 큰 조각(높이 20 이상, 종횡비 12 이하) / 작은 조각"], edge=BLUE)
arrow(LX + LW / 2, y, LX + LW / 2, y - GAP)
y -= GAP

y = box(LX, y, LW, "2. 혼합 인식 hybrid_rec",
        ["1) korean_PP-OCRv5_rec_mobile 로 모든 조각을 읽는다",
         "2) 숫자가 3자 이상이거나 날짜 후보가 보이는 조각만",
         "     ch_PP-OCRv3 로 한 번 더 읽어 비교한다",
         "3) 완전한 날짜가 나오는 쪽을 채택",
         "4) 신뢰도 0.5 미만 조각은 버린다"], edge=BLUE)
arrow(LX + LW / 2, y, LX + LW / 2, y - GAP)
y -= GAP

gate_top = y
y = box(LX, y, LW, "3. 종료 판정 _ok",
        ["같은 줄 조각을 묶어 규칙 엔진에 넣는다",
         "날짜가 하나라도 나오면 그 단계에서 즉시 종료"], edge=GREEN)
gate_mid = (gate_top + y) / 2      # 규칙 엔진으로 가는 화살표는 오른쪽 열을 그린 뒤에 잇는다
arrow(LX + LW / 2, y, LX + LW / 2, y - GAP, color=ORANGE)
note(LX + LW / 2 + 1.5, y - GAP / 2, "못 찾으면 다음 단계", color=ORANGE)
y -= GAP

# ---------------------------------------------------------------- 단계 사다리
stages = [
    ("s1", "큰 조각만 인식", "기본 rec", "791장 해결, 정답률 96.2%"),
    ("s2", "작은 조각까지 추가", "기본 rec", "27장 해결, 정답률 92.6%"),
    ("det5", "PP-OCRv5 검출기로 재검출 (도트, 저대비)", "파인튜닝 v2", "75장 해결, 정답률 77.3%"),
    ("rot90", "시계 방향 90도 회전", "파인튜닝 v2", "7장 해결, 정답률 71.4%"),
    ("rot270", "반시계 방향 90도 회전", "파인튜닝 v2", "2장 해결, 정답률 0.0%"),
    ("rot180", "180도 회전", "파인튜닝 v2", "1장 해결, 정답률 0.0%"),
    ("clahe", "대비 강화 (금속면, 저대비 인쇄)", "파인튜닝 v2", "24장 해결, 정답률 66.7%"),
    ("hires", "원본 긴 변 1920 + 대비 강화", "파인튜닝 v2", "10장 해결, 정답률 60.0%"),
    ("up2x", "2배 확대 (작은 글씨)", "파인튜닝 v2", "11장 해결, 정답률 45.5%"),
    ("erode5", "침식 5x5 (도트 프린팅 점 잇기)", "파인튜닝 v2", "20장 해결, 정답률 90.0%"),
    ("erode3", "침식 3x3", "파인튜닝 v2", "7장 해결, 정답률 42.9%"),
    ("fail", "모든 단계 실패, 그동안 모은 글자로 판정", "", "25장, 정답률 16.0%"),
]
ROW_H, ROW_GAP = 5.0, 0.55
ladder_h = TITLE_H + 1.4 + len(stages) * (ROW_H + ROW_GAP) + PAD
ladder_top, ladder_bot = y, y - ladder_h
ax.add_patch(FancyBboxPatch((LX, ladder_bot), LW, ladder_h,
                            boxstyle="round,pad=0.2,rounding_size=0.7",
                            linewidth=1.4, edgecolor=ORANGE, facecolor="white", zorder=2))
ax.text(LX + LW / 2, ladder_top - 1.9, "4. 단계 사다리 (날짜를 찾는 즉시 종료)",
        ha="center", va="center", fontsize=12, fontweight="bold", color=ORANGE, zorder=3)

ry = ladder_top - TITLE_H - 1.4
for i, (name, desc, model, stat) in enumerate(stages):
    last = name == "fail"
    face = "#fdeeee" if last else ("#eef4fb" if i < 2 else "#fdf4e9")
    ec = RED if last else "#c9c9c9"
    ax.add_patch(FancyBboxPatch((LX + 4.2, ry - ROW_H), LW - 6.4, ROW_H,
                                boxstyle="round,pad=0.12,rounding_size=0.45",
                                linewidth=1.0, edgecolor=ec, facecolor=face, zorder=3))
    ax.text(LX + 5.8, ry - 1.7, name, fontsize=10.5, fontweight="bold",
            color=RED if last else INK, va="center", zorder=4)
    ax.text(LX + 14.5, ry - 1.7, desc, fontsize=9, color=INK, va="center", zorder=4)
    ax.text(LX + 5.8, ry - 3.6, "골드 " + stat, fontsize=8, color=GREY, va="center", zorder=4)
    if model:
        ax.text(LX + LW - 3.2, ry - 3.6, model, fontsize=8, va="center", ha="right", zorder=4,
                color=GREEN if model != "기본 rec" else GREY, style="italic")
    ry -= ROW_H + ROW_GAP

ax.add_patch(FancyArrowPatch((LX + 2.4, ladder_top - TITLE_H - 2.0), (LX + 2.4, ladder_bot + 2.0),
                             arrowstyle="-|>", mutation_scale=15, linewidth=1.8,
                             color=ORANGE, zorder=3))
ax.text(LX + 1.0, (ladder_top + ladder_bot) / 2, "실패하면 아래 단계로", rotation=90,
        fontsize=8.5, color=ORANGE, ha="center", va="center", zorder=3)

ladder_mid = (ladder_top + ladder_bot) / 2

# ---------------------------------------------------------------- 오른쪽 열
ry2 = TOP - 10.5
rule_top = ry2
ry2 = box(RX, ry2, RW, "5. 후처리 규칙 엔진 (src/dateparse.py)",
          ["정규화: 숫자가 섞인 덩어리 안에서만 O를 0, I와 l을 1로",
           "날짜 패턴 20여종: YYYY.MM.DD, YY.MM.DD, DD MM YYYY,",
           "     01 SEP 2023, 20280527, 연도가 뒤에 오는 표기 등",
           "키워드 교정 사전 22종 (유동기한, 유롱기한 -> 유통기한)",
           "키워드 점수: 앞 조각 만료 +1, 앞 조각 제조 -1,",
           "     뒤 조각 까지 +1, 뒤 조각 부터 -1",
           "소비기한과 유통기한이 함께 있으면 소비기한 우선",
           "범위 표기는 끝 날짜, 포장일자 줄의 날짜는 후보에서 제외",
           "쓰레기 방어: 자릿수 깨짐, 구분자 불일치, 쉼표 섞임 감점",
           "부분 날짜 허용: 연도가 없으면 NONE-02-18 로 출력"], edge=GREEN)
rule_mid = (rule_top + ry2) / 2

# 종료 판정과 사다리에서 날짜가 나오면 규칙 엔진으로 넘어간다 (꺾은 화살표)
for src_y in (gate_mid, ladder_mid):
    ax.add_patch(FancyArrowPatch((LX + LW, src_y), (RX, rule_mid), arrowstyle="-|>",
                                 mutation_scale=14, linewidth=1.5, color=GREEN, zorder=1,
                                 connectionstyle="angle,angleA=0,angleB=90,rad=3"))
    note(LX + LW + 1.5, src_y + 1.7, "날짜 나옴", color=GREEN, weight="bold")

arrow(RX + RW / 2, ry2, RX + RW / 2, ry2 - GAP)
ry2 -= GAP

ry2 = box(RX, ry2, RW, "6. 최종 선택",
          ["후보마다 점수를 매겨 가장 높은 것을 고른다",
           "동점이면 더 늦은 날짜 (운영진 판정 기준)",
           "연, 월, 일을 각각 독립으로 채운다"], edge=GREEN)
arrow(RX + RW / 2, ry2, RX + RW / 2, ry2 - GAP)
ry2 -= GAP

ry2 = box(RX, ry2, RW, "출력: submission.csv",
          ["image_id, year, month, day, final_date",
           "미인식 항목은 NONE, 셋 다 없으면 final_date 는 NONE"], edge=BLUE)
ry2 -= GAP * 1.6

ry2 = box(RX, ry2, RW, "시간 예산 가드 (속도 점수 보호)",
          ["set_budget(2280초, 장수) 로 시작한다",
           "장마다 남은 시간을 남은 장수로 나눠 여유를 계산",
           "여유 6.0초 이상: full, 사다리 전부 수행",
           "여유 2.0초 이상: cheap, s1 과 s2 와 det5 까지만",
           "그 미만: s1 만 수행",
           "채점 서버가 느려도 2,400초 한도를 넘기지 않는다"], edge=RED)
ry2 -= GAP

ry2 = box(RX, ry2, RW, "두 줄 분리 (침식 단계 안에서)",
          ["침식하면 날짜 줄과 시각 줄이 붙어버리는 경우가 있다",
           "조각 안에서 어두운 픽셀이 가장 적은 경로를 왼쪽에서",
           "     오른쪽으로 찾아 그 선을 따라 자른다 (이음매 자르기)",
           "자른 뒤 새 날짜나 키워드나 시각이 보일 때만 채택",
           "무조건 절반으로 자르지 않아 잘못된 분할을 막는다"], edge=ORANGE)
ry2 -= GAP

ry2 = box(RX, ry2, RW, "사용 모델 (전부 오프라인 ONNX)",
          ["det 기본: PP-OCRv4, rapidocr-onnxruntime 패키지 동봉",
           "det 재시도: ch_PP-OCRv5_det_mobile (4.8MB)",
           "rec 기본: korean_PP-OCRv5_rec_mobile (13.5MB)",
           "rec 숫자 재확인: ch_PP-OCRv3_rec_infer (10.7MB)",
           "rec 재시도: korean_PP-OCRv5_rec_ft_v2 (13.5MB)",
           "     ExpDate 날짜 조각과 일반 글자 앵커를 1대1로 학습",
           "가중치는 규정상 Git 커밋 금지, Release Assets 로 배포"],
          edge=BLUE, face=PALE)

# ---------------------------------------------------------------- 하단
bottom = min(ladder_bot, ry2) - GAP * 1.8

perf_h = TITLE_H + 4 * LINE_H + PAD
py = bottom - perf_h
ax.add_patch(FancyBboxPatch((LX, py), RX + RW - LX, perf_h,
                            boxstyle="round,pad=0.2,rounding_size=0.7",
                            linewidth=1.4, edgecolor=INK, facecolor=PALE, zorder=2))
ax.text((LX + RX + RW) / 2, bottom - 1.9, "실측 성능", ha="center", va="center",
        fontsize=12, fontweight="bold", color=INK, zorder=3)
cols = [
    (LX + 2.5, "골드 1,000장 (사람이 직접 라벨링)",
     ["exact 901장 (0.9010), field 0.9347", "연 0.935 / 월 0.942 / 일 0.927",
      "s1 에서 종료 791장, 재시도 209장"]),
    (LX + 33, "전량 3,352장",
     ["오류 0건, 형식 위반 0건", "날짜 미검출 61장 (1.8%)",
      "s1 2,833 / det5 180 / s2 109 / fail 81"]),
    (LX + 65, "속도 (로컬 4코어 기준)",
     ["1.50초/장, 500장 환산 750초", "제한 2,400초의 31%",
      "채점 서버가 3배 느려도 한도 안"]),
]
for cx, head, items in cols:
    ax.text(cx, bottom - TITLE_H - 1.2, head, fontsize=10, fontweight="bold", color=INK, zorder=3)
    for i, t in enumerate(items):
        ax.text(cx, bottom - TITLE_H - 3.3 - i * LINE_H, "- " + t, fontsize=9.5, color=INK, zorder=3)

rej = [
    "rec 파인튜닝 v1: 골드 884 -> 865. 날짜는 좋아졌지만 키워드 인식이 무너졌다",
    "rec 파인튜닝 v3: 골드 901 -> 896. 조각은 더 잘 읽지만 사다리가 일찍 멈춘다 (뒤집힌 9장 중 7장이 단계 변경)",
    "단계 교차검증: exact +2장에 시간 +75%. 속도 점수 위험이 이득보다 크다",
    "전 단계 완전 탐색: 10초/장으로 한도 초과",
    "조기 종료 조건 완화: 걸리는 20장 중 이미 틀린 것이 10장. 기대 이득이 노이즈 수준",
]
ry3 = py - GAP
rej_h = TITLE_H + len(rej) * LINE_H + PAD
ax.add_patch(FancyBboxPatch((LX, ry3 - rej_h), RX + RW - LX, rej_h,
                            boxstyle="round,pad=0.2,rounding_size=0.7",
                            linewidth=1.4, edgecolor=RED, facecolor="white", zorder=2))
ax.text((LX + RX + RW) / 2, ry3 - 1.9, "측정으로 기각한 설계 (EXPERIMENT_LOG.md)",
        ha="center", va="center", fontsize=12, fontweight="bold", color=RED, zorder=3)
for i, t in enumerate(rej):
    ax.text(LX + 2.5, ry3 - TITLE_H - 1.2 - i * LINE_H, "- " + t, fontsize=9.5, color=INK, zorder=3)

ax.set_xlim(0, W)
ax.set_ylim(ry3 - rej_h - 2, TOP + 2)
fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print("saved", OUT)
