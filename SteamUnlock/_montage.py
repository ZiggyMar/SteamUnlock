import os, glob, cairosvg, io
from PIL import Image, ImageDraw, ImageFont

asset = r'F:\!Projects\SteamTools\SteamUnlock\assets'
svgs = sorted(glob.glob(os.path.join(asset, 'svg_*.svg')),
              key=lambda p: int(p.split('_')[-1].split('.')[0]))
cell, cols = 80, 8
rows = (len(svgs) + cols - 1) // cols
W, H = cols * cell, rows * cell
sheet = Image.new('RGBA', (W, H), (40, 40, 40, 255))
draw = ImageDraw.Draw(sheet)
try:
    font = ImageFont.truetype("arial.ttf", 11)
except Exception:
    font = ImageFont.load_default()

for i, sp in enumerate(svgs):
    idx = sp.split('_')[-1].split('.')[0]
    try:
        png = cairosvg.svg2png(url=sp, output_width=44, output_height=44,
                               background_color='white')
        icon = Image.open(io.BytesIO(png)).convert('RGBA')
    except Exception as e:
        continue
    cx = (i % cols) * cell
    cy = (i // cols) * cell
    sheet.paste(icon, (cx + 18, cy + 8), icon)
    draw.text((cx + 4, cy + 60), f"#{idx}", fill=(255, 220, 120), font=font)

sheet.save(os.path.join(asset, '_svg_montage.png'))
print("montage saved:", len(svgs), "icons")
