"""Rebuild preview.html from the selftest screenshots.

Each shot is a full 1920x1080 grab of the transparent overlay, so it is cropped
to its ink bounding box first and then inlined as a data URI: the preview has to
stand on its own with no sibling files to fetch.

    python main.py --selftest --pos=top --page=notif ...   # render the shots
    python build_preview.py                                # rebuild the page
"""

from __future__ import annotations

import base64
import io
import json
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))

# (file, caption). Order tells the story: the capsule, every edge, the morph,
# then the notification surfaces added last.
SHOTS = [
    ("ekpill_selftest_top.png", "<b>Collapsed (top)</b> — weekday, dot-matrix clock, battery."),
    ("ekpill_selftest_right.png", "<b>Docked right</b> — a slim upright strip, not rotated text."),
    ("ekpill_selftest_right_quick.png", "<b>Docked right, opened</b> — the same upright panel, docked to the edge."),
    ("ekpill_selftest_quick.png", "<b>Quick settings</b> — the default on hover: media, volume, radios, Focus, and the tool tiles."),
    ("ekpill_selftest_media.png", "<b>Now playing</b> — title, artist, art, transport and seek, from SMTC."),
    ("ekpill_selftest_launcher.png", "<b>Launcher</b> — Start Menu apps with instant search."),
    ("ekpill_selftest_power.png", "<b>Power menu.</b>"),
    ("ekpill_selftest_settings.png", "<b>Settings</b> — a compact switchboard: Focus, auto-hide, autostart, dock edge and hotkeys."),
    ("ekpill_selftest_audio.png", "<b>Audio Mixer</b> — per-application volume sliders and reactive WASAPI wave visualizer."),
    ("ekpill_selftest_record.png", "<b>Screen Recorder</b> — FPS selection, microphone and loopback audio controls."),
    ("ekpill_selftest_files.png", "<b>Files</b> — the usual folders, every drive, sorting, and a delete that goes to the Recycle Bin."),
    ("ekpill_selftest_files_menu.png", "<b>Files, row menu</b> — open, rename, copy, cut, recycle: the verbs Explorer has, in the capsule."),
]

PAD = 4          # breathing room around the silhouette


def crop(path: str) -> Image.Image:
    """Crop a full-screen grab to EkPill's silhouette.

    The grab is RGBA: the pill is opaque black over a transparent window, so the
    **alpha** channel is the shape — luminance cannot see it at all. Keeping the
    alpha is also what lets the preview's gradient show through the parts where
    the capsule is not, which is the whole point of showing a transparent shell.

    When the selftest wrote its geometry sidecar, the reported rect has to be
    covered by those pixels; if it is not, the render and the geometry disagree
    and the capture is not trustworthy.
    """
    im = Image.open(path)
    if im.mode != "RGBA":
        raise SystemExit(f"{path}: expected an RGBA grab, got {im.mode}")
    w, h = im.size
    box = im.getchannel("A").point(lambda v: 255 if v > 0 else 0).getbbox()
    if box is None:
        raise SystemExit(f"{path}: fully transparent — did the render fail?")
    x0, y0, x1, y1 = box

    sidecar = os.path.splitext(path)[0] + ".json"
    if os.path.exists(sidecar):
        with open(sidecar, encoding="utf-8") as fh:
            r = json.load(fh)
        rx, ry = int(r["x"]), int(r["y"])
        rw, rh = int(r["w"]), int(r["h"])
        if rx < x0 - 1 or ry < y0 - 1 or rx + rw > x1 + 1 or ry + rh > y1 + 1:
            raise SystemExit(
                f"{path}: QML says the capsule is ({rx}, {ry}, {rw}, {rh}) but the pixels "
                f"only reach ({x0}, {y0}, {x1 - x0}, {y1 - y0}) — render and geometry disagree"
            )
        print(f"  {os.path.basename(path)}: silhouette ({x0}, {y0}, {x1 - x0}, {y1 - y0}) "
              f"covers QML rect ({rx}, {ry}, {rw}, {rh})")

    return im.crop((max(0, x0 - PAD), max(0, y0 - PAD),
                    min(w, x1 + PAD), min(h, y1 + PAD)))


def data_uri(im: Image.Image) -> str:
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def main() -> None:
    figures = []
    missing = []
    for name, caption in SHOTS:
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            missing.append(name)
            continue
        im = crop(path)
        figures.append(
            '    <figure>\n'
            f'      <img src="{data_uri(im)}" width="{im.width}" height="{im.height}" '
            f'alt="{caption.replace("<b>", "").replace("</b>", "").split(" — ")[0]}">\n'
            f'      <figcaption>{caption}</figcaption>\n'
            "    </figure>"
        )
    if missing:
        raise SystemExit("missing screenshots: " + ", ".join(missing))

    # The shared art the app, exe and installer icons are generated from,
    # embedded like everything else so the preview stays one self-contained file.
    cand_hero = [
        os.path.normpath(os.path.join(HERE, "..", "app_art_assets", "hero_1536x864.png")),
        os.path.join(HERE, "app_art_assets", "hero_1536x864.png"),
    ]
    hero = next((h for h in cand_hero if os.path.exists(h)), cand_hero[0])
    if os.path.exists(hero):
        him = Image.open(hero).convert("RGB")
        him.thumbnail((900, 900), Image.LANCZOS)
        figures.append(
            '    <figure>\n'
            f'      <img src="{data_uri(him)}" width="{him.width}" '
            f'height="{him.height}" alt="EkPill hero art">\n'
            '      <figcaption><b>Hero art</b> — from <code>app_art_assets</code>, '
            'the same source the app, exe and installer icons are built from.</figcaption>\n'
            "    </figure>"
        )

    # Same art as the browser tab, embedded so the file stays self-contained.
    favicon_uri = ""
    cand_fav = [
        os.path.normpath(os.path.join(HERE, "..", "app_art_assets", "icon_32x32.png")),
        os.path.join(HERE, "app_art_assets", "icon_32x32.png"),
    ]
    fav = next((f for f in cand_fav if os.path.exists(f)), cand_fav[0])
    if os.path.exists(fav):
        favicon_uri = data_uri(Image.open(fav).convert("RGB"))

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>EkPill &mdash; rendered states</title>
<link rel="icon" type="image/png" href="{favicon_uri}">
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; background:#101012; color:#eee; font:14px/1.5 "Segoe UI", system-ui, sans-serif; }}
  header {{ padding:22px 26px 4px; }}
  h1 {{ margin:0 0 5px; font-size:18px; font-weight:600; }}
  p.sub {{ margin:0; color:#9a9aa2; font-size:13px; max-width:76ch; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:16px; padding:18px 26px 34px; }}
  figure {{ margin:0; display:flex; flex-direction:column; background:#1b1b1f;
      border:1px solid #2b2b31; border-radius:12px; padding:12px; }}
  /* Natural size, never stretched: the side-edge shots are 82px wide and a
     full-width capsule is 650 — both are the point, so neither is blown up. */
  figure img {{ max-width:100%; max-height:560px; width:auto; height:auto;
      object-fit:contain; display:block; margin:0 auto; border-radius:8px;
      background:linear-gradient(135deg,#242432 0%,#3a2a3f 45%,#20303a 100%); }}
  figcaption {{ margin-top:9px; color:#b9b9c2; font-size:12.5px; }}
  figcaption b {{ color:#fff; font-weight:600; }}
  code {{ background:#232329; padding:1px 5px; border-radius:4px; }}
</style>
</head>
<body>
  <header>
    <h1>EkPill &mdash; rendered states</h1>
    <p class="sub">Rendered headlessly with <code>python main.py --selftest --pos=... --page=...</code>,
       then cropped to the content. EkPill is genuinely transparent &mdash; the gradient behind each
       shot stands in for your desktop. Both dock edges, the morph, click-through, the focus
       mirror, and the files page are verified by pixel analysis, not by eye.</p>
  </header>
  <div class="grid">
{chr(10).join(figures)}
  </div>
</body>
</html>
"""
    out = os.path.join(HERE, "preview.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"preview: {out} ({os.path.getsize(out)} bytes, {len(figures)} figures)")


if __name__ == "__main__":
    main()
