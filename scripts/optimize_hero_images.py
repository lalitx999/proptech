#!/usr/bin/env python3
"""
Generate the responsive WebP variants used by the hero banner (LCP element).

WHY THIS EXISTS
---------------
`static/images/hero_banner.jpg` is 1600x1200 and ~536 KB. It is the Largest
Contentful Paint element on both `/` and `/listings/`, so on a 4G connection the
download alone blows past Google's 2.5 s LCP budget — the rest of the page is
irrelevant if the hero is still streaming.

`templates/core/home.html` and `templates/listings/marketplace.html` therefore
reference a <picture> element with:

    hero_banner-800.webp    ~93 KB   (phones)
    hero_banner-1200.webp  ~188 KB   (tablets / small laptops)
    hero_banner-1600.webp  ~326 KB   (retina desktop)
    hero_banner-1200.jpg   ~266 KB   (fallback for pre-WebP clients)

Re-run whenever the source photo changes:

    ../venv/bin/python scripts/optimize_hero_images.py

Requires Pillow. The original hero_banner.jpg is never modified.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
IMAGES_DIR = BASE_DIR / "static" / "images"
SRC = IMAGES_DIR / "hero_banner.jpg"

WIDTHS = (800, 1200, 1600)
WEBP_QUALITY = 78
JPEG_WIDTH = 1200
JPEG_QUALITY = 82


def main() -> int:
    if not SRC.exists():
        raise SystemExit(f"missing source image: {SRC}")

    source = Image.open(SRC).convert("RGB")
    print(f"source {SRC.name}: {source.size[0]}x{source.size[1]}, {SRC.stat().st_size / 1024:.0f} KB")

    for width in WIDTHS:
        height = round(source.height * width / source.width)
        target = IMAGES_DIR / f"hero_banner-{width}.webp"
        source.resize((width, height), Image.Resampling.LANCZOS).save(
            target, format="WEBP", quality=WEBP_QUALITY, method=6
        )
        print(f"  wrote {target.name:<24} {width}x{height}  {target.stat().st_size / 1024:.0f} KB")

    fallback_height = round(source.height * JPEG_WIDTH / source.width)
    fallback = IMAGES_DIR / f"hero_banner-{JPEG_WIDTH}.jpg"
    source.resize((JPEG_WIDTH, fallback_height), Image.Resampling.LANCZOS).save(
        fallback, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True
    )
    print(
        f"  wrote {fallback.name:<24} {JPEG_WIDTH}x{fallback_height}  "
        f"{fallback.stat().st_size / 1024:.0f} KB (fallback)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
