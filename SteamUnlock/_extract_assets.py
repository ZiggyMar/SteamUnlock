import re, os
out = os.path.expandvars(r'%TEMP%\st_extract')
asset = r'F:\!Projects\SteamTools\SteamUnlock\assets'
os.makedirs(asset, exist_ok=True)
png_count = svg_count = 0
for binf in ('SteamTools.exe', 'Core.dll', 'Qt5Gui.dll'):
    p = os.path.join(out, binf)
    if not os.path.exists(p):
        continue
    data = open(p, 'rb').read()
    i = 0
    while True:
        s = data.find(b'\x89PNG\r\n\x1a\n', i)
        if s < 0:
            break
        e = data.find(b'IEND', s)
        if e > 0:
            blob = data[s:e + 8]
            if 200 < len(blob) < 2_000_000:
                open(os.path.join(asset, f'png_{binf}_{png_count}.png'), 'wb').write(blob)
                png_count += 1
        i = s + 8
    for m in re.finditer(rb'<svg[\s\S]{0,8000}?</svg>', data):
        blob = m.group(0)
        open(os.path.join(asset, f'svg_{binf}_{svg_count}.svg'), 'wb').write(blob)
        svg_count += 1
    # font-family declarations in QSS
    txt = data.decode('latin-1', 'ignore')
    fams = set(re.findall(r'font-family\s*:\s*["\']?([^;"\'}]+)', txt))
    if fams:
        print(f'{binf} fonts:', fams)
print('PNGs:', png_count, 'SVGs:', svg_count)
