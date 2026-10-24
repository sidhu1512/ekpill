# EkPill — Release History & Changelog (`UPDATES.md`)

All notable changes to **EkPill** are documented in this file.

---

## v1.3.0 — Hardware-Notch Concave Fillets, WASAPI Mixer & 60 FPS Recorder

### Highlights
- **Per-Application WASAPI Audio Mixer (`AudioView.qml`):** Added full per-app audio session volume sliders (`0–100%`) and mute toggles powered by `pycaw` (`IAudioSessionManager2`), accessible directly from the Quick Settings bottom utility bar.
- **WinRT SMTC Media Studio (`MediaPage.qml`):** Enhanced Now Playing studio with high-DPI album art squircle, interactive timeline seeker, `MM:SS` position/duration timestamps, and 60 FPS 7-bar `WaveBars` equalizer.
- **Right-Edge Upright Vertical Dock:** Switching `screen_edge` to `Right` now docks a `58x178` vertical capsule on the right monitor bezel with top/bottom concave fillets and upright typography (zero rotated text).
- **Crash-Safe 30 / 60 FPS Screen Recorder (`ScreenRecorder.qml` + `recorder.py`):** Captures desktop video via FFmpeg (`ddagrab` / `gdigrab`) into crash-resilient `.mkv` segments with pause/resume and DirectShow microphone support, automatically remuxing to `+faststart .mp4` on stop.
- **Native Files Hub Upgrades (`FilesView.qml`):** Added 7 Quick Folder pills, mounted drive jumpers (`C:`–`Z:`), Name/Date/Size sort toggles, inline New Folder creation, and right-click context menu (`Open`, `Rename`, `Copy`, `Cut`, `Paste`, `Recycle`).

### Verification & Packaging
- Packaged self-contained Windows 10/11 installer `EkPillSetup.exe` (`188,489,585` bytes, SHA-256: `9E03B568ABE83D9CD6DF9A84C043265469292F94BE85DF38A82868FA2AE3F29F`).
- Added 114 automated verification assertions across `verify.py` (33), `test_interactive_features.py` (47), and `operate_all_panels_live.py` (34).

---

## v1.2.0 — Instant App Launcher & Native Win32 Icon Extraction

- Added Start Menu `.lnk` scanner (`launcher.py`) with Win32 `SHGetFileInfoW` + `CreateDIBSection` 32x32 RGBA icon extraction encoded as data-URI PNGs.
- Registered global `Ctrl+Alt+L` hotkey via `user32.RegisterHotKey` on a dedicated Win32 message-pump thread (`hotkeys.py`).
- Added two-step confirmation bar in `PowerMenu.qml` for Lock, Sleep, Restart, and Shutdown.

---

## v1.1.0 — Wireless Radios & Smooth Volume Easing

- Added `WifiList.qml` and `BluetoothList.qml` backed by `netsh wlan` BSSID scanning, XML profile generation for WPA2/WPA3 networks, and WinRT `Windows.Devices.Radios`.
- Upgraded Quick Settings master volume slider with `Behavior on width` cubic-out easing (`140 ms`).

---

## v1.0.0 — Initial Qt6 QML Capsule & 60 Hz Click-Through Engine

- Initial release featuring top-edge hardware notch (`332x50`), `CurveRenderer` MSAAx4 concave fillets, `DotMatrixClock`, `AppleBattery`, and 60 Hz `WS_EX_TRANSPARENT` cursor hit-testing.
