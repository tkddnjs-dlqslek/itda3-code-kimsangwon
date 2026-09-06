"""검수 시트. python tools/make_sheets.py ../images labels/auto.csv labels/sheets"""
import sys, os, csv
from PIL import Image, ImageDraw, ImageOps, ImageFont

img_dir, label_csv, out_dir = sys.argv[1:4]
os.makedirs(out_dir, exist_ok=True)
rows = list(csv.DictReader(open(label_csv, encoding="utf-8")))
files = {os.path.splitext(f)[0]: f for f in os.listdir(img_dir)}
try:
    font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 22)
except Exception:
    font = ImageFont.load_default()
N, COLS, W = 20, 4, 520
for s in range(0, len(rows), N):
    chunk = rows[s:s + N]
    sheet = Image.new("RGB", (COLS * W, ((len(chunk) + COLS - 1) // COLS) * W), "white")
    for i, r in enumerate(chunk):
        im = ImageOps.exif_transpose(Image.open(os.path.join(img_dir, files[r["image_id"]]))).convert("RGB")
        im.thumbnail((W - 10, W - 50))
        x, y = (i % COLS) * W, (i // COLS) * W
        sheet.paste(im, (x + 5, y + 45))
        d = ImageDraw.Draw(sheet)
        d.text((x + 5, y + 5), f'{r["image_id"]}  {r["final_date"]}', fill="red", font=font)
        d.text((x + 5, y + 25), r.get("stage", ""), fill="blue", font=font)
    sheet.save(os.path.join(out_dir, f"sheet_{s // N:03d}.jpg"), quality=80)
print("sheets:", (len(rows) + N - 1) // N)
