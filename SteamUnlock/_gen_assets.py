"""Build-time: turn the extracted SteamTools SVG/PNG assets into the runtime
PNG/ICO files the app loads. Produces light-tinted menu icons (for the dark
menu), resized logos, and an app.ico. Run once; outputs are bundled into the exe."""
import os, io, glob, cairosvg
from PIL import Image

ASSET = r'F:\!Projects\SteamTools\SteamUnlock\assets'
ICONS = os.path.join(ASSET, 'icons')
os.makedirs(ICONS, exist_ok=True)

# our-menu-item -> extracted SteamTools svg index
ICON_MAP = {
    'launch':     9,   # play
    'search':     18,  # magnifier
    'unlock':     3,   # open padlock
    'bulk':       31,  # stacked windows
    'solution':   20,  # shield-lock
    'keys':       39,  # key
    'folder':     10,  # folder
    'restart':    16,  # clock / refresh
    'settings':   33,  # sliders
    'mainwindow': 21,  # monitor
    'exit':       38,  # power
}

TINT = (203, 203, 203, 255)   # ST_ICON light grey for dark menu
SIZE = 20

def tint_png(png_bytes, color):
    im = Image.open(io.BytesIO(png_bytes)).convert('RGBA')
    alpha = im.split()[3]
    solid = Image.new('RGBA', im.size, color)
    out = Image.new('RGBA', im.size, (0, 0, 0, 0))
    out.paste(solid, (0, 0), alpha)
    return out

for name, idx in ICON_MAP.items():
    svg = os.path.join(ASSET, f'svg_SteamTools.exe_{idx}.svg')
    if not os.path.exists(svg):
        print('MISSING', svg); continue
    png = cairosvg.svg2png(url=svg, output_width=SIZE * 2, output_height=SIZE * 2)
    icon = tint_png(png, TINT).resize((SIZE, SIZE), Image.LANCZOS)
    icon.save(os.path.join(ICONS, f'{name}.png'))

# logos from the real SteamTools floating icon PNG (256x256)
logo = Image.open(os.path.join(ASSET, 'png_SteamTools.exe_0.png')).convert('RGBA')
logo.resize((78, 78), Image.LANCZOS).save(os.path.join(ASSET, 'logo_78.png'))
logo.resize((26, 26), Image.LANCZOS).save(os.path.join(ASSET, 'logo_26.png'))
logo.save(os.path.join(ASSET, 'app.ico'),
          sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])

print('generated', len(ICON_MAP), 'menu icons + logos + app.ico')
