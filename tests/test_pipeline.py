import os, pytest, numpy as np, cv2
from pipeline import predict_one, predict_dir, COLS
IMG = os.path.join(os.path.dirname(__file__), "..", "..", "images")
pytestmark = pytest.mark.skipif(not os.path.isdir(IMG), reason="local images only")


@pytest.mark.parametrize("fn,expected", [
    ("000001.jpg", "2027-06-26"),
    ("000002.jpg", "2025-12-11"),
    ("000500.jpg", "2026-12-17"),
    ("000050.jpg", "2025-09-30"),
])
def test_predict_one_known(fn, expected):
    row = predict_one(os.path.join(IMG, fn))
    assert row["image_id"] == os.path.splitext(fn)[0]
    assert row["final_date"] == expected
    assert row["stage"] in ("s1", "s2")


def test_schema_on_blank(tmp_path):
    cv2.imwrite(str(tmp_path / "x.jpg"), np.full((100, 100, 3), 255, np.uint8))
    df = predict_dir(str(tmp_path))
    assert list(df.columns) == COLS
    assert df.iloc[0].tolist() == ["x", "NONE", "NONE", "NONE", "NONE"]


def test_strict_false_catches(tmp_path):
    (tmp_path / "bad.jpg").write_bytes(b"not an image")
    with pytest.raises(Exception):
        predict_one(str(tmp_path / "bad.jpg"), strict=True)
    row = predict_one(str(tmp_path / "bad.jpg"), strict=False)
    assert row["final_date"] == "NONE" and row["stage"] == "error"


def test_leading_zero_id_preserved(tmp_path):
    cv2.imwrite(str(tmp_path / "000007.jpg"), np.full((100, 100, 3), 255, np.uint8))
    df = predict_dir(str(tmp_path))
    assert df.iloc[0]["image_id"] == "000007"


def _box(x, y, w=120, h=30):
    return [[x, y - h / 2], [x + w, y - h / 2], [x + w, y + h / 2], [x, y + h / 2]]


def test_group_lines_two_rows():
    from ocr import group_lines
    items = [("부터", _box(200, 100)), ("2025.06.17", _box(10, 100)),
             ("까지", _box(205, 140)), ("2026.06.16", _box(12, 140))]
    assert group_lines(items) == ["2025.06.17 부터", "2026.06.16 까지"]


def test_group_lines_tilted():
    from ocr import group_lines
    items = [("2025.06.17", _box(10, 100)), ("부터", _box(200, 112)),
             ("2026.06.16", _box(12, 138)), ("까지", _box(205, 150))]
    assert group_lines(items) == ["2025.06.17 부터", "2026.06.16 까지"]
