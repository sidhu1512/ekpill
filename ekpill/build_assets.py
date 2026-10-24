"""Turn ../app_art_assets into what the app and the packager need.

The shared art folder holds one flat set of PNGs plus a single-frame favicon.
The app wants a 32px tray PNG beside its code, and Windows wants a *multi-size*
.ico for the exe and the installer — a single-frame ico renders blurry in the
task manager and the Alt-Tab picker. This script copies the runtime asset and
regenerates the ico from the PNGs (16/32/48/64/128/256) every time, so the two
can never drift apart.

It also derives a sample media asset (assets/sample.jpg) from the hero art
for testing the media and file viewer.

    python build_assets.py
"""

from __future__ import annotations

import os
import shutil

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
candidate_sources = [
    os.path.normpath(os.path.join(HERE, "..", "app_art_assets")),
    os.path.join(HERE, "app_art_assets"),
]
SOURCE = next((s for s in candidate_sources if os.path.isdir(s)), candidate_sources[0])
ASSETS = os.path.join(HERE, "assets")
BUILD = os.path.join(HERE, "build")

# Sizes the ico must carry; Windows picks per context (explorer, task manager,
# Alt-Tab, the tray all ask for different ones).
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> int:
    if not os.path.isdir(SOURCE):
        print(f"assets: missing source folder {SOURCE}")
        return 1

    os.makedirs(ASSETS, exist_ok=True)
    os.makedirs(BUILD, exist_ok=True)

    # 1. The tray/window icon the running app loads. 32px is the size the tray
    #    draws at; anything larger is wasted work on a 40ms repaint path.
    src_32 = os.path.join(SOURCE, "icon_32x32.png")
    dst = os.path.join(ASSETS, "icon.png")
    shutil.copy2(src_32, dst)
    print(f"assets: {os.path.relpath(dst, HERE)} <- app_art_assets/icon_32x32.png")

    # 2. A real multi-size .ico. Pillow's ICO plugin is fed the largest frame
    #    and asked for the sizes it should downscale to; passing append_images
    #    instead records one frame, which is exactly the blurry bug this
    #    script exists to avoid.
    ico = os.path.join(BUILD, "ekpill.ico")
    base = Image.open(os.path.join(SOURCE, "icon_256x256.png")).convert("RGBA")
    base.save(ico, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    embedded = _ico_sizes(ico)
    print(f"assets: {os.path.relpath(ico, HERE)} "
          f"({len(embedded)} frames, sizes={embedded})")
    if len(embedded) < len(ICO_SIZES):
        print(f"assets: FAIL — expected {len(ICO_SIZES)} frames")
        return 1

    # 3. Clean up obsolete sample images / wallpapers if present
    sample_dst = os.path.join(ASSETS, "sample.jpg")
    if os.path.isfile(sample_dst):
        try:
            os.remove(sample_dst)
        except Exception:
            pass

    wallpapers_dir = os.path.join(ASSETS, "wallpapers")
    if os.path.isdir(wallpapers_dir):
        try:
            shutil.rmtree(wallpapers_dir)
        except Exception:
            pass
    return 0


def _ico_sizes(path: str) -> list[tuple[int, int]]:
    """Read the embedded sizes back out of the file's own directory.

    `Image.info['sizes']` only reports what PIL itself generated, so trusting
    it would hide a half-written icon; the directory is the ground truth
    Windows reads.
    """
    import struct

    with open(path, "rb") as fh:
        header = fh.read(6)
        _reserved, _type, count = struct.unpack("<HHH", header)
        out: list[tuple[int, int]] = []
        for _ in range(count):
            entry = fh.read(16)
            width, height = entry[0], entry[1]
            out.append((width or 256, height or 256))
    return sorted(out)


if __name__ == "__main__":
    raise SystemExit(main())