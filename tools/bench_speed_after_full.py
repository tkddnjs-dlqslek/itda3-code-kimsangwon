"""전체 3,352장 실행이 끝나면(= CPU 여유) 채택 구성으로 500장 속도를 단독 측정한다."""
import os, sys, time, random, shutil, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
FULL = "labels/auto_full_v6.csv"
def rows(p):
    return sum(1 for _ in open(p, encoding="utf-8")) - 1 if os.path.exists(p) else 0
while rows(FULL) < 3352:
    time.sleep(60)
time.sleep(30)                      # 파일 정리 여유
import ocr, pipeline
print("RETRY_REC =", ocr.RETRY_REC, flush=True)
allp = pipeline.list_images(os.path.join("..", "images"))
random.Random(42).shuffle(allp)
tmp = tempfile.mkdtemp(prefix="speed500b_")
for p in allp[:500]:
    shutil.copy2(p, tmp)
paths = pipeline.list_images(tmp)
pipeline.set_budget(2280, len(paths))
t0 = time.time()
df = pipeline.predict_dir(tmp, strict=False, retry_upscale=True, log_every=100)
el = time.time() - t0
print(f"RESULT 채택 구성 500장 {el:.1f}초 ({el/len(paths):.2f} s/img), 한도 2400초 대비 {el/2400*100:.0f}%", flush=True)
df.to_csv("labels/speed500_mixed_preds.csv", index=False, encoding="utf-8")
shutil.rmtree(tmp, ignore_errors=True)
print("DONE", flush=True)
