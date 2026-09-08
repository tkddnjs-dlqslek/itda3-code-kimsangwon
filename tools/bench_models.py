"""오류 이미지에 det/rec 변형 비교. python tools/bench_models.py labels/gold.csv labels/errors.csv
변형별로 정답 맞춘 수와 장당 시간 출력."""
import sys, os, csv, time, importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import ocr, pipeline

gold = {r["image_id"]: f'{r["year"]}-{r["month"]}-{r["day"]}' for r in csv.DictReader(open(sys.argv[1], encoding="utf-8"))}
err = [r["image_id"] for r in csv.DictReader(open(sys.argv[2], encoding="utf-8")) if r["kind"] != "false_positive"]
# 대조군: 맞았던 이미지 60장 (회귀 확인)
ok_ids = [i for i in gold if i not in set(err)][:60]
files = {os.path.splitext(f)[0]: os.path.join("../images", f) for f in os.listdir("../images")}

VARIANTS = {
    "A_current (v4det, ko5+ch3)": dict(det=None, ch="ch_PP-OCRv3_rec_infer.onnx"),
    "B_v5det": dict(det="ch_PP-OCRv5_det_mobile.onnx", ch="ch_PP-OCRv3_rec_infer.onnx"),
    "C_ch5rec": dict(det=None, ch="ch_PP-OCRv5_rec_mobile.onnx"),
    "D_en5rec": dict(det=None, ch="en_PP-OCRv5_rec_mobile.onnx"),
    "E_v5det+ch5rec": dict(det="ch_PP-OCRv5_det_mobile.onnx", ch="ch_PP-OCRv5_rec_mobile.onnx"),
    "F_v6det_small": dict(det="PP-OCRv6_det_small.onnx", ch="ch_PP-OCRv3_rec_infer.onnx"),
}
which = sys.argv[3].split(",") if len(sys.argv) > 3 else list(VARIANTS)
for name in which:
    cfg = VARIANTS[name]
    ocr._ENGINES.clear(); ocr.DET_FILE = cfg["det"]; ocr._REC_FILES["ch"] = cfg["ch"]
    try:
        t = time.time(); hit_err = 0; hit_ok = 0
        for i in err:
            r = pipeline.predict_one(files[i], strict=False, retry_upscale=True)
            hit_err += r["final_date"] == gold[i]
        t_err = time.time() - t
        for i in ok_ids:
            r = pipeline.predict_one(files[i], strict=False, retry_upscale=True)
            hit_ok += r["final_date"] == gold[i]
        print(f"{name:28s} 오류{len(err)}장 중 회복 {hit_err:3d}   대조{len(ok_ids)}장 유지 {hit_ok:2d}   {t_err/len(err):.2f}s/img(오류셋)", flush=True)
    except Exception as e:
        print(f"{name:28s} FAILED {type(e).__name__}: {str(e)[:120]}", flush=True)
