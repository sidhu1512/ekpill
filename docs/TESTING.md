# EkPill — Verification & Test Suite Guide (`TESTING.md`)

EkPill ships with three automated Python verification suites totaling **114 assertions**, plus a standalone asset and link verifier for the interactive showcase website.

---

## 1. Automated Desktop Verification Suites (`114 / 114 Passing`)

### Suite A: Architectural & Self-Test Suite (`ekpill/verify.py` — 33 Checks)
Validates module imports, backend service initialization, QML syntax loading across all 9 pages, and offscreen/live rendering of the capsule:

```powershell
python ekpill/verify.py
```

**What it checks:**
- All 11 Python backend modules (`bridge`, `media`, `audio`, `network`, `files`, `launcher`, `recorder`, `battery`, `power`, `hotkeys`, `settings`) import cleanly.
- Every QML component and page loads with `QQuickView` status `Ready` (`loaderStatus == 1`) and zero QML warnings or errors.
- Self-test rendering (`main.py --selftest`) captures pixel-accurate PNGs and JSON telemetry for `pill`, `quick`, `media`, `audio`, `files`, `launcher`, `settings`, `recorder`, and `power`.

### Suite B: Interactive Feature & Backend Suite (`ekpill/test_interactive_features.py` — 47 Checks)
Tests live two-way interactions between QML panels and the Python `Backend` bridge:

```powershell
python ekpill/test_interactive_features.py
```

**What it checks:**
- Volume slider adjustments (`set_volume`, `toggle_mute`) and per-application WASAPI session controls (`set_app_volume`, `toggle_app_mute`).
- Files Hub navigation across all 7 Quick Folders (`Home`, `Desktop`, `Documents`, `Downloads`, `Pictures`, `Music`, `Videos`), drive enumeration, sorting (`name`, `date`, `size`), search filtering, folder creation, rename, copy/paste, and Recycle Bin deletion.
- App Launcher Start Menu `.lnk` indexing, Win32 `SHGetFileInfoW` base64 PNG icon extraction, and search filtering.
- Screen Recorder FPS selection (`30` / `60`), target folder switching (`Videos`, `Pictures`, `Desktop`), and microphone toggle.
- Settings persistence (`theme`, `screen_edge` Top/Right, `collapse_delay`, `start_with_windows`).

### Suite C: Live Panel Operation & Pixel Audit (`ekpill/operate_all_panels_live.py` — 34 Checks)
Launches the real desktop overlay and drives every panel state transition end-to-end while verifying rendered pixel variance and non-zero bounding boxes:

```powershell
python ekpill/operate_all_panels_live.py
```

---

## 2. Showcase Website Asset & Integrity Verifier

The interactive showcase website in `website/` includes an automated asset and integrity verification script (`website/scripts/verify-assets.mjs`):

```powershell
npm run website:build
npm run website:verify
```

**What it checks:**
- Every `<img src="...">`, `<video src="...">`, and `<source srcset="...">` in `README.md`, `website/index.html`, `website/src/config.js`, and `website/src/main.js` exists on disk and is non-empty (`> 1024` bytes).
- All 8 flagship showcase PNGs and 5 dual-format `.webm` + `.gif` recordings exist in both `docs/showcase/` and `website/public/showcase/`.
- All 16 paired `-light.png` / `-dark.png` gallery screenshots exist in `website/public/shots/`.
- Zero Unicode emojis or dingbats exist in `README.md`, `website/index.html`, `website/src/main.js`, or `website/src/style.css`.
- Production Vite bundle (`website/dist/index.html`) compiles cleanly.
