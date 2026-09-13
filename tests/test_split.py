import numpy as np
import cv2
import ocr


def _line_img(text, baseline_y):
    img = np.full((70, 300, 3), 235, np.uint8)
    cv2.putText(img, text, (5, baseline_y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    return img


def test_split2_separates_lines():
    a = _line_img("2026.12.19", 30)
    b = _line_img("15:52", 58)
    combined = np.minimum(a, b)
    box = [[0, 0], [300, 0], [300, 70], [0, 70]]
    top, bot = ocr._split2(combined, box)
    top_img, _ = top
    bot_img, _ = bot

    g = cv2.cvtColor(combined, cv2.COLOR_BGR2GRAY)
    path = ocr._seam((g < 128).astype(float), g.shape[0] // 4, 3 * g.shape[0] // 4)

    dark_a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY) < 128
    dark_b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY) < 128

    # top piece 는 원본 좌표계 0..path.max() 를 담는다
    top_full = np.zeros_like(dark_a)
    top_full[: path.max() + 1] = cv2.cvtColor(top_img, cv2.COLOR_BGR2GRAY)[: path.max() + 1] < 128
    bot_full = np.zeros_like(dark_a)
    bot_full[path.min():] = cv2.cvtColor(bot_img, cv2.COLOR_BGR2GRAY)[:] < 128

    a_total = dark_a.sum()
    b_total = dark_b.sum()
    assert (top_full & dark_a).sum() >= 0.95 * a_total
    assert (top_full & dark_b).sum() < 0.05 * b_total
    assert (bot_full & dark_b).sum() >= 0.95 * b_total
    assert (bot_full & dark_a).sum() < 0.05 * a_total


def test_features_time_only():
    assert ocr._features("15:52E") == {"time"}


def test_features_date():
    assert "date" in ocr._features("2026.12.19")


def test_features_keyword():
    assert "kw" in ocr._features("소비기한 2026.12.19 까지")
