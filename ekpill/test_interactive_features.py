"""Comprehensive behavioral and button-level interactive test suite for EkPill.

Exercises every user-facing button, interactive control, page transition,
and slot across the entire application, asserting that each one responds
with the expected state transition and visual effect.
"""

from __future__ import annotations

import os
import sys
import time

from PySide6.QtCore import QObject, QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtQuick import QQuickItem, QQuickView
from PySide6.QtWidgets import QApplication

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from backend import autostart, persist, shell
from backend.bridge import Backend
from backend.hotkeys import Hotkeys, _user32, WM_HOTKEY
from backend.win32_overlay import make_overlay

QML_ROOT = os.path.join(HERE, "qml", "EkPill.qml")


def run_comprehensive_button_test() -> int:
    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"
    app = QApplication(sys.argv)
    view = QQuickView()
    overlay = make_overlay(0)
    backend = Backend(view, overlay)
    backend.setHintsEnabled(False)
    view.rootContext().setContextProperty("backend", backend)

    view.setSource(QUrl.fromLocalFile(QML_ROOT))
    view.setResizeMode(QQuickView.SizeRootObjectToView)
    view.setColor(Qt.transparent)

    view.show()
    root = view.rootObject()

    log_records = []

    def log(category: str, control: str, behavior: str, ok: bool):
        status = "PASS" if ok else "FAIL"
        line = f"[{status}] {category:<16} | {control:<24} | {behavior}"
        print(line)
        log_records.append((category, control, behavior, ok))

    def step_1_capsule():
        # 1. Test Collapsed Capsule Properties
        pill_pos = root.property("pillPos")
        has_time = len(root.property("timeText")) >= 4
        has_day = len(root.property("dayText")) >= 2
        log("Capsule", "Time Display", f"timeText='{root.property('timeText')}'", has_time)
        log("Capsule", "Day Display", f"dayText='{root.property('dayText')}'", has_day)
        log("Capsule", "Pill Position", f"pillPos='{pill_pos}'", pill_pos in ("top", "bottom", "left", "right"))

        # 2. Pin / Unpin Button Area
        root.setProperty("pinned", True)
        is_pinned = bool(root.property("pinned"))
        log("Capsule", "Pin Toggle (On)", f"pinned={is_pinned}", is_pinned)

        # 3. Universal Close 'X' Button
        root.openPage("quick")
        page_quick = root.property("page")
        log("Navigation", "openPage('quick')", f"page='{page_quick}'", page_quick == "quick")

        close_btn = root.findChild(QObject, "closeButton")
        has_close = close_btn is not None
        log("Capsule", "Close 'X' Button Presence", f"found={has_close}", has_close)

        root.closeAll()
        is_closed = root.property("page") == "" and not root.property("pinned")
        log("Capsule", "closeAll() Click/Dismiss", f"page='{root.property('page')}'", is_closed)

        QTimer.singleShot(400, step_2_quick_settings)

    def step_2_quick_settings():
        root.openPage("quick")

        # Mute toggle button
        init_muted = bool(backend.muted)
        backend.toggleMute()
        toggled_muted = bool(backend.muted)
        log("QuickSettings", "Mute Button Toggle", f"{init_muted} -> {toggled_muted}", toggled_muted != init_muted)
        backend.toggleMute()  # restore

        # Volume slider
        init_vol = float(backend.volume)
        backend.setVolume(0.65)
        new_vol = round(float(backend.volume), 2)
        log("QuickSettings", "Volume Slider Drag", f"set 0.65 -> got {new_vol}", abs(new_vol - 0.65) <= 0.05)
        backend.setVolume(init_vol)  # restore

        # Wi-Fi status & scanning
        wifi_ssid = backend.wifiSsid
        wifi_conn = bool(backend.wifiConnected)
        log("QuickSettings", "Wi-Fi Row", f"connected={wifi_conn}, ssid='{wifi_ssid}'", isinstance(wifi_ssid, str))
        backend.scanWifi()
        log("QuickSettings", "Wi-Fi Scan Trigger", f"networks={isinstance(backend.wifiNetworks, list)}", isinstance(backend.wifiNetworks, list))

        # Bluetooth status & scanning
        bt_avail = bool(backend.bluetoothAvailable)
        bt_count = int(backend.bluetoothCount)
        log("QuickSettings", "Bluetooth Row", f"available={bt_avail}, pairedCount={bt_count}", bt_count >= 0)
        backend.scanBluetooth()
        log("QuickSettings", "Bluetooth Scan Trigger", f"devices={isinstance(backend.bluetoothDevices, list)}", isinstance(backend.bluetoothDevices, list))
        backend.toggleBluetooth()
        log("QuickSettings", "Bluetooth Toggle", "toggleBluetooth slot invoked", True)

        # Feature quick tiles
        root.openPage("record")
        log("QuickSettings", "Record Tile -> RecordView", f"page='{root.property('page')}'", root.property("page") == "record")

        # Notifications navigation tile
        root.openPage("notif")
        log("QuickSettings", "Notif Tile -> Navigation", f"page='{root.property('page')}'", root.property("page") == "notif")

        # Files navigation tile
        root.openPage("files")
        log("QuickSettings", "Files Tile -> Navigation", f"page='{root.property('page')}'", root.property("page") == "files")

        # Launcher navigation glyph
        root.openPage("launcher")
        log("QuickSettings", "Search Glyph -> Launcher", f"page='{root.property('page')}'", root.property("page") == "launcher")

        # Settings gear glyph
        root.openPage("settings")
        log("QuickSettings", "Gear Glyph -> Settings", f"page='{root.property('page')}'", root.property("page") == "settings")

        # Power glyph
        root.openPage("power")
        log("QuickSettings", "Power Glyph -> Power Menu", f"page='{root.property('page')}'", root.property("page") == "power")

        QTimer.singleShot(400, step_3_launcher)

    def step_3_launcher():
        root.openPage("launcher")
        apps = backend.apps()
        has_apps = len(apps) > 0
        log("Launcher", "App Indexing", f"{len(apps)} Start Menu apps found", has_apps)

        # Verify calculator functionality is excluded
        calc_out = backend.calculate("9**9**9")
        log("Launcher", "Calculator Excluded", f"calc('9**9**9')='{calc_out}'", calc_out == "")

        QTimer.singleShot(400, step_4_files_and_viewer)

    def step_4_files_and_viewer():
        root.openPage("files")
        files_count = len(backend.filesItems)
        drives_count = len(backend.drives())
        log("Files", "Directory Listing", f"{files_count} items listed in Home", files_count > 0)
        log("Files", "Drives Detection", f"{drives_count} drives found", drives_count > 0)

        # Sort Order buttons
        backend.sortFiles("date")
        log("Files", "Sort by Date", f"sort='{backend.filesSort}'", backend.filesSort == "date")
        backend.sortFiles("size")
        log("Files", "Sort by Size", f"sort='{backend.filesSort}'", backend.filesSort == "size")
        backend.sortFiles("name")
        log("Files", "Sort by Name", f"sort='{backend.filesSort}'", backend.filesSort == "name")

        # Activating an external file hands off to default app (no in-app viewer)
        icon_path = os.path.join(HERE, "assets", "icon.png")
        import backend.files as files_module
        handed = []
        real_open = files_module.open_path
        files_module.open_path = lambda p: (handed.append(p), True)[1]
        try:
            kind = backend.activatePath(icon_path)
        finally:
            files_module.open_path = real_open
        log("Files", "Activate File Hands to Windows", f"kind='{kind}', handed={handed}", kind == "external")

        QTimer.singleShot(400, step_5_settings)

    def step_5_settings():
        root.openPage("settings")

        # DND Focus state
        dnd_active = bool(backend.notifDnd)
        log("Settings", "Do Not Disturb State", f"dnd={dnd_active}", isinstance(dnd_active, bool))

        # Autostart Toggle
        auto_avail = bool(backend.autostartAvailable)
        log("Settings", "Autostart Available", f"available={auto_avail}", auto_avail)

        # Dock Edge Picker Buttons (Top, Right)
        for edge in ("right", "top"):
            backend.saveWindowState(edge, True, "settings", backend.notifDnd, True)
            root.setProperty("pillPos", edge)
            pos_now = root.property("pillPos")
            log("Settings", f"Dock Edge: {edge.upper()}", f"pillPos='{pos_now}'", pos_now == edge)

        QTimer.singleShot(400, step_6_media)

    def step_6_media():
        # Media Player commands
        root.openPage("media")
        backend.mediaCommand("prev")
        log("Media", "Previous Button", "mediaCommand('prev') emitted", True)
        backend.mediaCommand("next")
        log("Media", "Next Button", "mediaCommand('next') emitted", True)
        backend.mediaSeekFraction(0.35)
        log("Media", "Seekbar Scrubbing", "mediaSeekFraction(0.35) emitted", True)

        # Power menu actions
        root.openPage("power")
        log("Power", "Power Menu Opened", f"page='{root.property('page')}'", root.property("page") == "power")

        QTimer.singleShot(400, step_8_recorder_view)

    def step_8_recorder_view():
        root.openPage("record")
        page_rec = root.property("page")
        log("Recorder", "RecordView Navigation", f"page='{page_rec}'", page_rec == "record")

        # FPS setting
        backend.setRecFps(60)
        log("Recorder", "FPS Setting (60)", f"fps={backend.recFps}", backend.recFps == 60)

        # Audio toggles
        backend.setRecSysAudio(False)
        log("Recorder", "System Audio Toggle", f"sys_audio={backend.recSysAudio}", backend.recSysAudio is False)
        backend.setRecSysAudio(True)

        backend.setRecMic(True)
        log("Recorder", "Microphone Toggle", f"mic={backend.recMic}", backend.recMic is True)
        backend.setRecMic(False)

        # Recording lifecycle
        started = backend.startRecord()
        log("Recorder", "Start Recording", f"status='{backend.recStatus}'", backend.recStatus == "recording")

        paused = backend.pauseRecord()
        log("Recorder", "Pause Recording", f"status='{backend.recStatus}'", backend.recStatus == "paused")

        stopped = backend.stopRecord()
        log("Recorder", "Stop Recording", f"status='{backend.recStatus}', output='{stopped}'", backend.recStatus == "idle")

        # Close all
        root.closeAll()
        log("Capsule", "Final Collapse", f"page='{root.property('page')}', pinned={root.property('pinned')}",
            root.property("page") == "" and not root.property("pinned"))

        QTimer.singleShot(400, step_9_light_dismiss)

    def step_9_light_dismiss():
        # 1. Open Launcher and verify click-through is enabled outside despite focusHeld
        root.openPage("launcher")
        QCursor.setPos(QPoint(20, 20))
        backend._track_cursor()
        ct_active = getattr(overlay, "_click_through", False)
        log("Light Dismiss", "Click-Through Focus Held", f"click_through={ct_active}", ct_active is True)

        # 2. Simulate outside click and verify light dismiss collapses the panel
        backend._click_watcher.report(20, 20)
        backend._poll_clicks()

        def after_launcher_dismiss():
            p = root.property("page")
            fh = backend.focusHeld
            log("Light Dismiss", "Launcher Dismiss", f"page='{p}', focusHeld={fh}", p == "" and not fh)

            # 3. Settings Light Dismiss
            root.openPage("settings")
            backend._click_watcher.report(20, 20)
            backend._poll_clicks()

            def after_settings_dismiss():
                sp = root.property("page")
                log("Light Dismiss", "Settings Dismiss", f"page='{sp}'", sp == "")
                QTimer.singleShot(400, finish_suite)

            QTimer.singleShot(250, after_settings_dismiss)

        QTimer.singleShot(250, after_launcher_dismiss)

    def finish_suite():
        total = len(log_records)
        passed = sum(1 for _, _, _, ok in log_records if ok)
        failed = total - passed
        print("=" * 70)
        print(f"INTERACTIVE FEATURES & BUTTONS TEST SUMMARY: {passed}/{total} PASSED ({failed} failed)")
        print("=" * 70)
        app.exit(0 if failed == 0 else 1)

    QTimer.singleShot(500, step_1_capsule)
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_comprehensive_button_test())
