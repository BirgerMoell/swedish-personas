"""Render the 1200x630 social preview (docs/og.png) from docs/people.json.

Needs Pillow and numpy. Fonts (Instrument Serif, OFL) are downloaded to data/fonts/.
"""

import json
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "data/fonts"
BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl/instrumentserif/"
S = 2  # supersample
W, H = 1200 * S, 630 * S
STOPS = [(0, (61, 245, 208)), (20, (74, 168, 255)), (40, (138, 107, 255)), (60, (255, 95, 176)), (80, (255, 154, 90)), (100, (255, 227, 106))]


def font(name, size):
    path = FONTS / name
    if not path.exists():
        FONTS.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(BASE + name, path)
    return ImageFont.truetype(str(path), size * S)


def age_rgb(age):
    age = max(0, min(100, age))
    for (a0, c0), (a1, c1) in zip(STOPS, STOPS[1:]):
        if age <= a1:
            t = (age - a0) / (a1 - a0)
            return tuple(c0[i] + (c1[i] - c0[i]) * t for i in range(3))
    return STOPS[-1][1]


def glow_blob(layer, x, y, color, radius, strength):
    d = ImageDraw.Draw(layer)
    d.ellipse([x - radius, y - radius, x + radius, y + radius], fill=(*[int(c) for c in color], int(255 * strength)))


def gradient_text(canvas, xy, text, fnt, colors):
    mask = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(mask).text(xy, text, font=fnt, fill=255)
    box = mask.getbbox()
    grad = Image.new("RGB", canvas.size)
    gd = ImageDraw.Draw(grad)
    x0, x1 = box[0], box[2]
    for x in range(x0, x1 + 1):
        t = (x - x0) / max(1, x1 - x0) * (len(colors) - 1)
        i = min(int(t), len(colors) - 2)
        f = t - i
        c = tuple(int(colors[i][k] + (colors[i + 1][k] - colors[i][k]) * f) for k in range(3))
        gd.line([(x, 0), (x, H)], fill=c)
    canvas.paste(grad, (0, 0), mask)
    return box


def main():
    p = json.loads((ROOT / "docs/people.json").read_text(encoding="utf-8"))
    img = Image.new("RGB", (W, H), (7, 10, 20))

    # aurora
    aur = Image.new("RGB", (W, H), (7, 10, 20))
    a = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for (cx, cy, r, col, al) in ((0.1, 0.0, 0.6, (138, 107, 255), 80), (0.95, 0.15, 0.45, (61, 245, 208), 50), (0.62, 1.05, 0.45, (255, 95, 176), 34), (0.0, 0.95, 0.4, (74, 168, 255), 45)):
        glow_blob(a, cx * W, cy * H, col, r * W, al / 255)
    a = a.filter(ImageFilter.GaussianBlur(160 * S))
    img = Image.alpha_composite(img.convert("RGBA"), a).convert("RGB")

    # map region (right side)
    mh = H * 0.9
    mw = mh * p["aspect"]
    ox = W * 0.955 - mw
    oy = (H - mh) / 2
    def pos(xv, yv):
        return ox + xv / 65535 * mw, oy + yv / 65535 * mh

    land = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(land)
    for i in range(0, len(p["land"]), 2):
        x, y = pos(p["land"][i], p["land"][i + 1])
        r = 1.5 * S
        ld.ellipse([x - r, y - r, x + r, y + r], fill=(150, 165, 220, 80))
    img = Image.alpha_composite(img.convert("RGBA"), land)

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dots = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd, dd = ImageDraw.Draw(glow), ImageDraw.Draw(dots)
    order = np.random.default_rng(3).permutation(len(p["x"]))
    for i in order:
        x, y = pos(p["x"][i], p["y"][i])
        c = tuple(int(v) for v in age_rgb(p["age"][i]))
        gr = 9 * S
        gd.ellipse([x - gr, y - gr, x + gr, y + gr], fill=(*c, 70))
        r = 3.4 * S
        dd.ellipse([x - r, y - r, x + r, y + r], fill=(*c, 235))
    glow = glow.filter(ImageFilter.GaussianBlur(7 * S))
    img = Image.alpha_composite(img, glow)
    img = Image.alpha_composite(img, dots)
    img = img.convert("RGB")

    # text
    d = ImageDraw.Draw(img)
    left = 76 * S
    d.rounded_rectangle([left, 74 * S, left + 22 * S, 76 * S], radius=S, fill=(138, 107, 255))
    small = font("InstrumentSerif-Regular.ttf", 1)  # placeholder to ensure download
    label_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15 * S) if Path("/System/Library/Fonts/Helvetica.ttc").exists() else ImageFont.load_default()
    d.text((left + 34 * S, 66 * S), "OPEN SYNTHETIC DATA  ·  NEMOTRON FORMAT", font=label_font, fill=(141, 149, 179))

    big = font("InstrumentSerif-Regular.ttf", 124)
    ital = font("InstrumentSerif-Italic.ttf", 124)
    d.text((left, 136 * S), "Sverige,", font=big, fill=(238, 241, 251))
    gradient_text(img, (left, 248 * S), "en person", ital, [(61, 245, 208), (74, 168, 255), (138, 107, 255), (255, 95, 176), (255, 179, 108)])
    d = ImageDraw.Draw(img)
    d.text((left, 360 * S), "i taget.", font=big, fill=(238, 241, 251))

    # glass persona card
    import textwrap
    idx = next(i for i in range(len(p["x"])) if 30 <= p["age"][i] <= 40 and len(p["txt"][i]) < 130)
    cx0, cy0, cx1, cy1 = 520 * S, 392 * S, 850 * S, 560 * S
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle([cx0, cy0, cx1, cy1], radius=22 * S, fill=(255, 255, 255, 22), outline=(255, 255, 255, 60), width=S)
    accent = tuple(int(v) for v in age_rgb(p["age"][idx]))
    ImageDraw.Draw(layer).rounded_rectangle([cx0, cy0 + 18 * S, cx0 + 4 * S, cy1 - 18 * S], radius=2 * S, fill=(*accent, 255))
    img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
    d = ImageDraw.Draw(img)
    d.text((cx0 + 26 * S, cy0 + 20 * S), p["name"][idx], font=font("InstrumentSerif-Regular.ttf", 34), fill=(238, 241, 251))
    meta = f"{p['age'][idx]} år · {p['kommuner'][p['kom'][idx]]}"
    d.text((cx0 + 26 * S, cy0 + 62 * S), meta, font=ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14 * S), fill=(141, 149, 179))
    body = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15 * S)
    for n, line in enumerate(textwrap.wrap(p["txt"][idx], 40)[:3]):
        d.text((cx0 + 26 * S, cy0 + 90 * S + n * 22 * S), line, font=body, fill=(198, 203, 224))

    sub = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 25 * S)
    d.text((left, 536 * S), "100 000 fiktiva personas", font=sub, fill=(238, 241, 251))
    d.text((left, 572 * S), "SCB · Socialstyrelsen · Folkhälsomyndigheten", font=ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 17 * S), fill=(141, 149, 179))

    out = img.resize((1200, 630), Image.LANCZOS)
    out.save(ROOT / "docs/og.png", optimize=True)
    print("Wrote docs/og.png")


if __name__ == "__main__":
    main()
