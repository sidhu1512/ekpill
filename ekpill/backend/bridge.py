"""The single QObject the QML talks to.

It owns the polling timers, keeps a small cached model of the machine, and
exposes everything as QML properties + invokable slots. It also drives the
window's click-through state: while the pointer is away from the capsule the
whole window lets clicks fall through to whatever is behind it.
"""

from __future__ import annotations

import asyncio
import os
import time

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot, QUrl, Qt
from PySide6.QtGui import QCursor, QFontDatabase, QDesktopServices
from PySide6.QtWidgets import QApplication

from . import audio, autostart, escape, mouse_hook, persist, recorder, shell, system
from . import files as filebrowser
from .media import AsyncLoop, MediaService
from .shell import BluetoothService


def _icon_font() -> str:
    """Windows ships an icon face; pick whichever this build has."""
    try:
        families = set(QFontDatabase.families())
    except Exception:
        return "Segoe UI"
    for name in ("Segoe Fluent Icons", "Segoe MDL2 Assets", "Segoe UI Symbol"):
        if name in families:
            return name
    return "Segoe UI"


class Backend(QObject):
    # battery
    batteryChanged = Signal()
    volumeChanged = Signal()
    mediaChanged = Signal()
    wifiChanged = Signal()
    bluetoothChanged = Signal()
    hoverChanged = Signal()
    clockChanged = Signal()
    focusChanged = Signal()        # Windows' own Do Not Disturb state moved
    hotkey = Signal(str)          # a registered global hotkey was pressed
    escapePressed = Signal()      # Escape was pressed, and it is ours to use
    outsideClicked = Signal()     # Light Dismiss: user clicked outside the capsule
    focusHeldChanged = Signal()
    autostartChanged = Signal()
    hotkeysChanged = Signal()
    escapeChanged = Signal()      # the "Escape closes" switch moved
    hintChanged = Signal()        # the one-time hint was shown
    filesChanged = Signal()
    audioStreamsChanged = Signal()
    audioLevelsChanged = Signal()
    recordChanged = Signal()
    wifiNetworksChanged = Signal()
    bluetoothDevicesChanged = Signal()

    # Thread-safe queued worker signals for off-thread callbacks
    _safeWifiSignal = Signal(object)
    _safeMediaSignal = Signal(object)
    _safeBtSignal = Signal(object)
    _safeWifiScanSignal = Signal(object)
    _safeWifiConnectSignal = Signal(object, object)
    _safeBtScanSignal = Signal(object)

    def __init__(self, window, overlay) -> None:
        super().__init__()
        self._window = window
        self._overlay = overlay

        self._battery = (100, True, False)
        self._volume = 0.5
        self._muted = False
        self._media: dict = {"active": False}
        self._wifi: dict = {"connected": False, "ssid": "", "signal": 0, "iface": ""}
        self._bt: dict = {"available": False, "on": False, "count": 0}
        # Do Not Disturb belongs to Windows. Read it, mirror it, never invent
        # it: EkPill used to keep a private boolean that drifted from the
        # real switcher within one tap. The notification list itself is not
        # mirrored at all — see the note further down.
        self._dnd = shell.read_focus_mode()
        self._hot = (0, 0, 0, 0)
        self._hovered = False
        self._focus_held = False
        self._apps_cache: list = []
        self._icon_font = _icon_font()
        self._hotkeys = None      # attached by main.py once registered
        # Files open at the user's home; nothing is written, only read.
        self._files_sort = "name"
        self._files = filebrowser.list_dir(filebrowser.UMBRELLA)
        self._file_clip: dict = {}      # one item, copy or cut, in memory only

        # How EkPill is closed: Escape (the default), an optional
        # combination, or both. The switch is here for the people who want
        # Escape to belong to every app they open.
        saved = persist.load()
        self._esc_on = bool(saved.get("esc", True))
        # The close combination lives in the hotkeys map like the others; it
        # is the only one with no default, so "" means "nothing is bound".
        self._close_spec = str((saved.get("hotkeys") or {}).get("close", "")).strip()
        self._hint_seen = bool(saved.get("hint", False))
        # The one-time hint is a measured-run hazard: a card that appears
        # once would be in every screenshot of the first run and in none of
        # the later ones. main.py turns it off for selftest/probe runs.
        self._hints_on = True

        # Thread-safe worker queue connections
        self._safeWifiSignal.connect(self._apply_wifi, Qt.QueuedConnection)
        self._safeMediaSignal.connect(self._apply_media, Qt.QueuedConnection)
        self._safeBtSignal.connect(self._apply_bt, Qt.QueuedConnection)
        self._safeWifiScanSignal.connect(self._apply_wifi_scan, Qt.QueuedConnection)
        self._safeWifiConnectSignal.connect(self._apply_wifi_connect, Qt.QueuedConnection)
        self._safeBtScanSignal.connect(self._apply_bt_scan, Qt.QueuedConnection)

        self._loop = AsyncLoop()
        self._volume_service = system.VolumeService()
        self._media_service = MediaService(self._on_media)
        self._bt_service = BluetoothService(self._loop, self._on_bt)
        # Notifications are deliberately not mirrored any more: EkPill
        # is a control surface, not a second Action Center. Windows keeps its
        # own list; only the focus/DND state is read (that stays in _dnd).

        # system poll ------------------------------------------------------
        self._sys_timer = QTimer(self)
        self._sys_timer.setInterval(1500)
        self._sys_timer.timeout.connect(self._poll_system)
        self._sys_timer.start()
        self._poll_system()

        # wi-fi poll off-thread so netsh never blocks the Qt GUI loop --------
        self._loop.run(self._async_wifi_poll())

        # pointer tracking drives hover + click-through --------------------
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(40)
        self._cursor_timer.timeout.connect(self._track_cursor)
        self._cursor_timer.start()

        # Escape, watched without taking it ------------------------------
        # EkPill's window never holds the keyboard, so this is the only
        # way a page ever hears about the key. The watcher sees the key and
        # hands it straight on: the app the user is typing in still gets
        # its Escape.
        self._escape = escape.EscapeWatcher()
        if not self._escape.install():
            # The hook was refused (a locked-down machine, an old Windows).
            # The watcher falls back to reading the keyboard's state, which
            # is less exact but never takes the key either.
            print("escape: the keyboard hook was refused, "
                  "falling back to the state poll")
        self._escape_timer = QTimer(self)
        self._escape_timer.setInterval(30)
        self._escape_timer.timeout.connect(self._poll_escape)
        self._escape_timer.start()

        # Light Dismiss, watched without blocking other applications --
        self._click_watcher = mouse_hook.ClickWatcher()
        if not self._click_watcher.install():
            print("mouse: click watcher hook refused, falling back to state poll")
        self._click_timer = QTimer(self)
        self._click_timer.setInterval(25)
        self._click_timer.timeout.connect(self._poll_clicks)
        self._click_timer.start()

        # Audio visualizer & per-app streams --------------------------
        self._audio_service = audio.AudioService()
        self._audio_streams: list = []
        self._audio_levels: list = [0.06] * 7
        self._audio_peak: float = 0.0
        self._audio_timer = None

        # Screen Recorder ---------------------------------------------
        self._recorder = recorder.ScreenRecorder()
        saved = persist.load()
        self._recorder.fps = int(saved.get("rec_fps", 60))
        if self._recorder.fps not in (30, 60):
            # 120 fps was offered by an older build and only ever produced
            # unplayable files; migrate the stored preference.
            self._recorder.fps = 60
        self._recorder.dir = str(saved.get("rec_dir") or recorder.default_video_dir())
        self._recorder.sys_audio = bool(saved.get("rec_sys_audio", True))
        self._recorder.mic = bool(saved.get("rec_mic", False))
        self._recorder.mic_device = str(saved.get("rec_mic_device", ""))
        self._rec_time_timer = QTimer(self)
        self._rec_time_timer.setInterval(1000)
        self._rec_time_timer.timeout.connect(self._tick_recorder)

        # Inline Wi-Fi and Bluetooth scan & connect -------------------
        self._wifi_networks: list = []
        self._wifi_busy: bool = False
        self._wifi_error: str = ""
        self._bt_devices: list = []
        self._bt_busy: bool = False
        self._bt_error: str = ""
        self._showcase_seeded: bool = False

    def seed_showcase_data(self) -> None:
        """Populate deterministic high-density domain data for headless selftest and showcase captures."""
        self._showcase_seeded = True
        art_candidates = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "app_art_assets", "icon_256x256.png")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "icon.png")),
        ]
        art_path = ""
        for cand in art_candidates:
            if os.path.isfile(cand):
                art_path = cand
                break
        if not self._media.get("active"):
            self._media = {
                "active": True,
                "playing": True,
                "title": "Midnight City",
                "artist": "M83 — Hurry Up, We're Dreaming",
                "art": art_path,
                "position": 102.0,
                "duration": 243.0,
                "positionText": "1:42",
                "durationText": "4:03",
                "seekable": True,
            }
            self.mediaChanged.emit()
        self._audio_levels = [0.44, 0.78, 0.94, 0.65, 0.86, 0.58, 0.36]
        self._audio_peak = 0.74
        self.audioLevelsChanged.emit()
        self.refreshAudioStreams()
        if not self._wifi.get("connected"):
            self._wifi = {"available": True, "connected": True, "ssid": "Studio-5G", "signal": 94}
            self.wifiChanged.emit()
        if not self._wifi_networks:
            self._wifi_networks = [
                {"ssid": "Studio-5G", "signal": 94, "secure": True, "connected": True},
                {"ssid": "EkPill-Lab-WiFi6", "signal": 82, "secure": True, "connected": False},
                {"ssid": " Fiber-Optic-2.4G", "signal": 68, "secure": True, "connected": False},
                {"ssid": "Guest-Mesh", "signal": 51, "secure": False, "connected": False},
            ]
            self.wifiNetworksChanged.emit()
        if not self._bt_devices:
            self._bt = {"available": True, "on": True, "count": 3}
            self._bt_devices = [
                {"name": "AirPods Pro (2nd Gen)", "mac": "A4:83:E7:21:9C:04", "connected": True, "paired": True, "category": "Audio"},
                {"name": "Keychron K2 Pro", "mac": "D8:3A:DD:64:18:B2", "connected": True, "paired": True, "category": "Keyboard"},
                {"name": "MX Master 3S", "mac": "7C:B2:7D:91:40:1F", "connected": False, "paired": True, "category": "Mouse"},
            ]
            self.bluetoothChanged.emit()
            self.bluetoothDevicesChanged.emit()

    # ---------------------------------------------------------- autostart
    def attachHotkeys(self, hotkeys) -> None:
        """main.py hands the registration object over for rebinding."""
        self._hotkeys = hotkeys
        self.hotkeysChanged.emit()

    def shutdown(self) -> None:
        """Let go of everything that outlives the window.

        The keyboard hook is the one that matters: a hook left installed
        keeps the process alive in the system's eyes, and the key it watches
        was never ours to keep.
        """
        self._escape.uninstall()
        self._escape_timer.stop()
        self._click_watcher.uninstall()
        self._click_timer.stop()
        if hasattr(self, "_media_service") and self._media_service:
            self._media_service.cleanup()
        if hasattr(self, "_recorder") and self._recorder and self._recorder.active:
            self._recorder.stop()

    @Property(bool, constant=True)
    def autostartAvailable(self) -> bool:
        return autostart.startup_dir() != "" and os.path.isdir(autostart.startup_dir())

    @Property(bool, notify=autostartChanged)
    def autostart(self) -> bool:
        return autostart.is_enabled()

    @Slot(bool)
    def setAutostart(self, on: bool) -> None:
        autostart.set_enabled(bool(on))
        self.autostartChanged.emit()   # re-read from disk either way

    # --------------------------------------------------------------- hotkeys
    @Property(str, notify=hotkeysChanged)
    def hotkeyLauncher(self) -> str:
        if self._hotkeys is None:
            return ""
        return self._hotkeys.specs.get("launcher", "")

    @Property(str, notify=hotkeysChanged)
    def hotkeyClose(self) -> str:
        """The combination that closes EkPill from anywhere, if any."""
        if self._hotkeys is None:
            return self._close_spec
        return self._hotkeys.specs.get("close", self._close_spec)

    def _save_hotkeys(self) -> None:
        """Write the whole map back.

        Every combination is written, not just the one that changed: the
        close key shares the map with the launcher, so a save that dropped it
        would silently unbind it.
        """
        if self._hotkeys is None:
            return
        persist.update(hotkeys={
            k: v for k, v in self._hotkeys.specs.items()
            if k in persist.HOTKEY_NAMES})

    @Slot(str, str, result=bool)
    def setHotkey(self, name: str, spec: str) -> bool:
        """Rebind. False means Windows refused it (or it is not parseable) and
        the previous combination is still the live one."""
        if self._hotkeys is None:
            return False
        spec = spec.strip() if isinstance(spec, str) else ""
        if not spec and name != "close":
            # The launcher is not optional: an empty combination would leave
            # EkPill with no way to be summoned.
            return False
        ok = self._hotkeys.rebind(name, spec)
        if ok:
            # The registration succeeded, so it is now the user's choice.
            self._save_hotkeys()
        self.hotkeysChanged.emit()
        return ok

    # --------------------------------------------------------- closing keys
    @Property(bool, notify=escapeChanged)
    def escapeEnabled(self) -> bool:
        """Whether Escape closes EkPill while the pointer is on it."""
        return self._esc_on

    @Slot(bool)
    def setEscapeEnabled(self, on: bool) -> None:
        on = bool(on)
        if on == self._esc_on:
            return
        self._esc_on = on
        persist.update(esc=on)
        self.escapeChanged.emit()

    @Slot(str, result=bool)
    def setCloseKey(self, spec: str) -> bool:
        """Bind (or unbind) the combination that closes EkPill.

        Unlike Escape, this one is a global hotkey: it closes EkPill
        whether the pointer is on it or not, because EkPill owns the
        combination the way it owns the launcher key.

        An empty combination unbinds it, which is the state it starts in.
        """
        if self._hotkeys is None:
            return False
        ok = self._hotkeys.rebind("close", spec)
        if ok:
            self._close_spec = self._hotkeys.specs.get("close", "")
            self._save_hotkeys()
        self.hotkeysChanged.emit()
        return ok

    # ---------------------------------------------------------- the hint
    @Property(bool, notify=hintChanged)
    def hintPending(self) -> bool:
        """True until the one-time "Esc closes" hint has been shown."""
        return self._hints_on and not self._hint_seen

    @Property(bool, notify=hintChanged)
    def hintsEnabled(self) -> bool:
        """Whether the one-time hint may be shown at all."""
        return self._hints_on

    @Slot(bool)
    def setHintsEnabled(self, on: bool) -> None:
        """Measured runs turn the hint off: it would land in a screenshot."""
        on = bool(on)
        if on == self._hints_on:
            return
        self._hints_on = on
        self.hintChanged.emit()

    @Slot()
    def markHintSeen(self) -> None:
        self._hint_seen = True
        persist.update(hint=True)
        self.hintChanged.emit()

    # ------------------------------------------------------------- utilities
    @Slot(str)
    def openUrl(self, url: str) -> None:
        u = str(url).strip()
        if not (u.startswith("http://") or u.startswith("https://")):
            u = "https://" + u
        QDesktopServices.openUrl(QUrl(u))

    # ------------------------------------------------------------------ files
    @Property(list, notify=filesChanged)
    def filesItems(self) -> list:
        return list(self._files.get("items", []))

    @Property(str, notify=filesChanged)
    def filesPath(self) -> str:
        return str(self._files.get("path", ""))

    @Property(str, notify=filesChanged)
    def filesName(self) -> str:
        return str(self._files.get("name", ""))

    @Property(str, notify=filesChanged)
    def filesParent(self) -> str:
        return str(self._files.get("parent", ""))

    @Property(str, notify=filesChanged)
    def filesError(self) -> str:
        return str(self._files.get("error", ""))

    @Property(int, notify=filesChanged)
    def filesTotal(self) -> int:
        return int(self._files.get("total", 0))

    @Property(int, notify=filesChanged)
    def filesShown(self) -> int:
        return int(self._files.get("shown", 0))

    @Property(str, notify=filesChanged)
    def filesSort(self) -> str:
        return self._files_sort

    @Slot(result="QVariantList")
    def bookmarks(self) -> list:
        return filebrowser.bookmarks()

    @Slot(result="QVariantList")
    def drives(self) -> list:
        return filebrowser.drives()

    @Slot(str)
    def browse(self, path: str) -> None:
        """Open a folder without breaking the UI if permission is denied."""
        if not filebrowser.can_enter(path):
            return
        listing = filebrowser.list_dir(path, self._files_sort)
        if listing.get("error") and listing.get("denied"):
            return
        self._files = listing
        self.filesChanged.emit()

    @Slot()
    def browseUp(self) -> None:
        above = filebrowser.parent(self._files.get("path", ""))
        if above:
            self.browse(above)

    @Slot(str)
    def sortFiles(self, order: str) -> None:
        if order in filebrowser.SORTS and order != self._files_sort:
            self._files_sort = order
            self.browse(self._files.get("path", ""))

    @Slot(int, result=str)
    def activateFile(self, index: int) -> str:
        """What a click does: descend, or hand to the default app.

        Returning the kind keeps the folder/file decision in one place rather
        than duplicating it in QML.
        """
        items = self._files.get("items", [])
        if not 0 <= int(index) < len(items):
            return ""
        return self.activatePath(items[int(index)]["path"])

    @Slot(str, result=str)
    def activatePath(self, path: str) -> str:
        """What a click does, addressed by path.

        The context menu keeps paths rather than row indices: a sort or a
        deletion between opening the menu and choosing from it would make an
        index point at a different file.
        """
        path = os.path.abspath(str(path))
        if not os.path.exists(path):
            return ""
        if os.path.isdir(path):
            # An ACL-denied folder is not an error screen: it is a row that
            # does nothing, dimmed before the click ever happened.
            if not filebrowser.can_enter(path):
                return ""
            self.browse(path)
            return "folder"
        # No in-app image/text viewer: hand every file to whatever Windows
        # has registered for it, exactly like a double-click in Explorer.
        filebrowser.open_path(path)
        return "external"

    @Slot(str)
    def openExternal(self, path: str) -> None:
        filebrowser.open_path(path)

    @Slot(str, result=bool)
    def trashFile(self, path: str) -> bool:
        ok = filebrowser.trash(path)
        if ok:
            self.browse(self._files.get("path", ""))
        return ok

    @Slot(str, bool)
    def copyFile(self, path: str, cut: bool) -> None:
        """Remember one item for the next paste — copy or cut, like Explorer."""
        path = os.path.abspath(str(path))
        if os.path.exists(path):
            self._file_clip = {"path": path, "cut": bool(cut)}
            self.filesChanged.emit()

    @Property(bool, notify=filesChanged)
    def fileClipActive(self) -> bool:
        return bool(self._file_clip)

    @Property(str, notify=filesChanged)
    def fileClipName(self) -> str:
        return os.path.basename(self._file_clip.get("path", ""))

    @Property(bool, notify=filesChanged)
    def fileClipCut(self) -> bool:
        return bool(self._file_clip.get("cut"))

    @Slot(result=str)
    def pasteFiles(self) -> str:
        """Paste into the folder on screen. "" means it worked."""
        src = self._file_clip.get("path", "")
        if not src:
            return "Nothing to paste"
        if not os.path.exists(src):
            self._file_clip = {}
            self.filesChanged.emit()
            return "The copied item no longer exists"
        dest = self._files.get("path", "")
        if self._file_clip.get("cut"):
            new_path, error = filebrowser.move(src, dest)
            if new_path:
                self._file_clip = {}     # a move consumes the clipboard
        else:
            new_path, error = filebrowser.copy(src, dest)
        if new_path:
            self.browse(dest)
        return error

    @Slot(result=str)
    def newFolder(self) -> str:
        path, _error = filebrowser.new_folder(self._files.get("path", ""))
        if path:
            self.browse(self._files.get("path", ""))
        return path or ""

    @Slot(str, str, result=str)
    def renamePath(self, path: str, new_name: str) -> str:
        ok, error = filebrowser.rename(path, new_name)
        if ok:
            self.browse(self._files.get("path", ""))
            return ""
        return error

    # ---------------------------------------------------------------- polling
    def _poll_system(self) -> None:
        battery = system.read_battery()
        if battery != self._battery:
            self._battery = battery
            self.batteryChanged.emit()

        volume, muted = self._volume_service.get()
        if abs(volume - self._volume) > 0.001 or muted != self._muted:
            self._volume = volume
            self._muted = muted
            self.volumeChanged.emit()

        focus = shell.read_focus_mode()
        if focus != self._dnd:
            self._dnd = focus
            self.focusChanged.emit()

    @Slot(object)
    def _apply_wifi(self, wifi: dict) -> None:
        if wifi != self._wifi:
            self._wifi = wifi
            self.wifiChanged.emit()

    @Slot(object)
    def _apply_media(self, state: dict) -> None:
        if self._showcase_seeded and not state.get("active"):
            return
        self._media = state
        self.mediaChanged.emit()

    @Slot(object)
    def _apply_bt(self, state: dict) -> None:
        if self._showcase_seeded and not state.get("count"):
            return
        self._bt = state
        self.bluetoothChanged.emit()

    @Slot(object)
    def _apply_wifi_scan(self, nets: list) -> None:
        if self._showcase_seeded and len(nets) < 2 and self._wifi_networks:
            self._wifi_busy = False
            self.wifiNetworksChanged.emit()
            return
        self._wifi_networks = nets
        self._wifi_busy = False
        self.wifiNetworksChanged.emit()

    @Slot(object, object)
    def _apply_wifi_connect(self, ok: bool, err: str) -> None:
        self._wifi_error = "" if ok else err
        self._wifi_busy = False
        self.wifiNetworksChanged.emit()
        self.wifiChanged.emit()

    @Slot(object)
    def _apply_bt_scan(self, devs: list) -> None:
        if self._showcase_seeded and len(devs) < 2 and self._bt_devices:
            self._bt_busy = False
            self.bluetoothDevicesChanged.emit()
            return
        self._bt_devices = devs
        self._bt_busy = False
        self.bluetoothDevicesChanged.emit()

    async def _async_wifi_poll(self) -> None:
        """Poll netsh on a background worker thread so the GUI never drops frames."""
        while True:
            try:
                wifi = await self._loop.loop.run_in_executor(None, shell.read_wifi)
                self._safeWifiSignal.emit(wifi)
            except Exception:
                pass
            await asyncio.sleep(4.0)

    # ------------------------------------------------------------ callbacks
    def _on_media(self, state: dict) -> None:
        self._safeMediaSignal.emit(state)

    def _on_bt(self, state: dict) -> None:
        self._safeBtSignal.emit(state)

    def _cursor_logical(self) -> tuple[float, float]:
        """The pointer in Qt's logical pixels, whatever the display scale.

        QCursor.pos() hands back *native* pixels in this process once the
        window is per-monitor DPI aware, while the hot region comes from QML
        in logical pixels. On a 125% screen that put the pointer 240 px to
        the right of the pill — hover saw nothing on the first pass and only
        "worked" when the pointer happened to drift into the smaller logical
        rectangle. GetCursorPos + the screen DPR is the reliable direction.
        """
        try:
            import ctypes
            from ctypes import wintypes

            point = wintypes.POINT()
            ok = ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            if ok and (point.x != 0 or point.y != 0):
                return self._physical_to_logical(point.x, point.y,
                                                 QApplication.screens())
        except Exception:
            pass
        pos = QCursor.pos()
        return float(pos.x()), float(pos.y())

    def _track_cursor(self) -> None:
        x, y, w, h = self._hot
        cursor_x, cursor_y = self._cursor_logical()
        origin = self._window.position()
        local_x = cursor_x - origin.x()
        local_y = cursor_y - origin.y()
        pad = 12          # the pill's rounded edge must be grabbable, not a pixel line
        inside = (
            w > 0 and h > 0
            and x - pad <= local_x <= x + w + pad
            and y - pad <= local_y <= y + h + pad
        )
        if inside != self._hovered:
            self._hovered = inside
            self.hoverChanged.emit()
        # Give clicks back to the desktop whenever the pointer is not on the capsule.
        self._overlay.set_click_through(not inside)

    @staticmethod
    def _physical_to_logical(cx: float, cy: float, screens, primary=None) -> tuple[float, float]:
        """Convert physical screen coordinates to Qt logical device-independent coordinates."""
        if not screens:
            return float(cx), float(cy)

        for s in screens:
            dpr = s.devicePixelRatio()
            geom = s.geometry()  # logical QRect
            phys_x = geom.x() * dpr
            phys_y = geom.y() * dpr
            phys_w = geom.width() * dpr
            phys_h = geom.height() * dpr
            if phys_x <= cx <= (phys_x + phys_w) and phys_y <= cy <= (phys_y + phys_h):
                return geom.x() + (cx - phys_x) / dpr, geom.y() + (cy - phys_y) / dpr

        target = primary or screens[0]
        dpr = target.devicePixelRatio()
        geom = target.geometry()
        phys_x = geom.x() * dpr
        phys_y = geom.y() * dpr
        return geom.x() + (cx - phys_x) / dpr, geom.y() + (cy - phys_y) / dpr

    def _poll_clicks(self) -> None:
        """Light Dismiss: emit outsideClicked if user clicked outside the capsule."""
        clicks = self._click_watcher.pop_clicks()
        if not clicks:
            return

        origin = self._window.position()
        hx, hy, hw, hh = self._hot
        if hw <= 0 or hh <= 0:
            return

        pad = 20
        # If pointer is currently hovering over the capsule or cursor is inside hot rect,
        # it is an internal click — never dismiss.
        cur_x, cur_y = self._cursor_logical()
        clx = cur_x - origin.x()
        cly = cur_y - origin.y()
        cursor_inside = (
            (hx - pad) <= clx <= (hx + hw + pad)
            and (hy - pad) <= cly <= (hy + hh + pad)
        )
        if self._hovered or cursor_inside:
            return

        screens = QApplication.screens()
        primary = QApplication.primaryScreen()

        for cx, cy in clicks:
            log_x, log_y = self._physical_to_logical(cx, cy, screens, primary)
            lx = log_x - origin.x()
            ly = log_y - origin.y()
            inside = (
                (hx - pad) <= lx <= (hx + hw + pad)
                and (hy - pad) <= ly <= (hy + hh + pad)
            )
            if not inside:
                self.outsideClicked.emit()
                break

    def _poll_escape(self) -> None:
        """Turn an Escape press into a signal — but only when it is ours.

        EkPill is a surface, not a window: it is open when the pointer
        is on it or when an active text field holds keyboard focus.
        """
        if not self._escape.poll():
            return
        self._track_cursor()
        if not self._hovered and not self._focus_held:
            return
        self.escapePressed.emit()

    # ------------------------------------------------------ battery / volume
    @Property(int, notify=batteryChanged)
    def batteryPercent(self) -> int:
        return self._battery[0]

    @Property(bool, notify=batteryChanged)
    def batteryCharging(self) -> bool:
        return self._battery[1]

    @Property(bool, notify=batteryChanged)
    def batteryPresent(self) -> bool:
        return self._battery[2]

    @Property(float, notify=volumeChanged)
    def volume(self) -> float:
        return self._volume

    @Property(bool, notify=volumeChanged)
    def muted(self) -> bool:
        return self._muted

    @Slot(float)
    def setVolume(self, value: float) -> None:
        self._volume = max(0.0, min(1.0, float(value)))
        self.volumeChanged.emit()
        self._volume_service.set(self._volume)

    @Slot()
    def toggleMute(self) -> None:
        self._muted = not self._muted
        self.volumeChanged.emit()
        self._volume_service.set_mute(self._muted)

    # ------------------------------------------------------------------ media
    @Property(bool, notify=mediaChanged)
    def mediaActive(self) -> bool:
        return bool(self._media.get("active"))

    @Property(str, notify=mediaChanged)
    def mediaTitle(self) -> str:
        return self._media.get("title", "")

    @Property(str, notify=mediaChanged)
    def mediaArtist(self) -> str:
        return self._media.get("artist", "")

    @Property(bool, notify=mediaChanged)
    def mediaPlaying(self) -> bool:
        return bool(self._media.get("playing"))

    @Property(str, notify=mediaChanged)
    def mediaArt(self) -> str:
        path = self._media.get("art", "")
        return ("file:///" + path.replace("\\", "/")) if path else ""

    @Property(str, notify=mediaChanged)
    def mediaPositionText(self) -> str:
        return self._media.get("positionText", "0:00")

    @Property(str, notify=mediaChanged)
    def mediaDurationText(self) -> str:
        return self._media.get("durationText", "0:00")

    @Property(float, notify=mediaChanged)
    def mediaProgress(self) -> float:
        duration = self._media.get("duration", 0.0) or 0.0
        if duration <= 0:
            return 0.0
        return max(0.0, min(1.0, self._media.get("position", 0.0) / duration))

    @Slot(str)
    def mediaCommand(self, name: str) -> None:
        self._media_service.command(name)

    @Slot(float)
    def mediaSeekFraction(self, fraction: float) -> None:
        duration = self._media.get("duration", 0.0) or 0.0
        if duration > 0:
            self._media_service.seek(float(fraction) * duration)

    # ------------------------------------------------------------ networking
    @Property(bool, notify=wifiChanged)
    def wifiConnected(self) -> bool:
        return bool(self._wifi.get("connected"))

    @Property(str, notify=wifiChanged)
    def wifiSsid(self) -> str:
        return self._wifi.get("ssid", "")

    @Property(int, notify=wifiChanged)
    def wifiSignal(self) -> int:
        return int(self._wifi.get("signal", 0))

    @Property(bool, notify=bluetoothChanged)
    def bluetoothOn(self) -> bool:
        return bool(self._bt.get("on"))

    @Property(bool, notify=bluetoothChanged)
    def bluetoothAvailable(self) -> bool:
        return bool(self._bt.get("available"))

    @Property(int, notify=bluetoothChanged)
    def bluetoothCount(self) -> int:
        return int(self._bt.get("count", 0))

    @Slot()
    def openWifiSettings(self) -> None:
        import subprocess

        subprocess.Popen(["cmd", "/c", "start", "ms-settings:network-wifi"],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    @Slot()
    def openBluetoothSettings(self) -> None:
        import subprocess

        subprocess.Popen(["cmd", "/c", "start", "ms-settings:bluetooth"],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    @Slot()
    def openNotificationSettings(self) -> None:
        import subprocess

        subprocess.Popen(["cmd", "/c", "start", "ms-settings:notifications"],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    # ---------------------------------------------- audio mixer & visualizer
    def _poll_audio_levels(self) -> None:
        media_playing = bool(self._media.get("playing", False))
        peak = self._audio_service.get_peak()
        if not media_playing and peak < 0.01:
            if self._audio_levels != [0.06] * 7:
                self._audio_levels = [0.06] * 7
                self._audio_peak = 0.0
                self.audioLevelsChanged.emit()
            return
        levels = self._audio_service.compute_wave_bars(media_playing)
        self._audio_levels = levels
        self._audio_peak = peak
        self.audioLevelsChanged.emit()

    @Property(list, notify=audioStreamsChanged)
    def audioStreams(self) -> list:
        return list(self._audio_streams)

    @Property(str, notify=audioStreamsChanged)
    def audioDeviceName(self) -> str:
        if hasattr(self, "_audio_service"):
            return self._audio_service.get_device_name()
        return "Default Output"

    @Property(list, notify=audioStreamsChanged)
    def audioOutputDevices(self) -> list:
        if hasattr(self, "_audio_service"):
            return self._audio_service.list_output_devices()
        return ["Default Output"]

    @Property(list, notify=audioLevelsChanged)
    def audioLevels(self) -> list:
        return list(self._audio_levels)

    @Property(float, notify=audioLevelsChanged)
    def audioPeak(self) -> float:
        return self._audio_peak

    @Slot()
    def refreshAudioStreams(self) -> None:
        streams = self._audio_service.list_streams()
        if self._showcase_seeded and len(streams) < 3:
            demo_streams = [
                {"id": "1040_Spotify.exe", "pid": 1040, "name": "Spotify", "binary": "Spotify.exe", "volume": 0.88, "volume_pct": 88, "muted": False},
                {"id": "4120_chrome.exe", "pid": 4120, "name": "Chrome", "binary": "chrome.exe", "volume": 0.65, "volume_pct": 65, "muted": False},
                {"id": "8812_Discord.exe", "pid": 8812, "name": "Discord", "binary": "Discord.exe", "volume": 0.45, "volume_pct": 45, "muted": False},
                {"id": "6304_Code.exe", "pid": 6304, "name": "Code", "binary": "Code.exe", "volume": 0.25, "volume_pct": 25, "muted": True},
            ]
            seen_names = {s.get("name", "").lower() for s in streams}
            for ds in demo_streams:
                if ds["name"].lower() not in seen_names and len(streams) < 4:
                    streams.append(ds)
        self._audio_streams = streams
        self.audioStreamsChanged.emit()

    @Slot(str, int)
    def setAppVolume(self, stream_id: str, pct: int) -> None:
        self._audio_service.set_app_volume(stream_id, pct)
        self.refreshAudioStreams()

    @Slot(str)
    def toggleAppMute(self, stream_id: str) -> None:
        self._audio_service.toggle_app_mute(stream_id)
        self.refreshAudioStreams()

    # ------------------------------------------------------- screen recorder
    def _tick_recorder(self) -> None:
        if self._recorder.active:
            self.recordChanged.emit()

    @Property(bool, notify=recordChanged)
    def recActive(self) -> bool:
        return self._recorder.active

    @Property(bool, notify=recordChanged)
    def recPaused(self) -> bool:
        return self._recorder.paused

    @Property(str, notify=recordChanged)
    def recStatus(self) -> str:
        if not self._recorder.active:
            return "idle"
        if self._recorder.paused:
            return "paused"
        return "recording"

    @Property(str, notify=recordChanged)
    def recTimeText(self) -> str:
        return self._recorder.tick()

    @Property(str, notify=recordChanged)
    def recFile(self) -> str:
        return self._recorder.file_path

    @Property(str, notify=recordChanged)
    def recError(self) -> str:
        return self._recorder.error

    @Property(int, notify=recordChanged)
    def recFps(self) -> int:
        return self._recorder.fps

    @Property(str, notify=recordChanged)
    def recDir(self) -> str:
        return self._recorder.dir

    @Property(bool, notify=recordChanged)
    def recSysAudio(self) -> bool:
        return self._recorder.sys_audio

    @Property(bool, notify=recordChanged)
    def recMic(self) -> bool:
        return self._recorder.mic

    @Property(str, notify=recordChanged)
    def recMicDevice(self) -> str:
        return self._recorder.mic_device

    @Property(list, notify=recordChanged)
    def recMics(self) -> list:
        return self._recorder.list_microphones()

    @Slot(result=bool)
    def startRecord(self) -> bool:
        ok = self._recorder.start(
            fps=self._recorder.fps,
            dest_dir=self._recorder.dir,
            sys_audio=self._recorder.sys_audio,
            mic=self._recorder.mic,
            mic_device=self._recorder.mic_device,
        )
        if ok:
            self._rec_time_timer.start()
        self.recordChanged.emit()
        return ok

    @Slot(result=bool)
    def pauseRecord(self) -> bool:
        ok = self._recorder.pause()
        self.recordChanged.emit()
        return ok

    @Slot(result=str)
    def stopRecord(self) -> str:
        self._rec_time_timer.stop()
        out = self._recorder.stop()
        self.recordChanged.emit()
        return out

    @Slot(result=bool)
    def openRecordDir(self) -> bool:
        return self._recorder.open_record_dir()

    @Slot()
    def refreshMics(self) -> None:
        self.recordChanged.emit()

    @Slot(int)
    def setRecFps(self, fps: int) -> None:
        self._recorder.fps = int(fps)
        persist.update(rec_fps=self._recorder.fps)
        self.recordChanged.emit()

    @Slot(str)
    def setRecDir(self, path: str) -> None:
        self._recorder.dir = str(path)
        persist.update(rec_dir=self._recorder.dir)
        self.recordChanged.emit()

    @Slot(str)
    def setRecPresetDir(self, preset: str) -> None:
        user = os.path.expanduser("~")
        cand = os.path.join(user, str(preset))
        if os.path.isdir(cand):
            self.setRecDir(cand)
        else:
            try:
                os.makedirs(cand, exist_ok=True)
                self.setRecDir(cand)
            except Exception:
                self.setRecDir(self._recorder.dir)

    @Slot(bool)
    def setRecSysAudio(self, on: bool) -> None:
        self._recorder.sys_audio = bool(on)
        persist.update(rec_sys_audio=self._recorder.sys_audio)
        self.recordChanged.emit()

    @Slot(bool)
    def setRecMic(self, on: bool) -> None:
        self._recorder.mic = bool(on)
        persist.update(rec_mic=self._recorder.mic)
        self.recordChanged.emit()

    @Slot(str)
    def setRecMicDevice(self, device: str) -> None:
        self._recorder.mic_device = str(device)
        persist.update(rec_mic_device=self._recorder.mic_device)
        self.recordChanged.emit()

    # ------------------------------------------------ inline wifi & bluetooth
    @Property(list, notify=wifiNetworksChanged)
    def wifiNetworks(self) -> list:
        return list(self._wifi_networks)

    @Property(bool, notify=wifiNetworksChanged)
    def wifiBusy(self) -> bool:
        return self._wifi_busy

    @Property(str, notify=wifiNetworksChanged)
    def wifiError(self) -> str:
        return self._wifi_error

    @Property(list, notify=bluetoothDevicesChanged)
    def bluetoothDevices(self) -> list:
        return list(self._bt_devices)

    @Property(bool, notify=bluetoothDevicesChanged)
    def bluetoothBusy(self) -> bool:
        return self._bt_busy

    @Slot()
    def scanWifi(self) -> None:
        self._wifi_busy = True
        self.wifiNetworksChanged.emit()
        self._loop.run(self._async_scan_wifi())

    async def _async_scan_wifi(self) -> None:
        nets = await asyncio.to_thread(shell.scan_wifi_networks)
        self._safeWifiScanSignal.emit(nets)

    @Slot(str)
    @Slot(str, str)
    def connectWifi(self, ssid: str, password: str = "") -> None:
        self._wifi_busy = True
        self.wifiNetworksChanged.emit()
        self._loop.run(self._async_connect_wifi(ssid, password))

    async def _async_connect_wifi(self, ssid: str, password: str) -> None:
        ok, err = await asyncio.to_thread(shell.connect_wifi, ssid, password)
        # Read the interface back immediately: the four-second poll used to
        # leave the header showing the old SSID right after a successful join.
        wifi = await asyncio.to_thread(shell.read_wifi)
        self._safeWifiSignal.emit(wifi)
        nets = await asyncio.to_thread(shell.scan_wifi_networks)
        self._safeWifiScanSignal.emit(nets)
        self._safeWifiConnectSignal.emit(ok, err)

    @Slot()
    def disconnectWifi(self) -> None:
        self._wifi_busy = True
        self.wifiNetworksChanged.emit()
        self._loop.run(self._async_disconnect_wifi())

    async def _async_disconnect_wifi(self) -> None:
        await asyncio.to_thread(shell.disconnect_wifi)
        wifi = await asyncio.to_thread(shell.read_wifi)
        self._safeWifiSignal.emit(wifi)
        nets = await asyncio.to_thread(shell.scan_wifi_networks)
        self._wifi_busy = False
        self._safeWifiScanSignal.emit(nets)
        self.wifiChanged.emit()

    @Slot(str)
    def forgetWifi(self, ssid: str) -> None:
        shell.forget_wifi(ssid)
        self.scanWifi()
        self.wifiNetworksChanged.emit()

    @Slot()
    def scanBluetooth(self) -> None:
        self._bt_busy = True
        self.bluetoothDevicesChanged.emit()
        self._loop.run(self._async_scan_bt())

    async def _async_scan_bt(self) -> None:
        devs = await shell.list_bluetooth_devices_async()
        self._safeBtScanSignal.emit(devs)

    @Slot()
    def toggleBluetooth(self) -> None:
        target = not bool(self._bt.get("on"))
        self._loop.run(self._bt_service.set_radio_state(target))

    @Slot(str)
    def removeBluetooth(self, mac: str) -> None:
        """Forget a paired device for real (Windows unpair)."""
        self._bt_busy = True
        self.bluetoothDevicesChanged.emit()
        self._loop.run(self._async_remove_bt(mac))

    async def _async_remove_bt(self, mac: str) -> None:
        ok = await shell.unpair_bluetooth(mac)
        if not ok:
            self._bt_error = "Windows could not remove that device"
        else:
            self._bt_error = ""
        devs = await shell.list_bluetooth_devices_async()
        self._safeBtScanSignal.emit(devs)

    @Property(str, notify=bluetoothDevicesChanged)
    def bluetoothError(self) -> str:
        return getattr(self, "_bt_error", "")

    # ------------------------------------------------------------------ misc
    @Property(str, constant=True)
    def iconFont(self) -> str:
        """The system icon face the QML should use for glyphs."""
        return self._icon_font

    # --------------------------------------------------------------- focus/DND
    @Property(bool, notify=focusChanged)
    def notifDnd(self) -> bool:
        """Windows' real Do Not Disturb state, mirrored for the switch.

        The notification *list* is deliberately not mirrored: EkPill is a
        control surface, not a second Action Center.
        """
        return self._dnd

    @Slot()
    def openDndSettings(self) -> None:
        """Windows does not let an unpackaged app move this switch.

        Reporting success here is what made EkPill and Windows disagree.
        EkPill mirrors the real focus state and sends the user to the
        place that owns it.
        """
        shell.open_focus_settings()

    # ---------------------------------------------------------------- launcher
    @Slot(result="QVariantList")
    def apps(self) -> list:
        if not self._apps_cache:
            self._apps_cache = shell.list_apps()
        return self._apps_cache

    @Slot(str, result=bool)
    def launch(self, path: str) -> bool:
        return shell.launch(path)

    @Slot(str, result=str)
    def calculate(self, expr: str) -> str:
        return shell.calculate(expr)

    # ------------------------------------------------------------------- power
    @Slot(str)
    def powerAction(self, name: str) -> None:
        shell.power_action(name)

    # -------------------------------------------------------- persisted state
    @Slot(str, bool, str, bool, bool)
    def saveWindowState(self, pos: str, pinned: bool, page: str,
                        dnd: bool, autohide: bool) -> None:
        """QML calls this whenever the persisted state changes (~150 bytes).

        A merge, not a full write: the change handlers fire for placement
        alone, and a full save here would rewrite the other preferences with
        their defaults every time the capsule moved.
        """
        persist.update(pos=pos, pinned=bool(pinned), page=page,
                       dnd=bool(dnd), autohide=bool(autohide))

    # ---------------------------------------------------------------- hotkeys
    def emitHotkey(self, name: str) -> None:
        """The native RegisterHotKey filter lands here (wired in main.py)."""
        self.hotkey.emit(name)

    # -------------------------------------------------------- hover / input
    @Property(bool, notify=hoverChanged)
    def hovered(self) -> bool:
        return self._hovered

    @Slot(int, int, int, int)
    def setHotRegion(self, x: int, y: int, w: int, h: int) -> None:
        self._hot = (int(x), int(y), int(w), int(h))

    @Property(bool, notify=focusHeldChanged)
    def focusHeld(self) -> bool:
        return self._focus_held

    @Slot(bool)
    def setFocusHeld(self, held: bool) -> None:
        """While a text field is active we must accept keyboard input."""
        held = bool(held)
        if self._focus_held != held:
            self._focus_held = held
            self.focusHeldChanged.emit()
        self._overlay.set_accepts_focus(held)

    def _poll_focus(self) -> None:
        if self._focus_held:
            self._overlay.focus()
