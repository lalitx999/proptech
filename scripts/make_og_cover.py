#!/usr/bin/env python3
"""
Generate the 1200x630 Open Graph / Twitter Card cover image.

WHY THIS EXISTS
---------------
`templates/base.html`, `templates/seo/sitemap.xml` and the listing JSON-LD all point at
`static/images/og-cover.png`, and the file did not exist — every social share and every
Google image reference resolved to a 404, which silently kills link previews and can make
the image sitemap fail validation.

The official OGP spec recommends 1200x630 (1.91:1) so Facebook / LINE / X / LinkedIn all
render a full-bleed card without cropping. Re-run this script whenever the brand changes:

    ../venv/bin/python scripts/make_og_cover.py

Requires Pillow and system Thai fonts.
Output: static/images/og-cover.png
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_LOGO = BASE_DIR / "static" / "images" / "logo.png"
OUT_PATH = BASE_DIR / "static" / "images" / "og-cover.png"

WIDTH, HEIGHT = 1200, 630

BRAND_PINK = (225, 29, 116)
BRAND_DARK = (109, 7, 58)
WHITE = (255, 255, 255)

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Thonburi.ttc",
    "/System/Library/Fonts/ThonburiUI.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    raise SystemExit("ไม่พบฟอนต์ไทย (Thonburi / Noto Sans Thai) — ติดตั้งฟอนต์ก่อนรันสคริปต์")


def vertical_gradient(size, top, bottom) -> Image.Image:
    """Cheap 1-pixel-wide gradient stretched horizontally (fast + smooth)."""
    width, height = size
    base = Image.new("RGB", (1, height))
    pixels = base.load()
    for y in range(height):
        ratio = y / max(height - 1, 1)
        pixels[0, y] = tuple(round(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
    return base.resize((width, height), Image.Resampling.BILINEAR)


def wordmark_image() -> Image.Image:
    """Crop the white Thai wordmark out of logo.png so it can sit on our own gradient."""
    logo = Image.open(SRC_LOGO).convert("RGBA")
    rgb = logo.convert("RGB")
    mask = Image.new("L", logo.size, 0)
    mask_pixels = mask.load()
    rgb_pixels = rgb.load()
    for y in range(logo.size[1]):
        for x in range(logo.size[0]):
            r, g, b = rgb_pixels[x, y]
            if min(r, g, b) > 205:
                mask_pixels[x, y] = 255

    bbox = mask.getbbox()
    if bbox is None:
        raise SystemExit("ไม่พบตัวอักษรสีขาวใน logo.png")

    cropped = logo.crop(bbox)
    cropped.putalpha(mask.crop(bbox))
    return cropped


def main() -> int:
    canvas = vertical_gradient((WIDTH, HEIGHT), BRAND_PINK, BRAND_DARK).convert("RGBA")

    # Soft radial glow behind the wordmark so the card reads as a designed asset, not a flat fill.
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        (WIDTH // 2 - 430, 40, WIDTH // 2 + 430, 470), fill=(255, 255, 255, 46)
    )
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(90)))

    # Subtle dot grid (matches the brand's web hero pattern).
    dots = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    dot_draw = ImageDraw.Draw(dots)
    for y in range(20, HEIGHT, 32):
        for x in range(20, WIDTH, 32):
            dot_draw.ellipse((x, y, x + 2, y + 2), fill=(255, 255, 255, 40))
    canvas = Image.alpha_composite(canvas, dots)

    # Wordmark: 880px wide, centred in the upper part of the card.
    mark = wordmark_image()
    target_w = 880
    target_h = round(mark.height * target_w / mark.width)
    mark = mark.resize((target_w, target_h), Image.Resampling.LANCZOS)
    canvas.alpha_composite(mark, ((WIDTH - target_w) // 2, 118))

    draw = ImageDraw.Draw(canvas)

    tagline = "ตลาดเซ้งร้าน ขายกิจการ ทำเลทอง ทั่วไทย"
    font_tag = load_font(38)
    draw.text(
        ((WIDTH - draw.textlength(tagline, font=font_tag)) / 2, 118 + target_h + 40),
        tagline,
        font=font_tag,
        fill=WHITE,
    )

    # Trust chips — drawn on their own RGBA layer first, because ImageDraw on an RGBA canvas
    # REPLACES the alpha channel instead of blending it (which is why a naive
    # `fill=(255,255,255,44)` flattened to solid white once the image went RGB).
    chip_font = load_font(26)
    chips = ["ตรวจร้านจริง", "ข้อมูลกำไร 3 เดือน", "สัญญาโปร่งใส"]
    chip_pad_x, gap, chip_h = 26, 16, 50
    chip_widths = [draw.textlength(text, font=chip_font) + chip_pad_x * 2 for text in chips]
    total_w = sum(chip_widths) + gap * (len(chips) - 1)
    chip_y = 118 + target_h + 112

    chip_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    chip_draw = ImageDraw.Draw(chip_layer)
    chip_text_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    chip_text_draw = ImageDraw.Draw(chip_text_layer)

    x = (WIDTH - total_w) / 2
    for text, chip_w in zip(chips, chip_widths):
        chip_draw.rounded_rectangle(
            (x, chip_y, x + chip_w, chip_y + chip_h),
            radius=chip_h // 2,
            fill=(255, 255, 255, 230),
        )
        text_h = chip_font.getbbox(text)[3]
        chip_text_draw.text(
            (x + chip_pad_x, chip_y + (chip_h - text_h) / 2 - 3),
            text,
            font=chip_font,
            fill=BRAND_DARK + (255,),
        )
        x += chip_w + gap

    canvas = Image.alpha_composite(canvas, chip_layer)
    canvas = Image.alpha_composite(canvas, chip_text_layer)

    # Footer URL — drawn last on its own layer (the `draw` handle above points at the
    # PRE-composite canvas, so drawing on it again would write to a discarded image).
    footer_font = load_font(24)
    footer = "เซ้งร้านด่วน.com"
    footer_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    footer_draw = ImageDraw.Draw(footer_layer)
    footer_draw.text(
        ((WIDTH - footer_draw.textlength(footer, font=footer_font)) / 2, HEIGHT - 60),
        footer,
        font=footer_font,
        fill=(255, 255, 255, 210),
    )
    canvas = Image.alpha_composite(canvas, footer_layer)

    # Flatten to RGB: OGP images have no alpha channel and some scrapers choke on RGBA PNGs.
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(OUT_PATH, format="PNG", optimize=True)
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.1f} KB, {WIDTH}x{HEIGHT})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
