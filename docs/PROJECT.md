# EkPill — Architecture & Module Reference (`PROJECT.md`)

EkPill is a native Windows 10 & 11 Dynamic Island and Hardware-Notch desktop utility capsule built with **Python 3.13**, **PySide6 / Qt6 QML**, **Win32 API (`ctypes`)**, **Windows Runtime (`winrt`)**, **WASAPI (`pycaw`)**, and **FFmpeg**.

---

## 1. Directory Structure

```text
ekpill/
├── ekpill/
│   ├── main.py                      # Application entry point, QQuickView setup, 60 Hz Win32 hit-test loop
│   ├── build.py                     # PyInstaller & Inno Setup packaging script
│   ├── verify.py                    # 33-test automated architectural & QML self-test suite
│   ├── test_interactive_features.py # 47-test interactive feature & state verification suite
│   ├── operate_all_panels_live.py   # 34-test live end-to-end panel operation & screenshot verifier
│   ├── backend/
│   │   ├── bridge.py                # Primary QObject bridge exposing Properties, Signals & @Slots to QML
│   │   ├── media.py                 # WinRT GlobalSystemMediaTransportControlsSessionManager reader
│   │   ├── audio.py                 # WASAPI master endpoint & per-application session audio mixer
│   │   ├── network.py               # Netsh WLAN scanner, XML profile connector & Bluetooth manager
│   │   ├── files.py                 # Directory browser, Quick Folders, Drive Jumpers & Recycle Bin API
│   │   ├── launcher.py              # Start Menu .lnk indexer & Win32 SHGetFileInfoW icon extractor
│   │   ├── recorder.py              # FFmpeg 30/60 FPS desktop recorder (.mkv staging -> .mp4 remux)
│   │   ├── battery.py               # GetSystemPowerStatus battery percentage & AC charging monitor
│   │   ├── power.py                 # LockWorkStation, SetSuspendState, Restart & Shutdown actions
│   │   ├── hotkeys.py               # Global Win32 RegisterHotKey listener (Ctrl+Alt+L)
│   │   └── settings.py              # Atomic JSON configuration persistence (~/.ekpill_config.json)
│   └── qml/
│       ├── EkPill.qml               # Root capsule shell, SpringAnimation morphing & CurveRenderer ears
│       ├── components/
│       │   ├── Theme.qml            # Singleton design tokens (colors, springs, radii, typography)
│       │   ├── DotMatrixClock.qml   # Custom 5x7 LED dot-matrix digital clock renderer
│       │   ├── AppleBattery.qml     # Proportional fill battery body with lightning bolt indicator
│       │   ├── WaveBars.qml         # 7-bar 60 FPS sinusoidal audio equalizer
│       │   ├── WifiIcon.qml         # Dynamic signal-strength Wi-Fi vector icon
│       │   └── IconButton.qml       # Reusable hover-reactive icon button
│       └── pages/
│           ├── QuickSettings.qml    # Control deck (media strip, volume, 5 tiles, utility bar)
│           ├── MediaPage.qml        # Full WinRT SMTC Now Playing studio with seeker bar
│           ├── AudioView.qml        # Per-application WASAPI volume & mute mixer
│           ├── WifiList.qml         # Wireless SSID list with inline WPA2/WPA3 password prompt
│           ├── BluetoothList.qml    # Bluetooth radio switch & paired device connection list
│           ├── FilesView.qml        # File browser with Quick Folders, Drives & Context Menu
│           ├── AppLauncher.qml      # 4-column Start Menu app grid with live search
│           ├── ScreenRecorder.qml   # 30/60 FPS capture settings, mic toggle & folder selector
│           ├── SettingsPage.qml     # Theme, Screen Edge (Top/Right), Auto-Collapse & Startup toggles
│           └── PowerMenu.qml        # Lock, Sleep, Restart & Shutdown with inline confirmation
├── docs/
│   ├── showcase/                    # 2x Retina widescreen screenshots & dual-format .webm/.gif demos
│   ├── PROJECT.md                   # Architectural documentation
│   ├── TESTING.md                   # Verification & test suite documentation
│   └── UPDATES.md                   # Release changelog
└── website/                         # Standalone zero-framework Vite interactive showcase website
```

---

## 2. Windowing & 60 Hz `WS_EX_TRANSPARENT` Hit-Testing

EkPill renders inside a single borderless, translucent `QQuickView` (`1536x864` logical canvas) anchored to the top of the primary screen with `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool`.

Because the Qt window spans a larger region to accommodate spring rebounds and drop shadows, `main.py` runs a 16 ms (`60 Hz`) Win32 timer (`_update_mouse_passthrough`) that:
1. Queries the physical cursor position via `user32.GetCursorPos` and converts it to logical QML coordinates using the window's `devicePixelRatio()`.
2. Compares the cursor position against the live QML `pill` item's animated bounding box (`pillX`, `pillY`, `pillWidth`, `pillHeight`).
3. Dynamically toggles `WS_EX_TRANSPARENT` via `SetWindowLongW(hwnd, GWL_EXSTYLE, ...)`. When the cursor is outside the capsule, all mouse clicks and wheel events pass transparently to the underlying desktop or application window.
4. Detects outside left/right mouse clicks (`GetAsyncKeyState(VK_LBUTTON)`) while expanded and automatically collapses the capsule.

---

## 3. Panel Dimensions & Spring Physics

All morphing transitions are driven by `SpringAnimation { spring: 3.8; damping: 0.32 }` in `EkPill.qml`:

| State / Page | Top Edge (`edge = "top"`) | Right Edge (`edge = "right"`) | QML Source |
| :--- | :--- | :--- | :--- |
| **Collapsed Capsule** | `332 x 50` px (`370 x 50` when recording) | `58 x 178` px (`58 x 210` when recording) | `EkPill.qml` |
| **Quick Settings (`quick`)** | `425 x 230` px (`425 x 272` when recording) | `425 x 230` px | `pages/QuickSettings.qml` |
| **Media Studio (`media`)** | `465 x 228` px | `465 x 228` px | `pages/MediaPage.qml` |
| **Audio Mixer (`audio`)** | `475 x 539` px | `475 x 539` px | `pages/AudioView.qml` |
| **Wi-Fi Scanner (`wifi`)** | `425 x 422` px | `425 x 422` px | `pages/WifiList.qml` |
| **Bluetooth (`bt`)** | `425 x 418` px | `425 x 418` px | `pages/BluetoothList.qml` |
| **Files Hub (`files`)** | `475 x 470` px | `475 x 470` px | `pages/FilesView.qml` |
| **App Launcher (`launcher`)** | `475 x 460` px | `475 x 460` px | `pages/AppLauncher.qml` |
| **Screen Recorder (`recorder`)** | `425 x 366` px | `425 x 366` px | `pages/ScreenRecorder.qml` |
| **Settings (`settings`)** | `425 x 390` px | `425 x 390` px | `pages/SettingsPage.qml` |
| **Power Menu (`power`)** | `425 x 200` px | `425 x 200` px | `pages/PowerMenu.qml` |
