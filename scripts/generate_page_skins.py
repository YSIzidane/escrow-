"""Generate DZHub page-skin backgrounds.

1. Inspects downloaded Unsplash images (validates size + dominant colour).
2. Generates custom modern blue/white "aurora mesh" backgrounds in the exact
   DZHub brand palette using Pillow.
3. Converts every skin to WebP (keeps the JPG too) for fast delivery.

Usage: python scripts/generate_page_skins.py
"""

import math
import os

from PIL import Image, ImageDraw, ImageFilter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND_DIR = os.path.join(BASE_DIR, "static", "images", "brand")

# DZHub palette
NAVY = (10, 37, 64)
BLUE = (18, 97, 160)
BLUE_DARK = (11, 71, 122)
SKY = (125, 211, 252)
AQUA = (56, 189, 248)
PAPER = (246, 250, 253)
WHITE = (255, 255, 255)


def inspect_downloaded() -> None:
    print("-- Downloaded Unsplash skins --")
    for name in sorted(os.listdir(BRAND_DIR)):
        if not (name.startswith("skin-") and name.endswith(".jpg")):
            continue
        path = os.path.join(BRAND_DIR, name)
        try:
            with Image.open(path) as im:
                im.load()
                small = im.convert("RGB").resize((32, 18))
                pixels = list(small.getdata())
                avg = tuple(sum(c[i] for c in pixels) // len(pixels) for i in range(3))
                print(f"  {name:28s} {im.size[0]}x{im.size[1]}  avg RGB={avg}  "
                      f"blue-dominant={avg[2] > avg[0]}")
        except Exception as exc:
            print(f"  {name:28s} INVALID: {exc}")


def radial_blob(size: int, color: tuple, alpha: int) -> Image.Image:
    """A soft radial-gradient disc of the given colour."""
    layer = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(layer)
    step = max(2, size // 90)
    for r in range(size // 2, 0, -step):
        a = int(alpha * (1 - r / (size / 2)) ** 1.6)
        draw.ellipse(
            [size // 2 - r, size // 2 - r, size // 2 + r, size // 2 + r],
            fill=a,
        )
    blob = Image.new("RGBA", (size, size), color + (0,))
    blob.putalpha(layer)
    return blob


def add_grain(img: Image.Image, strength: int) -> Image.Image:
    """Subtle film grain for a luxury texture feel."""
    w, h = img.size
    grain = Image.effect_noise((w // 4, h // 4), strength).resize((w, h)).convert("L")
    return Image.blend(img, Image.merge("RGB", (grain, grain, grain)), 0.035)


def paste_blob(img: Image.Image, cx: float, cy: float, scale: float,
               color: tuple, alpha: int, blur_div: int = 10) -> Image.Image:
    w, h = img.size
    size = int(min(w, h) * scale)
    blob = radial_blob(size, color, alpha)
    blob = blob.filter(ImageFilter.GaussianBlur(size // blur_div))
    img.paste(blob, (int(w * cx - size / 2), int(h * cy - size / 2)), blob)
    return img


def aurora_light(w: int, h: int) -> Image.Image:
    """Light luxury mesh: paper base + soft blue/white aurora blobs + streak."""
    img = Image.new("RGB", (w, h), PAPER)
    for cx, cy, scale, color, alpha in [
        (0.18, 0.22, 0.92, BLUE, 66), (0.78, 0.16, 0.86, SKY, 74),
        (0.62, 0.68, 0.96, AQUA, 58), (0.30, 0.84, 0.80, BLUE_DARK, 42),
        (0.94, 0.86, 0.70, SKY, 56), (0.06, 0.62, 0.66, BLUE, 48),
    ]:
        paste_blob(img, cx, cy, scale, color, alpha)
    # gentle diagonal light streak
    streak = Image.new("L", (w, h), 0)
    sd = ImageDraw.Draw(streak)
    sd.polygon([(int(w * .45), 0), (int(w * .62), 0),
                (int(w * .38), h), (int(w * .21), h)], fill=26)
    streak = streak.filter(ImageFilter.GaussianBlur(120))
    img = Image.composite(Image.new("RGB", (w, h), WHITE), img, streak)
    return add_grain(img, 5)


def aurora_dark(w: int, h: int) -> Image.Image:
    """Deep-navy aurora for dark bands (page headers / footer accents)."""
    img = Image.new("RGB", (w, h), NAVY)
    for cx, cy, scale, color, alpha in [
        (0.24, 0.30, 0.95, BLUE, 88), (0.80, 0.22, 0.85, AQUA, 72),
        (0.68, 0.78, 0.90, BLUE_DARK, 80), (0.10, 0.80, 0.75, BLUE, 66),
    ]:
        paste_blob(img, cx, cy, scale, color, alpha, blur_div=9)
    return add_grain(img, 4)


def grid_tech_light(w: int, h: int) -> Image.Image:
    """Paper base + faint engineering grid + blue corner glows."""
    img = Image.new("RGB", (w, h), PAPER)
    paste_blob(img, 0.08, 0.10, 0.80, BLUE, 60, blur_div=8)
    paste_blob(img, 0.92, 0.88, 0.80, SKY, 64, blur_div=8)
    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    for x in range(0, w, 64):
        gd.line([(x, 0), (x, h)], fill=BLUE + (16,), width=1)
    for y in range(0, h, 64):
        gd.line([(0, y), (w, y)], fill=BLUE + (16,), width=1)
    img = Image.alpha_composite(img.convert("RGBA"), grid).convert("RGB")
    return add_grain(img, 4)


def waves_light(w: int, h: int) -> Image.Image:
    """Soft flowing blue waves on white — premium, calm."""
    img = Image.new("RGB", (w, h), PAPER)
    wave = Image.new("RGB", (w, h), PAPER)
    wd = ImageDraw.Draw(wave)
    for color, thick, phase in [
        ((224, 242, 254), 150, 0.0), ((186, 230, 253), 110, 0.9),
        ((125, 211, 252), 70, 1.7), ((56, 189, 248), 36, 2.4),
    ]:
        points = [(x, h * 0.55 + math.sin(x / w * math.pi * 2.2 + phase) * h * 0.16)
                   for x in range(0, w + 8, 8)]
        wd.line(points, fill=color, width=thick)
    wave = wave.filter(ImageFilter.GaussianBlur(46))
    # waves get stronger toward the bottom, headers stay clean
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    top = int(h * 0.18)
    for y in range(top, h):
        md.line([(0, y), (w, y)], fill=int(255 * (y - top) / (h - top)))
    img.paste(wave, (0, 0), mask)
    return add_grain(img, 4)


GENERATED = {
    "skin-mesh-aurora-light.jpg": aurora_light,
    "skin-mesh-aurora-dark.jpg": aurora_dark,
    "skin-grid-tech-light.jpg": grid_tech_light,
    "skin-waves-light.jpg": waves_light,
}


def save_skins() -> None:
    print("-- Generated brand skins --")
    for name, fn in GENERATED.items():
        img = fn(1920, 1200)
        path = os.path.join(BRAND_DIR, name)
        img.save(path, "JPEG", quality=88, optimize=True)
        webp = path.replace(".jpg", ".webp")
        img.save(webp, "WEBP", quality=82, method=6)
        print(f"  {name:28s} {os.path.getsize(path)//1024}KB "
              f"(webp {os.path.getsize(webp)//1024}KB)")


def make_webp_for_downloaded() -> None:
    print("-- WebP for downloaded skins --")
    for name in sorted(os.listdir(BRAND_DIR)):
        if not (name.startswith("skin-") and name.endswith(".jpg")):
            continue
        if name in GENERATED:
            continue
        path = os.path.join(BRAND_DIR, name)
        webp = path.replace(".jpg", ".webp")
        with Image.open(path) as im:
            im.save(webp, "WEBP", quality=80, method=6)
        print(f"  {name:28s} jpg {os.path.getsize(path)//1024}KB "
              f"-> webp {os.path.getsize(webp)//1024}KB")


if __name__ == "__main__":
    inspect_downloaded()
    save_skins()
    make_webp_for_downloaded()
    print("Done.")

def paste_blob(img: Image.Image, cx: float, cy: float, scale: float,
               color: tuple, alpha: int, blur_div: int = 10) -> Image.Image:
    w, h = img.size
    size = int(min(w, h) * scale)
    blob = radial_blob(size, color, alpha)
    blob = blob.filter(ImageFilter.GaussianBlur(size // blur_div))
    img.paste(blob, (int(w * cx - size / 2), int(h * cy - size / 2)), blob)
    return img
