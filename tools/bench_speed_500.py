"""채점 환경 모사 속도 실측: 500장, 시간 예산 2280초, 4스레드.
predict.ipynb 와 같은 경로(pipeline.set_budget + predict_dir)를 그대로 쓴다."""
import os, sys, time, random, shutil, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pipeline
IMAGES = os.path.join("..", "images")
allp = pipeline.list_images(IMAGES)
random.Random(42).shuffle(allp)
sample = allp[:500]
tmp = tempfile.mkdtemp(prefix="speed500_")
for p in sample:
    shutil.copy2(p, tmp)
print(f"복사 완료 {len(os.listdir(tmp))}장 -> {tmp}", flush=True)
paths = pipeline.list_images(tmp)
pipeline.set_budget(2280, len(paths))
t0 = time.time()
df = pipeline.predict_dir(tmp, strict=False, retry_upscale=True, log_every=50)
el = time.time() - t0
print(f"RESULT 500장 {el:.1f}초 ({el/len(paths):.2f} s/img), 한도 2400초 대비 {el/2400*100:.0f}%", flush=True)
df.to_csv("labels/speed500_preds.csv", index=False, encoding="utf-8")
shutil.rmtree(tmp, ignore_errors=True)
print("DONE", flush=True)
