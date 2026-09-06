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
