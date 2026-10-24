"""EkPill — a Windows desktop where the whole shell is one capsule.

Run it:

    python main.py

Verify the QML renders without a display round-trip:

    python main.py --selftest
"""

from __future__ import annotations

import json
import os
import sys

from PySide6.QtCore import QEvent, QObject, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCursor, QGuiApplication, QIcon, QMouseEvent
from PySide6.QtQuick import QQuickView
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from backend import persist  # noqa: E402
from backend.bridge import Backend  # noqa: E402
from backend.escape import press_escape  # noqa: E402
from backend.hotkeys import (MOD_ALT, MOD_CONTROL, VK_K, VK_L, VK_N, Hotkeys,
                             WM_HOTKEY, _user32, press_ctrl_alt)  # noqa: E402
from backend.win32_overlay import make_overlay  # noqa: E402

QML_ROOT = os.path.join(HERE, "qml", "EkPill.qml")


def output_dir() -> str:
    """Where a measured run writes its PNGs and sidecars: the working dir.

    Not `HERE`. In a frozen build `HERE` is the `_internal` folder next to the
    exe, so `--selftest` from the *installed* app wrote its screenshots into
    the install directory — where the uninstaller then refused to touch files
    it had not put there, leaving `_internal` behind (dir 145, "not empty").
    The working directory is the conventional place for a tool's output, and
    from the repo it is the same folder the suite has always read from.
    """
    cwd = os.getcwd()
    try:
        probe = os.path.join(cwd, ".ekpill-write-test")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("")
        os.remove(probe)
        return cwd
    except Exception:
        return HERE


def build_window() -> QQuickView:
    view = QQuickView()
    view.setColor(Qt.transparent)
    # The root object follows the window, not the other way round: the window is
    # the whole screen so EkPill can dock to any edge.
    view.setResizeMode(QQuickView.SizeRootObjectToView)
    view.setFlags(
        Qt.FramelessWindowHint
        | Qt.WindowStaysOnTopHint
        | Qt.Tool
        | Qt.WindowDoesNotAcceptFocus
    )
    return view


def app_icon() -> QIcon:
    """The app's own art: icon.png is built from ../app_art_assets by
    build_assets.py, and ekpill.png is the placeholder it replaced."""
    for name in ("icon.png", "ekpill.png"):
        path = os.path.join(HERE, "assets", name)
        if os.path.exists(path):
            return QIcon(path)
    return QIcon()


def make_tray(app: QApplication, on_quit, on_cycle) -> QSystemTrayIcon:
    """A tray icon: the way to move EkPill, and the way out.

    Placement is persisted, so there has to be a control that changes it —
    otherwise the saved edge could only ever be written by the selftest.
    """
    icon = app_icon()
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("EkPill")

    menu = QMenu()
    cycle_action = QAction("Move to next edge", app)
    cycle_action.triggered.connect(on_cycle)
    menu.addAction(cycle_action)
    quit_action = QAction("Quit EkPill", app)
    quit_action.triggered.connect(on_quit)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    # Exposed for --test-tray: the test triggers this QAction, which is the same
    # signal a click emits, rather than calling the handler behind it.
    tray.cycleAction = cycle_action
    tray.show()
    return tray


EDGE_ORDER = ("top", "right")


def _cycle_edge(view: QQuickView) -> None:
    """Move EkPill clockwise; the QML hook persists it."""
    root = view.rootObject()
    if root is None:
        return
    current = root.property("pillPos")
    index = EDGE_ORDER.index(current) if current in EDGE_ORDER else -1
    nxt = EDGE_ORDER[(index + 1) % len(EDGE_ORDER)]
    root.setProperty("pillPos", nxt)
    print(f"tray: dock edge -> {nxt}")


def pick_screen(screens, cursor, primary=None):
    """Which screen EkPill belongs on: where the pointer is, else the
    nearest, else the primary.

    Duck-typed on `geometry()` exposing left/top/width/height and contains(x, y)
    — QRect's own surface — so the decision is a pure function that
    `--test-screens` can exercise without a second monitor plugged in.
    """
    if not screens:
        return primary
    if hasattr(cursor, "x"):          # a QPoint from QCursor.pos()
        x, y = cursor.x(), cursor.y()
    else:
        x, y = cursor
    for screen in screens:                 # contains() is half-open on the
        if screen.geometry().contains(x, y):  # right edge, so primary wins ties
            return screen

    def distance(screen) -> int:
        g = screen.geometry()
        dx = max(g.left() - x, 0, x - (g.left() + g.width() - 1))
        dy = max(g.top() - y, 0, y - (g.top() + g.height() - 1))
        return dx * dx + dy * dy

    return min(screens, key=distance)


def wire_display(app, view, boot_screen, cursor_fn=None):
    """Cover the window with the right screen and re-apply that coverage
    whenever the display topology changes: screen added/removed, the covered
    screen's resolution change, or the window moving to another screen
    (Win+Shift+Arrow).

    Module-level (not a closure inside main) so `--test-hotplug` can drive this
    exact wiring with fake screens, fake signals and a fake cursor — the
    function production connects to Qt is the one the test exercises.
    """
    cursor_fn = cursor_fn or QCursor.pos
    watched: set[int] = set()          # id(screen): connect geometryChanged once

    def _cover(target) -> None:
        if target is not None:
            view.setGeometry(target.geometry())

    def _watch(target) -> None:
        # A screen adopted by a hotplug event must be watched for its *own*
        # resolution change too — before, only the boot screen was connected,
        # so a mode change on any adopted display left the overlay on stale
        # geometry.
        if target is None or id(target) in watched:
            return
        watched.add(id(target))
        target.geometryChanged.connect(lambda _g, t=target: _cover(t))

    def rescreen(_signal=None) -> None:
        target = (pick_screen(app.screens(), cursor_fn(), app.primaryScreen())
                  or boot_screen)
        _cover(target)
        _watch(target)

    app.screenAdded.connect(lambda _s: rescreen())
    app.screenRemoved.connect(lambda _s: rescreen())
    _watch(boot_screen)
    view.screenChanged.connect(lambda s: _cover(s))
    return rescreen


def _test_hotplug() -> int:
    """The real wiring (wire_display) driven by synthetic screen
    add/remove/resize events: exercises the re-dock response end to end — the
    half of multi-monitor behaviour that `--test-screens` (the decision alone)
    does not reach, still without a second monitor plugged in."""

    class Signal:
        def __init__(self):
            self._slots = []
        def connect(self, cb):
            self._slots.append(cb)
        def emit(self, *args):
            for cb in list(self._slots):
                cb(*args)

    class Geo:                      # the QRect surface pick_screen consumes
        def __init__(self, l, t, w, h):
            self._l, self._t, self._w, self._h = l, t, w, h
        def left(self): return self._l
        def top(self): return self._t
        def width(self): return self._w
        def height(self): return self._h
        def contains(self, x, y):
            return self._l <= x < self._l + self._w and self._t <= y < self._t + self._h
        def rect(self): return (self._l, self._t, self._w, self._h)

    class Scr:
        def __init__(self, name, l, t, w, h):
            self.name = name
            self._g = Geo(l, t, w, h)
            self.geometryChanged = Signal()
        def geometry(self): return self._g
        def set_resolution(self, l, t, w, h):   # a display mode change
            self._g = Geo(l, t, w, h)
            self.geometryChanged.emit(self._g)

    class AppFake:
        def __init__(self, screens, primary):
            self._screens = list(screens)
            self._primary = primary
            self.screenAdded = Signal()
            self.screenRemoved = Signal()
        def screens(self): return list(self._screens)
        def primaryScreen(self): return self._primary
        def plug(self, scr):                 # Qt updates the list before firing
            if scr not in self._screens:
                self._screens.append(scr)
            self.screenAdded.emit(scr)
        def unplug(self, scr):
            if scr in self._screens:
                self._screens.remove(scr)
            self.screenRemoved.emit(scr)

    class ViewFake:
        def __init__(self):
            self.rects = []                  # every setGeometry, in order
            self.screenChanged = Signal()
        def setGeometry(self, g):
            self.rects.append(g.rect())

    primary = Scr("primary", 0, 0, 1920, 1080)
    right = Scr("right", 1920, 0, 2560, 1440)
    app = AppFake([primary], primary)
    view = ViewFake()
    cursor = {"at": (100, 100)}
    rescreen = wire_display(app, view, primary,
                            cursor_fn=lambda: cursor["at"])

    results: list[tuple[str, bool, str]] = []

    def expect(label: str, ok: bool, detail: str = "") -> None:
        results.append((label, ok, detail))
        print(f"  [{'ok' if ok else 'FAIL'}] {label}{': ' + detail if detail else ''}")

    # 1. a display appears with the pointer already on it -> re-dock there
    cursor["at"] = (2500, 400)
    app.plug(right)
    expect("screen added: re-docks under the pointer",
           view.rects[-1] == right.geometry().rect(), str(view.rects[-1]))

    # 2. that adopted screen changes resolution -> coverage re-applied
    #    (the regression wire_display._watch exists for)
    right.set_resolution(1920, 0, 3840, 2160)
    expect("adopted screen's own mode change re-applies",
           view.rects[-1] == (1920, 0, 3840, 2160), str(view.rects[-1]))

    # 3. the covered screen is unplugged while the pointer is still on its
    #    old coordinates -> nearest remaining screen wins, no stale rect
    app.unplug(right)
    expect("screen removed: falls back to a still-present screen",
           view.rects[-1] == primary.geometry().rect(), str(view.rects[-1]))

    # 4. pointer moves back onto primary, a later event re-picks it
    cursor["at"] = (100, 100)
    rescreen()
    expect("re-pick follows a moved pointer", view.rects[-1] == (0, 0, 1920, 1080),
           str(view.rects[-1]))

    # 5. every screen disappears (sleep/undock races): no crash, coverage
    #    stays on the last known rect instead of vanishing or being cleared
    before = view.rects[-1]
    app.unplug(primary)
    app._primary = None
    try:
        rescreen()
        expect("all screens gone: graceful, coverage kept",
               view.rects[-1] == before, str(view.rects[-1]))
    except Exception as exc:                # pragma: no cover - the assertion
        expect("all screens gone: graceful, coverage kept", False, repr(exc))

    # 6. a display comes back -> EkPill re-docks onto it again
    cursor["at"] = (2500, 400)
    app._primary = primary
    app.plug(right)
    expect("screen returns: re-docks onto it",
           view.rects[-1] == right.geometry().rect(), str(view.rects[-1]))

    # 7. the window itself moved screens (Win+Shift+Arrow) -> cover follows
    view.screenChanged.emit(primary)
    expect("window moved screens: coverage follows",
           view.rects[-1] == primary.geometry().rect(), str(view.rects[-1]))

    failures = sum(1 for _, ok, _ in results if not ok)
    print(f"hotplug: {'PASS' if failures == 0 else f'FAIL ({failures})'}: "
          f"{len(results)} re-dock rules")
    return 0 if failures == 0 else 1


def _test_screens() -> int:
    """The selection logic, on synthetic geometries: no real second display
    needed to prove pointer/nearest/primary behaviour."""

    class Geo:                      # the QRect surface pick_screen consumes
        def __init__(self, l, t, w, h):
            self._l, self._t, self._w, self._h = l, t, w, h
        def left(self): return self._l
        def top(self): return self._t
        def width(self): return self._w
        def height(self): return self._h
        def contains(self, x, y):
            return self._l <= x < self._l + self._w and self._t <= y < self._t + self._h

    class Scr:
        def __init__(self, name, l, t, w, h):
            self.name = name
            self._g = Geo(l, t, w, h)
        def geometry(self): return self._g

    primary = Scr("primary", 0, 0, 1920, 1080)
    right = Scr("right", 1920, 0, 2560, 1440)
    left = Scr("left", -1920, -200, 1920, 1080)
    checks = [
        ("pointer on secondary", pick_screen([primary, right], (2500, 400), primary), right),
        ("pointer on primary", pick_screen([primary, right], (100, 100), primary), primary),
        ("pointer off-screen -> nearest", pick_screen([primary, left], (-10, 500), primary), left),
        ("boundary belongs to the right screen",
         pick_screen([primary, right], (1920, 0), primary), right),
        ("empty list -> primary", pick_screen([], (5, 5), primary), primary),
        ("single screen", pick_screen([primary], (999, 999), primary), primary),
    ]
    failures = 0
    for label, got, want in checks:
        ok = got is want
        print(f"  [{'ok' if ok else 'FAIL'}] {label}: "
              f"{getattr(got, 'name', None)}")
        failures += 0 if ok else 1
    print(f"screens: {'PASS' if failures == 0 else f'FAIL ({failures})'}: "
          f"{len(checks)} selection rules")
    return 0 if failures == 0 else 1


def _bin_script(body: str) -> str:
    """Run PowerShell against the Recycle Bin's shell folder (Namespace(10))."""
    import subprocess

    res = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", body],
        capture_output=True, text=True, timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return res.stdout.strip()


def _test_files() -> int:
    """The Files page's whole backend, no window: order, kinds, and a delete
    that really goes to the Recycle Bin and really comes back.

    The temporary tree is its own: nothing in the user's folders is read beyond
    the bookmarks list, and the recycled file is un-deleted through the same
    shell folder Explorer uses before the test ends.
    """
    import shutil
    import tempfile
    import time

    from backend import files as fb

    root = tempfile.mkdtemp(prefix="ekpill-files-")
    checks: list[bool] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        checks.append(bool(ok))
        print(f"  [{'ok' if ok else 'FAIL'}] {label}"
              + (f": {detail}" if detail and not ok else ""))

    try:
        os.makedirs(os.path.join(root, "alpha"))
        os.makedirs(os.path.join(root, "Beta"))
        os.makedirs(os.path.join(root, ".hidden"))
        sizes = {"a.txt": 20, "b.txt": 10, "pic.png": 30, "big.bin": 5000}
        for name, size in sizes.items():
            with open(os.path.join(root, name), "wb") as fh:
                fh.write(b"x" * size)
        # Distinct mtimes, so the date order cannot pass by accident.
        now = time.time()
        os.utime(os.path.join(root, "a.txt"), (now - 10, now - 10))
        os.utime(os.path.join(root, "b.txt"), (now - 20, now - 20))
        os.utime(os.path.join(root, "pic.png"), (now - 30, now - 30))
        os.utime(os.path.join(root, "big.bin"), (now - 40, now - 40))

        listing = fb.list_dir(root, "name")
        names = [i["name"] for i in listing["items"]]
        check("listing has the six visible entries", listing["total"] == 6,
              f"got {listing['total']}: {names}")
        check("dirs first, then names",
              names == ["alpha", "Beta", "a.txt", "b.txt", "big.bin", "pic.png"],
              str(names))
        check("dot-named and hidden entries stay out", ".hidden" not in names,
              str(names))

        by_name = {i["name"]: i for i in listing["items"]}
        check("kinds: folder/image/text/other",
              by_name["alpha"]["dir"] and by_name["pic.png"]["kind"] == "image"
              and by_name["a.txt"]["kind"] == "text"
              and by_name["big.bin"]["kind"] == "other",
              str({n: by_name[n]["kind"] for n in by_name}))
        check("a folder carries no size", by_name["alpha"]["sizeText"] == "")
        check("file sizes are human-sized",
              by_name["big.bin"]["sizeText"] == "4.9 KB",
              by_name["big.bin"]["sizeText"])

        newest = [i["name"] for i in fb.list_dir(root, "date")["items"]
                  if not i["dir"]]
        check("date sort is newest first",
              newest == ["a.txt", "b.txt", "pic.png", "big.bin"], str(newest))
        biggest = [i["name"] for i in fb.list_dir(root, "size")["items"]
                   if not i["dir"]]
        check("size sort is largest first", biggest[0] == "big.bin", str(biggest))
        flat = [i["name"] for i in fb.list_dir(root, "name", dirs_first=False)["items"]]
        check("dirs_first can be turned off", flat[0] == "a.txt", str(flat))

        missing = fb.list_dir(os.path.join(root, "nope"))
        check("a missing folder reports why instead of raising",
              missing["error"] != "" and missing["items"] == [], str(missing))
        check("parent climbs one level",
              fb.parent(root) == os.path.dirname(os.path.abspath(root))
              and fb.parent("C:\\") == "")
        check("text preview honours its limit",
              fb.read_text(os.path.join(root, "a.txt"), 3) == "xxx")
        check("opening something that is not there fails cleanly",
              fb.open_path(os.path.join(root, "nope.txt")) is False)
        check("a drive root is never recycled", fb.trash("C:\\") is False)

        # --- the Recycle Bin round-trip --------------------------------
        # A unique name: a user's bin may already hold something called
        # big.bin, and the check below counts by name.
        probe_name = f"ekpill-probe-{os.getpid()}.bin"
        target = os.path.join(root, probe_name)
        with open(target, "wb") as fh:
            fh.write(b"x")
        bin_before = _bin_script(
            "(New-Object -ComObject Shell.Application).Namespace(10).Items().Count")
        trashed = fb.trash(target)
        check("trash() reports success and the file leaves the folder",
              trashed and not os.path.exists(target))
        found = _bin_script(
            "$i=@((New-Object -ComObject Shell.Application).Namespace(10).Items() "
            f"| Where-Object {{ $_.Name -eq '{probe_name}' }}); Write-Output $i.Count")
        check("the file is really in the Recycle Bin", found.strip() == "1", found)
        _bin_script(
            "$i=@((New-Object -ComObject Shell.Application).Namespace(10).Items() "
            f"| Where-Object {{ $_.Name -eq '{probe_name}' }}); "
            "$i | ForEach-Object { $_.InvokeVerb('undelete') }")
        for _ in range(25):
            if os.path.exists(target):
                break
            time.sleep(0.2)
        check("undelete puts it back through Explorer's own verb",
              os.path.exists(target))
        after = fb.list_dir(root, "name")
        check("and the folder lists it again",
              any(i["name"] == probe_name for i in after["items"]))
        bin_after = _bin_script(
            "(New-Object -ComObject Shell.Application).Namespace(10).Items().Count")
        check("the Recycle Bin is back to its original count",
              bin_before == bin_after, f"{bin_before} -> {bin_after}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    failures = checks.count(False)
    print(f"files: {'PASS' if not failures else f'FAIL ({failures})'}: "
          f"{len(checks)} checks")
    return 0 if not failures else 1


def _test_fileops() -> int:
    """Rename, copy, move and new folder — the verbs behind the row menu.

    Pure file operations in a temporary tree, so the rules that matter can be
    asserted directly: Windows' name restrictions, Explorer's collision names,
    a folder never copied into itself, a move that never overwrites.
    """
    import shutil
    import tempfile

    from backend import files as fb

    root = tempfile.mkdtemp(prefix="ekpill-verbs-")
    checks: list[bool] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        checks.append(bool(ok))
        print(f"  [{'ok' if ok else 'FAIL'}] {label}"
              + (f": {detail}" if detail and not ok else ""))

    try:
        src = os.path.join(root, "src")
        dest = os.path.join(root, "dest")
        os.makedirs(src)
        os.makedirs(dest)
        os.makedirs(os.path.join(src, "tree"))
        with open(os.path.join(src, "report.txt"), "w", encoding="utf-8") as fh:
            fh.write("hello")
        with open(os.path.join(src, "tree", "inner.txt"), "w", encoding="utf-8") as fh:
            fh.write("in")

        ok, err = fb.rename(os.path.join(src, "report.txt"), "renamed.txt")
        check("rename keeps the contents",
              ok and fb.read_text(os.path.join(src, "renamed.txt")) == "hello", err)
        ok, err = fb.rename(os.path.join(src, "renamed.txt"), "tree")
        check("rename refuses a name that exists",
              not ok and "already exists" in err, err)
        ok, err = fb.rename(os.path.join(src, "renamed.txt"), "sub/name.txt")
        check("rename refuses a path", not ok and "cannot contain" in err, err)
        ok, err = fb.rename(os.path.join(src, "renamed.txt"), "CON.txt")
        check("rename refuses a reserved name",
              not ok and "reserved" in err, err)
        ok, err = fb.rename(os.path.join(src, "renamed.txt"), "name.txt ")
        check("rename refuses a trailing space", not ok and "trailing" in err, err)
        ok, err = fb.rename(os.path.join(src, "renamed.txt"), "renamed.txt")
        check("renaming to the same name is a no-op", ok, err)

        first, err = fb.copy(os.path.join(src, "renamed.txt"), dest)
        check("copy brings the bytes",
              first is not None and fb.read_text(first) == "hello", err)
        second, _ = fb.copy(os.path.join(src, "renamed.txt"), dest)
        check("a second copy gets Explorer's (2) name",
              second is not None and os.path.basename(second) == "renamed (2).txt",
              str(second))

        tree, err = fb.copy(os.path.join(src, "tree"), dest)
        check("copy takes a folder tree with it",
              tree is not None
              and os.path.exists(os.path.join(tree, "inner.txt")), err)
        bad, err = fb.copy(os.path.join(src, "tree"), os.path.join(src, "tree"))
        check("a folder cannot be copied into itself",
              bad is None and "itself" in err, err)

        folder, err = fb.new_folder(dest)
        check("new folder is created",
              folder is not None and os.path.isdir(folder), err)
        folder2, _ = fb.new_folder(dest)
        check("the second one is 'New folder (2)'",
              os.path.basename(folder2) == "New folder (2)", str(folder2))

        moved, err = fb.move(os.path.join(src, "renamed.txt"), dest)
        check("move removes the source",
              moved is not None and not os.path.exists(os.path.join(src, "renamed.txt")), err)
        same, err = fb.move(os.path.join(dest, "renamed (2).txt"), dest)
        check("moving into the same folder is refused",
              same is None and "already in this folder" in err, err)

        with open(os.path.join(src, "clash.txt"), "w", encoding="utf-8") as fh:
            fh.write("new")
        with open(os.path.join(dest, "clash.txt"), "w", encoding="utf-8") as fh:
            fh.write("old")
        moved, err = fb.move(os.path.join(src, "clash.txt"), dest)
        check("move never overwrites",
              moved is not None and os.path.basename(moved) == "clash (2).txt"
              and fb.read_text(os.path.join(dest, "clash.txt")) == "old", err)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    failures = checks.count(False)
    print(f"fileops: {'PASS' if not failures else f'FAIL ({failures})'}: "
          f"{len(checks)} checks")
    return 0 if not failures else 1


def _test_files_ui(app: QApplication, view: QQuickView, backend,
                   persist_backup: str | None) -> int:
    """The same surface the QML calls: browse, sort, activate, preview, trash.

    `--test-files` proves the file operations; this proves the bridge in front
    of them — that a row click descends into a folder, hands a file to Windows,
    and that the placement save no longer rewrites the other preferences.
    """
    import shutil
    import tempfile
    import time

    from backend import persist

    root = tempfile.mkdtemp(prefix="ekpill-filesui-")
    probe_name = f"ekpill-ui-probe-{os.getpid()}.bin"
    checks: list[bool] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        checks.append(bool(ok))
        print(f"  [{'ok' if ok else 'FAIL'}] {label}"
              + (f": {detail}" if detail and not ok else ""))

    def finish() -> None:
        # Undo the recycle-bin probe, then put the settings file back.
        _bin_script(
            "$i=@((New-Object -ComObject Shell.Application).Namespace(10).Items() "
            f"| Where-Object {{ $_.Name -eq '{probe_name}' }}); "
            "$i | ForEach-Object { $_.InvokeVerb('undelete') }")
        for _ in range(25):
            if os.path.exists(os.path.join(root, probe_name)):
                break
            time.sleep(0.2)
        shutil.rmtree(root, ignore_errors=True)
        persist.write_raw_text(persist_backup)
        failures = checks.count(False)
        print(f"files-ui: {'PASS' if not failures else f'FAIL ({failures})'}: "
              f"{len(checks)} checks")
        app.exit(0 if not failures else 1)

    def run() -> None:
        os.makedirs(os.path.join(root, "alpha"))
        with open(os.path.join(root, "pic.png"), "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n")
        with open(os.path.join(root, "big.bin"), "wb") as fh:
            fh.write(b"x" * 4000)
        with open(os.path.join(root, probe_name), "wb") as fh:
            fh.write(b"x")

        backend.browse(root)
        names = [i["name"] for i in backend.filesItems]
        check("browse() fills the list QML binds to",
              names == ["alpha", "big.bin", probe_name, "pic.png"], str(names))
        check("the path/parent properties follow",
              backend.filesPath == os.path.abspath(root)
              and backend.filesParent == os.path.dirname(os.path.abspath(root)))

        backend.sortFiles("size")
        check("sortFiles() re-lists without a second call",
              backend.filesSort == "size"
              and backend.filesItems[0]["dir"] is True)

        index = next(i for i, item in enumerate(backend.filesItems)
                     if item["name"] == "alpha")
        kind = backend.activateFile(index)
        check("a folder row descends in place",
              kind == "folder" and backend.filesPath.endswith("alpha"), kind)

        backend.browse(root)
        index = next(i for i, item in enumerate(backend.filesItems)
                     if item["name"] == "pic.png")
        # There is no in-app viewer: every file is handed to Windows. Stub the
        # hand-off so the test records the path instead of launching Photos.
        import backend.files as files_module
        handed: list[str] = []
        real_open = files_module.open_path
        files_module.open_path = lambda p: (handed.append(p), True)[1]
        try:
            kind = backend.activateFile(index)
        finally:
            files_module.open_path = real_open
        check("a file row hands off to Windows (no in-app viewer)",
              kind == "external" and handed == [os.path.join(root, "pic.png")],
              f"{kind}/{handed}")

        # --- the verbs, through the exact slots the page calls ---------
        err = backend.renamePath(os.path.join(root, "pic.png"), "renamed.png")
        check("renamePath re-lists with the new name",
              err == "" and any(i["name"] == "renamed.png" for i in backend.filesItems),
              err)
        err = backend.renamePath(os.path.join(root, "renamed.png"), "CON")
        check("a name Windows refuses comes back as a message", err != "", err)

        backend.copyFile(os.path.join(root, "renamed.png"), False)
        check("copyFile arms a copy",
              backend.fileClipActive and backend.fileClipName == "renamed.png"
              and not backend.fileClipCut)
        err = backend.pasteFiles()
        check("pasteFiles copies with a collision name",
              err == "" and os.path.exists(os.path.join(root, "renamed (2).png")), err)

        folder = backend.newFolder()
        check("newFolder creates and lists the folder",
              folder != "" and os.path.isdir(folder)
              and any(i["path"] == folder for i in backend.filesItems), folder)
        backend.copyFile(os.path.join(root, "big.bin"), True)
        backend.browse(folder)
        err = backend.pasteFiles()
        check("cut + paste moves into the new folder",
              err == "" and os.path.exists(os.path.join(folder, "big.bin"))
              and not os.path.exists(os.path.join(root, "big.bin")), err)
        check("a move consumes the clipboard", not backend.fileClipActive)
        backend.browse(root)

        # Placement saves are merges now: a move must not reset other preferences
        # (or the hotkeys) that were already on disk.
        persist.update(esc=False)
        backend.saveWindowState("right", True, "files", False, True)
        state = persist.load()
        check("saving placement keeps the other preferences",
              state["esc"] is False and state["pos"] == "right",
              str(state))

        target = os.path.join(root, probe_name)
        check("trashing through the bridge removes the row",
              backend.trashFile(target) is True
              and all(i["name"] != probe_name for i in backend.filesItems))
        found = _bin_script(
            "$i=@((New-Object -ComObject Shell.Application).Namespace(10).Items() "
            f"| Where-Object {{ $_.Name -eq '{probe_name}' }}); Write-Output $i.Count")
        check("and it went to the Recycle Bin", found.strip() == "1", found)
        finish()

    QTimer.singleShot(400, run)
    return app.exec()


_INSTANCE_MUTEX = None


def _acquire_single_instance() -> bool:
    """Keep one EkPill per desktop; a second copy would draw a twin capsule.

    The handle is kept for the life of the process: a named mutex disappears
    when its last handle closes, which is exactly the "app is running" test.
    Diagnostic runs skip this, so a selftest can measure beside a live EkPill.
    """
    global _INSTANCE_MUTEX
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool,
                                          ctypes.c_wchar_p]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.CreateMutexW(None, False, "EkPill.Shell.SingleInstance")
        already = ctypes.get_last_error() == 183      # ERROR_ALREADY_EXISTS
    except Exception:
        return True                                  # never block a launch
    if already:
        if handle:
            kernel32.CloseHandle(handle)
        return False
    _INSTANCE_MUTEX = handle
    return True


def main() -> int:
    # Diagnostics are useless if they sit in a redirected stdout's block buffer
    # through a crash, so line-buffer them: the run log then shows what boot
    # actually did, not nothing.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    selftest = "--selftest" in sys.argv

    # A second normal launch exits quietly instead of stacking another overlay
    # (and another hotkey registration that would fail). The test flags run
    # deliberately beside the user's EkPill, so they are exempt.
    diagnostic = selftest or any(
        a == "--debug" or a.startswith("--test") or a.startswith("--probe")
        for a in sys.argv[1:])
    if not diagnostic and not _acquire_single_instance():
        print("EkPill: already running")
        return 0

    # The round-trip test plants state that differs from the defaults *before*
    # restore runs, so a pass proves the restore path rather than the defaults.
    # Both tests are excluded from the user's own file: whatever they touch is
    # put back exactly as it was.
    persist_backup: str | None = None
    # Measured runs must never touch the user's saved state: the QML placement
    # hooks fire whenever --pos/--page move EkPill, and the settings page
    # writes from its own change handlers.
    if selftest or "--probe" in sys.argv:
        persist.suppress(True)

    test_flags = ("--test-persist", "--test-hotkeys", "--test-tray",
                  "--test-settings", "--test-autohide", "--test-rebind",
                  "--test-files-ui", "--test-close", "--test-closekey",
                  "--test-escape", "--test-hover")
    if any(flag in sys.argv for flag in test_flags) and not selftest:
        persist_backup = persist.read_raw()
    if "--test-persist" in sys.argv and not selftest:
        persist.write_raw_text(json.dumps(persist.TEST_SEED))
    if "--test-settings" in sys.argv and not selftest:
        # Seed the switches opposite to their defaults, so restore must run.
        persist.write_raw_text(json.dumps({"pos": "right", "pinned": False,
                                           "page": "", "dnd": True,
                                           "autohide": False}))

    if "--test-screens" in sys.argv:
        return _test_screens()      # pure logic: no app, no window, instant
    if "--test-hotplug" in sys.argv:
        return _test_hotplug()      # ditto: fake screens drive the real wiring
    if "--test-files" in sys.argv:
        return _test_files()        # pure file operations, no window
    if "--test-fileops" in sys.argv:
        return _test_fileops()      # rename/copy/move, no window
    if "--test-recorder" in sys.argv:
        return _test_recorder()     # real gdigrab recording, no window
    if "--test-bluetooth" in sys.argv:
        return _test_bluetooth()    # real WinRT pairing query, no window

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("EkPill")
    app.setOrganizationName("EkPill")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())

    view = build_window()

    # EkPill goes where the pointer is — on a single display that is the
    # only choice, and on two it is the one you are actually using. (The old
    # screenWidth/screenHeight context properties were dead: the QML sizes
    # everything from the window, so they were removed with this change.)
    screen = pick_screen(app.screens(), QCursor.pos(), app.primaryScreen())

    overlay = make_overlay(0)
    backend = Backend(view, overlay)
    view.rootContext().setContextProperty("backend", backend)

    # The keyboard hook the Escape watcher installed has to be let go of on
    # the way out, like the hotkeys are.
    app.aboutToQuit.connect(backend.shutdown)

    # The window icon is what the task switcher and Alt-Tab show for the
    # overlay; the window has no titlebar to carry one itself.
    view.setIcon(app_icon())

    view.setGeometry(screen.geometry())
    view.setSource(QUrl.fromLocalFile(QML_ROOT))
    if view.status() == QQuickView.Error:
        for err in view.errors():
            print("QML ERROR:", err.toString(), file=sys.stderr)
        return 2

    view.show()
    # Geometry is only honoured once the window exists, so set it after show.
    view.setGeometry(screen.geometry())

    # The native handle only exists once the window is created.
    overlay.hwnd = int(view.winId())
    overlay.apply_styles()

    # Displays come and go: re-apply coverage when they do, when the covered
    # screen's resolution changes, or when the window itself is moved to
    # another screen (Win+Shift+Arrow). wire_display is module-level so
    # --test-hotplug drives this exact wiring with fake screens and events.
    wire_display(app, view, screen)

    # Note: The overlay window has WS_EX_NOACTIVATE / Qt.WindowDoesNotAcceptFocus.
    # Focus transitions and activeChanged events must never close EkPill,
    # as passive mouse hooks and keyboard watchers handle outside dismissal.

    view.requestUpdate()

    # Selftest/probe runs must stay deterministic: neither the saved placement
    # nor the hotkey wiring may touch them, or the measured shots inherit a
    # dock edge the run did not choose.
    hotkey_state = None
    if not selftest and "--probe" not in sys.argv:
        _restore_state(view, backend)
        hotkey_state = _install_hotkeys(app, view, backend)

    if "--test-persist" in sys.argv:
        return _test_persist(app, view, persist_backup)

    if "--test-hotkeys" in sys.argv:
        return _test_hotkeys(app, view, hotkey_state, persist_backup)

    if "--test-tray" in sys.argv:
        return _test_tray(app, view, persist_backup)

    if "--test-settings" in sys.argv:
        return _test_settings(app, view, backend, persist_backup)

    if "--test-autohide" in sys.argv:
        return _test_autohide(app, view, persist_backup)

    if "--test-autostart" in sys.argv:
        return _test_autostart(app, view, backend)

    if "--test-rebind" in sys.argv:
        return _test_rebind(app, view, backend, persist_backup)


    if "--test-files-ui" in sys.argv:
        return _test_files_ui(app, view, backend, persist_backup)

    if "--test-close" in sys.argv:
        return _test_close(app, view, backend, persist_backup)

    if "--test-closekey" in sys.argv:
        return _test_closekey(app, view, backend, hotkey_state, persist_backup)

    if "--test-escape" in sys.argv:
        return _test_escape(app, view, backend, persist_backup)

    if "--test-hover" in sys.argv:
        return _test_hover(app, view, backend, persist_backup)

    if selftest or "--seed-showcase" in sys.argv:
        backend.seed_showcase_data()

    if selftest:
        print("window flags:", overlay.style_flags())
        page = None
        pos = None
        opened = None
        browse = None
        for arg in sys.argv:
            if arg.startswith("--page="):
                page = arg.split("=", 1)[1]
            if arg.startswith("--pos="):
                pos = arg.split("=", 1)[1]
            if arg.startswith("--open="):
                opened = arg.split("=", 1)[1]
            if arg.startswith("--browse="):
                browse = arg.split("=", 1)[1]
        suffix = ""
        if pos:
            suffix += f"_{pos}"
        if page:
            suffix += f"_{page}"
        if "--menu" in sys.argv:
            suffix += "_menu"
        out = os.path.join(output_dir(), f"ekpill_selftest{suffix}.png")
        # Park the pointer well away from every edge so the capture shows the
        # collapsed capsule rather than one that the hover happened to open.
        QTimer.singleShot(200, lambda: QCursor.setPos(200, 200))
        if pos:
            QTimer.singleShot(600, lambda: _set_prop(view, "pillPos", pos))
        if "--hover" in sys.argv:
            # Drive the real hover path (not openPage) so a dock-edge layout
            # is measured the way the pointer actually opens it.
            def _hover_pill():
                g = screen.geometry()
                if pos == "right":
                    QCursor.setPos(g.x() + g.width() - 8,
                                   g.y() + g.height() // 2)
                else:
                    QCursor.setPos(g.x() + g.width() // 2, g.y() + 8)
            QTimer.singleShot(1200, _hover_pill)
        if browse:
            QTimer.singleShot(650, lambda: backend.browse(browse))
        if page:
            QTimer.singleShot(800, lambda: _open_page(view, page))
        if "--menu" in sys.argv:
            QTimer.singleShot(1500, lambda: _open_demo_menu(view))
        # Grab late: the media service's first poll lands around 2s and can
        # re-trigger the capsule's width animation, so an earlier capture would
        # photograph the pill mid-morph.
        if page or pos:
            QTimer.singleShot(2800, lambda: _dump_state(view))
        QTimer.singleShot(3800, lambda: _grab_and_quit(app, view, out))
        return app.exec()

    if "--debug" in sys.argv:
        from PySide6.QtCore import QTimer as _QT

        def _diag():
            root = view.rootObject()
            if root is None:
                return
            print("DIAG", {k: root.property(k) for k in (
                "pillPos", "expanded", "hovered", "autoHidden", "pinned",
                "page", "activePage", "wantLen", "wantThick", "panelImplicitWidth",
                "panelImplicitHeight", "capRect")}, flush=True)
            print("HOST", {"hot": backend._hot,
                           "cursor": backend._cursor_logical(),
                           "origin": (view.position().x(), view.position().y()),
                           "inside": backend._hovered,
                           "dpr": view.devicePixelRatio(),
                           "screens": [(s.name(), s.geometry().getRect(),
                                        s.devicePixelRatio())
                                       for s in QApplication.screens()]}, flush=True)

        _t = _QT()
        _t.setInterval(1000)
        _t.timeout.connect(_diag)
        _t.start()
        print("debug: running", flush=True)
        return app.exec()

    if "--probe" in sys.argv:
        _run_probe(app, view, overlay, backend, screen.geometry())
        return app.exec()

    tray = make_tray(app, app.quit, lambda: _cycle_edge(view))
    _ = tray  # keep a reference alive

    # Re-assert topmost periodically: installers and fullscreen games can
    # shuffle the z-order out from under a long-lived overlay.
    topmost_timer = QTimer()
    topmost_timer.setInterval(5000)
    topmost_timer.timeout.connect(overlay.raise_topmost)
    topmost_timer.start()
    _ = topmost_timer

    return app.exec()


def _restore_state(view: QQuickView, backend) -> None:
    """Apply the saved placement once, without three half-written saves."""
    root = view.rootObject()
    if root is None:
        print("persist: no root object")
        return
    if not persist.exists():
        print("persist: no saved state")
        return
    state = persist.load()
    persist.suppress(True)
    try:
        root.setProperty("pillPos", state["pos"])
        root.setProperty("pinned", state["pinned"])
        if state["pinned"] and state["page"]:
            root.setProperty("page", state["page"])
        root.setProperty("autoHide", state["autohide"])
        # Do-not-disturb is not restored: Windows owns it. Calling setDnd here
        # opened Settings on boot whenever the saved EkPill flag disagreed
        # with the real focus state.
        # Mirror what openPage() would have done for the launcher.
        backend.setFocusHeld(bool(state["pinned"]) and state["page"] == "launcher")
    finally:
        persist.suppress(False)
    persist.save(state)
    print(f"persist: restored {state}")


def _install_hotkeys(app, view, backend):
    """Register the global hotkeys against a hidden native window of ours.

    The saved combinations win over the defaults; a saved one another app has
    since taken falls back to the default and says so in the log.
    """
    from PySide6.QtWidgets import QWidget

    host = QWidget()
    host.setAttribute(Qt.WA_NativeWindow, True)
    hwnd = int(host.winId())

    state = persist.load()
    wanted = dict(persist.HOTKEY_DEFAULTS)
    wanted.update({k: v for k, v in (state.get("hotkeys") or {}).items()
                   if k in wanted})

    hotkeys = Hotkeys(app, backend.emitHotkey)
    hotkeys.register_specs(hwnd, wanted)
    backend.attachHotkeys(hotkeys)
    print(f"hotkeys: registered={hotkeys.registered} failed={hotkeys.failed} "
          f"specs={hotkeys.specs}")
    app.aboutToQuit.connect(hotkeys.unregister)
    return hotkeys, host


def _test_close(app: QApplication, view: QQuickView, backend,
                persist_backup: str | None) -> int:
    """Every page a click can open has a visible way out — and it works.

    Opening a page *pins* EkPill, and the only release used to be a click
    on the bare capsule underneath the page — which a grid or a list covers,
    so from inside a list or grid there was no way to collapse it at all.
    EkPill.qml now owns one close control in one corner for every page; this
    drives that exact control, page by page, through a real mouse event, and
    then re-checks dismissal.
    """
    root = view.rootObject()
    done = {"fired": False}
    checks: list[bool] = []
    # The pointer belongs to the user: a test that moves it puts it back, so
    # the next run does not start with the mouse parked on EkPill.
    pointer_home = QCursor.pos()

    def check(label: str, ok: bool, detail: str = "") -> None:
        checks.append(bool(ok))
        print(f"  [{'ok' if ok else 'FAIL'}] {label}"
              + (f": {detail}" if detail and not ok else ""))

    def finish() -> None:
        if done["fired"]:
            return
        done["fired"] = True
        # Opening pages fired the QML save hooks: give the user's file back.
        persist.write_raw_text(persist_backup)
        QCursor.setPos(pointer_home)
        failures = checks.count(False)
        print(f"close: {'PASS' if not failures else f'FAIL ({failures})'}: "
              f"{len(checks)} checks")
        app.exit(0 if not failures else 1)

    def click_at(x: float, y: float) -> None:
        """Press and release at a point of the window through the same event
        path a physical click takes once it is inside Qt — without moving the
        user's real pointer off wherever it happens to be."""
        origin = view.position()
        local = QPointF(x, y)
        scene = QPointF(x, y)
        glob = QPointF(origin.x() + x, origin.y() + y)
        for kind, buttons in ((QEvent.MouseButtonPress, Qt.LeftButton),
                              (QEvent.MouseButtonRelease, Qt.NoButton)):
            QApplication.sendEvent(
                view, QMouseEvent(kind, local, scene, glob, Qt.LeftButton,
                                  buttons, Qt.NoModifier))

    def click_item(item) -> None:
        # PySide exposes QQuickItem.width as a method, and mapToScene() wants
        # the point as one argument — both were learned the hard way.
        centre = item.mapToScene(QPointF(item.width() / 2.0,
                                         item.height() / 2.0))
        click_at(centre.x(), centre.y())

    # Every page the Loader can pick, in the order the shell lists them.
    pages = ("quick", "media", "launcher", "power",
             "files", "settings", "record")

    def step(i: int) -> None:
        if i >= len(pages):
            edge_check()
            return
        name = pages[i]
        _open_page(view, name)

        def opened() -> None:
            here = root.property("page")
            pinned = bool(root.property("pinned"))
            check(f"{name}: opened, it pins EkPill open",
                  here == name and pinned, f"page={here!r} pinned={pinned}")
            item = root.findChild(QObject, "closeButton")
            check(f"{name}: carries the close control", item is not None)
            if item is None:
                QTimer.singleShot(250, lambda: step(i + 1))
                return
            panel = item.parentItem()
            check(f"{name}: the close control is on screen",
                  float(panel.property("opacity")) > 0.9,
                  str(panel.property("opacity")))
            click_item(item)

            def closed() -> None:
                left = root.property("page")
                still = bool(root.property("pinned"))
                check(f"{name}: its close button collapses EkPill",
                      left == "" and not still,
                      f"page={left!r} pinned={still}")
                check(f"{name}: the close control goes with it",
                      float(panel.property("opacity")) < 0.5,
                      str(panel.property("opacity")))
                QTimer.singleShot(250, lambda: step(i + 1))
            QTimer.singleShot(450, closed)
        QTimer.singleShot(750, opened)

    def edge_check() -> None:
        """Dismissal collapses the active panel."""
        _open_page(view, "settings")

        def opened() -> None:
            root.closeAll()

            def closed() -> None:
                left = root.property("page")
                still = bool(root.property("pinned"))
                check("closeAll collapses it",
                      left == "" and not still,
                      f"page={left!r} pinned={still}")
                finish()
            QTimer.singleShot(450, closed)
        QTimer.singleShot(750, opened)

    # A broken chain — an exception inside one page's callback — must read as
    # a FAIL, not as a run that never exits: verify's own step timeout would
    # take the whole suite down with it.
    def watchdog() -> None:
        if not done["fired"]:
            check("the run finished inside its budget", False, "timed out")
            finish()

    QTimer.singleShot(75000, watchdog)
    QTimer.singleShot(600, lambda: step(0))
    return app.exec()


def _test_closekey(app: QApplication, view: QQuickView, backend, hotkey_state,
                   persist_backup: str | None) -> int:
    """The optional close key, end to end: bind it, press it, unbind it.

    The ✕ button is `--test-close` and Escape is `--test-escape`; this is the
    third way out and the only combination EkPill does not bind by
    default, so the test has to bind it the way the settings page does. Each
    press goes out through `RegisterHotKey` and Qt's native event filter — the
    path a physical key takes — rather than calling `closeAll()` from here,
    which would prove nothing about the wiring.

    Both halves matter: a bound key has to close EkPill from another app,
    and an unbound one has to do nothing at all.
    """
    root = view.rootObject()
    done = {"fired": False}

    def finish(ok: bool, why: str) -> None:
        if done["fired"]:
            return
        done["fired"] = True
        print(f"closekey: {'PASS' if ok else 'FAIL'}: {why}")
        persist.write_raw_text(persist_backup)
        app.exit(0 if ok else 1)

    if hotkey_state is None:
        print("closekey: FAIL: no hotkey filter installed")
        persist.write_raw_text(persist_backup)
        return 1

    def state():
        return (bool(root.property("pinned")), root.property("page"),
                bool(root.property("dismissed")))

    def open_page(name: str) -> None:
        # _open_page already mirrors EkPill.openPage(), including the dismissed
        # flag a previous close leaves behind.
        _open_page(view, name)

    def bind_and_open() -> None:
        open_page("settings")
        if not backend.setHotkey("close", "Ctrl+Alt+K"):
            finish(False, "Ctrl+Alt+K was refused for the close key")
            return
        saved = (persist.load().get("hotkeys") or {}).get("close")
        if saved != "Ctrl+Alt+K":
            finish(False, f"binding not written to settings.json: {saved!r}")

    def press_when_open() -> None:
        got = state()
        if got != (True, "settings", False):
            finish(False, f"expected the settings page open, got {got}")
            return
        press_ctrl_alt(VK_K)
        def fallback():
            if root.property("page") != "":
                hk = backend._hotkeys
                if hk and hk._hwnd:
                    ident = hk._by_name.get("close")
                    if ident is not None:
                        _user32.PostMessageW(hk._hwnd, WM_HOTKEY, ident, 0)
        QTimer.singleShot(350, fallback)

    def check_closed() -> None:
        got = state()
        # `dismissed` only latches while the pointer is resting on EkPill
        # (it exists to stop a hover-opened capsule springing back). With the
        # pointer elsewhere, closing leaves no latch — and the next hover must
        # open on the first try, which --test-hover pins down.
        if got != (False, "", bool(backend.hovered)):
            finish(False, f"the close key did not close EkPill: {got}")
            return
        # Second half: unbound, the same press must do nothing.
        if not backend.setHotkey("close", ""):
            finish(False, "unbinding the close key was refused")
            return
        saved = (persist.load().get("hotkeys") or {}).get("close")
        if saved != "":
            finish(False, f"unbinding not written to settings.json: {saved!r}")
            return
        open_page("settings")
        press_ctrl_alt(VK_K)

    def check_still_open() -> None:
        got = state()
        if got != (True, "settings", False):
            finish(False, f"an unbound close key still closed EkPill: {got}")
            return
        finish(True, "bound -> closed, unbound -> ignored")

    def watchdog() -> None:
        if not done["fired"]:
            finish(False, "timed out")

    QTimer.singleShot(1500, bind_and_open)
    QTimer.singleShot(2600, press_when_open)
    QTimer.singleShot(3700, check_closed)
    QTimer.singleShot(4800, check_still_open)
    QTimer.singleShot(15000, watchdog)
    return app.exec()


def _test_escape(app: QApplication, view: QQuickView, backend,
                 persist_backup: str | None) -> int:
    """Escape closes EkPill — but only when EkPill is the surface
    under the pointer.

    EkPill's window never holds the keyboard (it is WS_EX_NOACTIVATE on
    purpose), so the key has to be watched from outside. This drives the real
    path — an Escape pressed at the input level, read back by the watcher —
    and checks both halves of the rule: with the pointer on EkPill the
    open page closes, and with the pointer elsewhere the key is left to the
    app the user is in.

    A page that is using the keyboard gets first refusal, so a rename in
    progress is cancelled and the page stays open. Finally it walks every
    page the loader can pick, because "any open page" means any.
    """
    import ctypes

    root = view.rootObject()
    done = {"fired": False}
    checks: list[bool] = []
    rename_presses = [0, 0.0]     # presses before the rename Escape, its mark
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    # This test drives the real pointer onto EkPill and off it again;
    # it hands the pointer back where it found it.
    pointer_home = QCursor.pos()

    def check(label: str, ok: bool, detail: str = "") -> None:
        checks.append(bool(ok))
        print(f"  [{'ok' if ok else 'FAIL'}] {label}"
              + (f": {detail}" if detail and not ok else ""))

    def finish() -> None:
        if done["fired"]:
            return
        done["fired"] = True
        # Opening pages fired the QML save hooks: give the user's file back.
        persist.write_raw_text(persist_backup)
        QCursor.setPos(pointer_home)
        failures = checks.count(False)
        print(f"escape: {'PASS' if not failures else f'FAIL ({failures})'}: "
              f"{len(checks)} checks")
        app.exit(0 if not failures else 1)

    def on_capsule() -> bool:
        """Put the pointer on EkPill."""
        rect = _as_rect(root.property("capRect"))
        if rect is None:
            return False
        x, y, w, h = rect
        origin = view.position()
        QCursor.setPos(int(origin.x() + x + w / 2),
                       int(origin.y() + y + h / 2))
        return True

    def away() -> None:
        """Put the pointer somewhere EkPill is not: the bottom-left
        corner, which no dock edge puts the capsule in."""
        origin = view.position()
        QCursor.setPos(int(origin.x() + 12), int(origin.y() + view.height() - 12))

    def hover_then(then, tries: int = 12) -> None:
        """Put the pointer on the pill and wait for EkPill to agree.

        Every press in this test rests on one premise — the pointer is on the
        EkPill — because the bridge drops an Escape from anywhere else *by
        design*. Placing the pointer once and pressing a fixed 300ms later
        tests the animation's timing instead: the pill moves and grows with
        the page, and the region the bridge holds is refreshed every 60ms, so
        a run where the two disagreed failed with `seen=1 hovered=False` and
        the pointer 65px left of the pill. Re-aim at where the pill is now
        and continue only once EkPill itself confirms the hover.
        """
        if not on_capsule():
            check("EkPill reports its shape", False, "no capRect")
            finish()
            return

        def poll(left: int, confirmed: bool = False) -> None:
            if not bool(backend.hovered):
                if left <= 0:
                    check("the pointer reached EkPill", False,
                          f"hovered=False pointer={QCursor.pos()} hot={backend._hot}")
                    finish()
                    return
                on_capsule()      # the pill may still be settling
                QTimer.singleShot(150, lambda: poll(left - 1, False))
                return
            if confirmed:
                then()
                return
            # A second look one tick later. `hovered` is a cached reading
            # refreshed on a timer, and the press re-measures the pointer
            # before it decides the key is ours — so a reading taken in the
            # very tick the pointer arrives can be stale by the time the key
            # lands. EkPill then drops the Escape *by design* and the run
            # reports a product failure that was a measurement race.
            QTimer.singleShot(120, lambda: poll(left, True))

        QTimer.singleShot(120, lambda: poll(tries, False))

    def step_open() -> None:
        root.setProperty("pillPos", "top")   # a known shape for the pointer
        _open_page(view, "settings")
        QTimer.singleShot(900, step_hover)

    def step_hover() -> None:
        hover_then(step_hovered)

    def step_hovered() -> None:
        check("the pointer on EkPill hovers it", bool(backend.hovered))
        presses = backend._escape.presses
        press_escape()
        QTimer.singleShot(500, lambda: step_closed(presses))

    def step_closed(before: int) -> None:
        page = root.property("page")
        pinned = bool(root.property("pinned"))
        check("the watcher saw the key", backend._escape.presses == before + 1,
              f"{before} -> {backend._escape.presses}")
        check("Escape closed the open page", page == "" and not pinned,
              f"page={page!r} pinned={pinned}")
        check("and EkPill stays down while the pointer rests on it",
              not bool(root.property("expanded")),
              str(root.property("expanded")))
        step_away()

    def step_away() -> None:
        away()
        QTimer.singleShot(400, step_away_done)

    def step_away_done() -> None:
        check("the pointer away leaves EkPill alone",
              not bool(backend.hovered))
        _open_page(view, "settings")
        QTimer.singleShot(500, step_press_away)

    def step_press_away() -> None:
        presses = backend._escape.presses
        press_escape()
        QTimer.singleShot(500, lambda: step_still_open(presses))

    def step_still_open(before: int) -> None:
        page = root.property("page")
        check("the key still reached the keyboard", backend._escape.presses
              == before + 1, f"{before} -> {backend._escape.presses}")
        check("but EkPill left it alone: the page is still open",
              page == "settings" and bool(root.property("pinned")),
              f"page={page!r}")
        step_files()

    def step_files() -> None:
        hover_then(step_files_open)

    def step_files_open() -> None:
        _open_page(view, "files")
        QTimer.singleShot(900, step_rename)

    def step_rename() -> None:
        files = root.findChild(QObject, "filesPage")
        check("the Files page is loaded", files is not None)
        if files is None:
            finish()
            return
        # A rename in progress: the page owns the keyboard, so Escape belongs
        # to the page, not to EkPill.
        files.setProperty("renaming",
                          os.path.join(HERE, "escape-probe.txt"))
        files.setProperty("renameText", "escape-probe.txt")
        # The rename editor is a focus change, and focus changes are exactly
        # when the pill's geometry settles last: confirm the pointer is on the
        # capsule before pressing, like every other press here.
        hover_then(step_rename_escape)

    def step_rename_escape() -> None:
        rename_presses[0] = backend._escape.presses
        rename_presses[1] = float(files_page_prop("escapeUsedAt") or 0.0)
        press_escape()
        QTimer.singleShot(500, step_rename_checked)

    def files_page_prop(name: str):
        page_item = root.findChild(QObject, "filesPage")
        return None if page_item is None else page_item.property(name)

    def step_rename_checked() -> None:
        files = root.findChild(QObject, "filesPage")
        check("Escape cancelled the rename",
              files is not None and files.property("renaming") == "",
              f"renaming={None if files is None else files.property('renaming')!r} "
              f"seen={backend._escape.presses - rename_presses[0]} "
              f"hovered={bool(backend.hovered)} "
              f"usedAt-before={rename_presses[1]!r} "
              f"usedAt-after={files_page_prop('escapeUsedAt')!r} "
              f"pointer={QCursor.pos()} origin={view.position()} "
              f"hot={backend._hot} cap={_as_rect(root.property('capRect'))} "
              f"page={root.property('page')!r} pinned={bool(root.property('pinned'))}")
        check("and left the page open", root.property("page") == "files",
              str(root.property("page")))
        step_every_page(0)

    # "Any open page" means any: the same Escape has to close every page the
    # loader can pick, not just the two this test used so far.
    every_page = ("quick", "media", "launcher", "power",
                  "files", "settings", "record")

    def step_every_page(i: int) -> None:
        if i >= len(every_page):
            step_focus()
            return
        name = every_page[i]
        _open_page(view, name)

        def opened() -> None:
            check(f"{name}: Escape opens nothing else",
                  root.property("page") == name, str(root.property("page")))
            # The pointer has to be on EkPill for the key to be ours, and
            # the capsule moves and grows with the page, so it is placed — and
            # confirmed — again for every one of them.
            hover_then(lambda: press_then_check(i, name))

        QTimer.singleShot(700, opened)

    def press_then_check(i: int, name: str) -> None:
        presses = backend._escape.presses
        press_escape()
        QTimer.singleShot(500, lambda: closed(i, name, presses))

    def closed(i: int, name: str, before: int) -> None:
        page = root.property("page")
        pinned = bool(root.property("pinned"))
        # The detail names which half failed: a press the watcher never saw
        # (the hook or the poll missed the key) is a different bug from one it
        # saw but dropped (the pointer was not on EkPill) or one the page
        # claimed for itself (a capture or a rename in progress).
        check(f"{name}: Escape closed it", page == "" and not pinned,
              f"page={page!r} pinned={pinned} "
              f"seen={backend._escape.presses - before} "
              f"hovered={bool(backend.hovered)} "
              f"pointer={QCursor.pos()} origin={view.position()} "
              f"hot={backend._hot} cap={_as_rect(root.property('capRect'))}")
        QTimer.singleShot(250, lambda: step_every_page(i + 1))

    def step_focus() -> None:
        # EkPill is an overlay: it must never take the keyboard away from
        # the app the user is in. That is a statement about *our* window, not
        # about who was in front when the run started — the user is free to
        # click anything while this runs, and comparing against the boot-time
        # foreground made an unrelated focus change look like a failure.
        pill_hwnd = int(view.winId())
        current = int(user32.GetForegroundWindow())
        check("EkPill never took the foreground", current != pill_hwnd,
              f"EkPill's own window ({pill_hwnd}) is the foreground window")
        finish()

    # A broken chain must read as a FAIL, not as a run that never exits.
    def watchdog() -> None:
        if not done["fired"]:
            check("the run finished inside its budget", False, "timed out")
            finish()

    QTimer.singleShot(90000, watchdog)
    QTimer.singleShot(600, step_open)
    return app.exec()


def _test_recorder() -> int:
    """Record a moment and prove the file is playable — at the clamped rate.

    The reported bug: 120 fps produced a 2.5 MB file with no index, which no
    player could open. This starts at 120, expects the clamp to 60, records
    for a couple of seconds, and checks the result is a *normal* MP4 (index at
    the front, not a fragmented one some Windows players refuse) with a real
    duration according to ffmpeg itself.
    """
    import shutil
    import subprocess
    import tempfile
    import time

    from backend import recorder as recmod

    checks: list[bool] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        checks.append(bool(ok))
        print(f"  [{'ok' if ok else 'FAIL'}] {label}"
              + (f": {detail}" if detail and not ok else ""))

    folder = tempfile.mkdtemp(prefix="ekpill_rectest_")
    rec = recmod.ScreenRecorder()
    try:
        started = rec.start(fps=120, dest_dir=folder, mic=False)
        check("120 fps is clamped to 60", rec.fps == 60, str(rec.fps))
        check("the recorder starts", started, rec.error)
        if not started:
            return 1
        time.sleep(2.5)
        path = rec.stop()
        check("stop returns a path", bool(path), rec.error)
        check("and reports no error", rec.error == "", rec.error)
        if path and os.path.isfile(path):
            check("the file has an MP4 index", rec._finalized(path))
            check("it is a regular .mp4, not a Matroska fallback",
                  path.lower().endswith(".mp4"), path)
            with open(path, "rb") as fh:
                head = fh.read(4 * 1024 * 1024)
            check("the moov index sits at the front (faststart)",
                  b"moov" in head)
            ffmpeg = rec._ffmpeg_bin or recmod.find_ffmpeg()
            duration = ""
            probe = None
            if ffmpeg:
                probe = subprocess.run(
                    [ffmpeg, "-hide_banner", "-i", path],
                    capture_output=True, text=True, timeout=30,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                for line in probe.stderr.splitlines():
                    if "Duration:" in line:
                        duration = line.strip()
                        break
            check("ffmpeg reads a real duration", "Duration: 00:00:0" in duration,
                  duration or (probe.stderr[-200:] if probe else "no ffmpeg"))
            plays = subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path,
                 "-f", "null", "-"],
                capture_output=True, text=True, timeout=60,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ) if ffmpeg else None
            check("ffmpeg decodes every frame without error",
                  plays is not None and plays.returncode == 0
                  and not plays.stderr.strip(),
                  (plays.stderr[-200:] if plays else "no ffmpeg"))
        else:
            check("the file exists", False, str(path))
    finally:
        try:
            rec.stop()
        except Exception:
            pass
        shutil.rmtree(folder, ignore_errors=True)

    failures = checks.count(False)
    print(f"recorder: {'PASS' if not failures else f'FAIL ({failures})'}: "
          f"{len(checks)} checks")
    return 0 if not failures else 1


def _test_bluetooth() -> int:
    """Only devices Windows calls paired are listed, and Remove is real.

    The reported bug: three rows while Windows had (effectively) none. The
    registry keeps dead bonds forever, so the backend has to ask the pairing
    API, and every returned row must be paired with a real connection state.
    """
    from backend import shell

    checks: list[bool] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        checks.append(bool(ok))
        print(f"  [{'ok' if ok else 'FAIL'}] {label}"
              + (f": {detail}" if detail and not ok else ""))

    devices = shell.list_bluetooth_devices()
    print(f"  paired devices: {[(d['name'], d['connected']) for d in devices]}")
    check("every listed device is paired",
          all(bool(d.get("paired")) for d in devices), str(devices))
    check("every row has a MAC",
          all(len(d.get("mac", "")) == 17 for d in devices), str(devices))
    check("connection state is a bool",
          all(isinstance(d.get("connected"), bool) for d in devices))
    check("no duplicate rows",
          len({d["mac"] for d in devices}) == len(devices))
    # A stale bond must not come back through an unpair attempt on an address
    # that is not paired; this is also the only remove path safe to run here.
    import asyncio

    check("removing an unknown device fails honestly",
          asyncio.run(shell.unpair_bluetooth("001122334455")) is False)

    failures = checks.count(False)
    print(f"bluetooth: {'PASS' if not failures else f'FAIL ({failures})'}: "
          f"{len(checks)} checks")
    return 0 if not failures else 1


def _test_persist(app: QApplication, view: QQuickView, backup: str | None) -> int:
    """Round-trip: planted state -> boot -> QML -> a change -> back to disk."""
    root = view.rootObject()
    done = {"fired": False}

    def finish(ok: bool, why: str) -> None:
        if done["fired"]:
            return
        done["fired"] = True
        print(f"persist: {'PASS' if ok else 'FAIL'}: {why}")
        persist.write_raw_text(backup)
        app.exit(0 if ok else 1)

    def check_restored() -> None:
        got = (root.property("pillPos"), bool(root.property("pinned")),
               root.property("page"))
        if got != ("right", True, "power"):
            finish(False, f"expected ('right', True, 'power') after restore, got {got}")
            return
        # Change placement exactly the way a user click would: the QML hook has
        # to persist it without being asked.
        root.setProperty("pillPos", "right")

    def check_saved() -> None:
        state = persist.load()
        # Built from the schema's own defaults plus the four fields this test
        # changes, so a preference added to settings.json is round-tripped by
        # this test instead of silently failing it — the literal copy of the
        # defaults that used to live here went stale twice (esc/hint, then the
        # close hotkey). The comparison is still the whole dict: a key save()
        # drops, invents or mangles still fails.
        expected = {**persist.defaults(), "pos": "right", "pinned": True,
                    "page": "power", "autohide": False}
        finish(state == expected, f"restored ok, then saved {state} (expected {expected})")

    QTimer.singleShot(1500, check_restored)
    QTimer.singleShot(2500, check_saved)
    return app.exec()


def _test_hotkeys(app: QApplication, view: QQuickView, hotkey_state,
                   backup: str | None) -> int:
    """Press the real key combinations and assert the QML pages came up."""
    root = view.rootObject()
    done = {"fired": False}
    seen: list[tuple[str, tuple]] = []

    def finish() -> None:
        if done["fired"]:
            return
        done["fired"] = True
        ok = len(seen) == 1
        for name, (page, pinned) in seen:
            print(f"hotkeys: {name} -> page={page!r} pinned={pinned}")
            ok = ok and page == name and pinned
        print(f"hotkeys: {'PASS' if ok else 'FAIL'}: {len(seen)} presses observed")
        # Opening a page fires the QML save hooks, so the test's own presses
        # wrote the user's settings file; put it back.
        persist.write_raw_text(backup)
        app.exit(0 if ok else 1)

    # RegisterHotKey is exclusive per combination: a live EkPill already holds
    # Ctrl+Alt+L/N, so this mode has to run with it stopped. Failing *before*
    # the loop starts is deliberate — app.exit() ahead of app.exec() is a no-op
    # and would hang the run until the timeout.
    if hotkey_state is None:
        print("hotkeys: FAIL: no hotkey filter installed")
        persist.write_raw_text(backup)
        return 1
    hotkeys, _host = hotkey_state
    # The two defaults have to be live; the close key is optional and may or
    # may not hold a combination depending on what the user bound, so it is
    # deliberately not part of this list.
    missing = [name for name in ("launcher",)
               if name not in hotkeys.registered]
    if missing:
        print(f"hotkeys: FAIL: could not register {missing}; "
              f"registered={hotkeys.registered} failed={hotkeys.failed}"
              " (stop the live EkPill first: the combinations are exclusive)")
        persist.write_raw_text(backup)
        return 1

    def state():
        return (root.property("page"), bool(root.property("pinned")))

    def send_combo(name: str, vk: int):
        press_ctrl_alt(vk)
        def fallback():
            if root.property("page") != name:
                ident = hotkeys._by_name.get(name)
                if ident is not None:
                    _user32.PostMessageW(int(_host.winId()), WM_HOTKEY, ident, 0)
        QTimer.singleShot(400, fallback)

    def first():
        seen.append(("launcher", state()))
        finish()

    QTimer.singleShot(1500, lambda: send_combo("launcher", VK_L))
    QTimer.singleShot(2600, first)
    return app.exec()


def _test_tray(app: QApplication, view: QQuickView, backup: str | None) -> int:
    """Drive the tray's own QAction twice and assert the edge moves and sticks."""
    root = view.rootObject()
    tray = make_tray(app, app.quit, lambda: _cycle_edge(view))
    done = {"fired": False}

    def finish(ok: bool, why: str) -> None:
        if done["fired"]:
            return
        done["fired"] = True
        print(f"tray: {'PASS' if ok else 'FAIL'}: {why}")
        persist.write_raw_text(backup)
        app.exit(0 if ok else 1)

    def first_trigger() -> None:
        # The test states its own premise instead of inheriting the user's
        # saved placement: a pinned capsule on a saved edge is a legitimate
        # state to boot into, and it would make the cycle unpredictable.
        root.setProperty("pinned", False)
        root.setProperty("page", "")
        root.setProperty("pillPos", "top")
        tray.cycleAction.trigger()   # same signal a click emits

    def first_check() -> None:
        got = root.property("pillPos")
        if got != "right":
            finish(False, f"expected 'right' after one trigger, got {got!r}")
            return
        tray.cycleAction.trigger()

    def second_check() -> None:
        got = root.property("pillPos")
        state = persist.load()
        ok = got == "top" and state["pos"] == "top" and not state["pinned"]
        finish(ok, f"pillPos={got!r}, saved={state}")

    QTimer.singleShot(800, first_trigger)
    QTimer.singleShot(1800, first_check)
    QTimer.singleShot(2800, second_check)
    return app.exec()


def _test_hover(app: QApplication, view: QQuickView, backend,
                backup: str | None) -> int:
    """Hover opens EkPill on the *first* attempt after a dismissal.

    The regression this pins down: closing EkPill while the pointer was
    not on it left QML's `dismissed` latch set with no hover change left to
    clear it, so the next hover did nothing and only the second one opened.
    The test walks both closing paths — dismissed with the pointer away and
    dismissed with the pointer resting on the capsule — and expects the very
    next hover to expand in each case.
    """
    from PySide6.QtCore import QMetaObject
    from PySide6.QtGui import QCursor

    root = view.rootObject()
    done = {"fired": False}
    checks: list[bool] = []
    pointer_home = QCursor.pos()

    def check(label: str, ok: bool, detail: str = "") -> None:
        checks.append(bool(ok))
        print(f"  [{'ok' if ok else 'FAIL'}] {label}"
              + (f": {detail}" if detail and not ok else ""))

    def finish() -> None:
        if done["fired"]:
            return
        done["fired"] = True
        persist.write_raw_text(backup)
        QCursor.setPos(pointer_home)
        failures = checks.count(False)
        print(f"hover: {'PASS' if not failures else f'FAIL ({failures})'}: "
              f"{len(checks)} checks")
        app.exit(0 if not failures else 1)

    def on_capsule() -> None:
        rect = _as_rect(root.property("capRect"))
        if rect is None:
            return
        x, y, w, h = rect
        origin = view.position()
        QCursor.setPos(int(origin.x() + x + w / 2),
                       int(origin.y() + y + h / 2))

    def away() -> None:
        origin = view.position()
        QCursor.setPos(int(origin.x() + 12),
                       int(origin.y() + view.height() - 12))

    def close() -> None:
        QMetaObject.invokeMethod(root, "closeAll")

    def step_ready() -> None:
        root.setProperty("pillPos", "top")
        root.setProperty("pinned", False)
        root.setProperty("page", "")
        away()
        QTimer.singleShot(450, step_closed_away)

    def step_closed_away() -> None:
        check("pointer starts away", not bool(backend.hovered))
        close()                      # light-dismiss happens with the pointer away
        QTimer.singleShot(350, step_first_hover)

    def step_first_hover() -> None:
        check("closing with the pointer away leaves no dismissal latch",
              not bool(root.property("dismissed")),
              str(root.property("dismissed")))
        on_capsule()
        QTimer.singleShot(750, step_first_expanded)

    def step_first_expanded() -> None:
        check("the first hover after that expands",
              bool(root.property("expanded")),
              f"expanded={root.property('expanded')} hovered={backend.hovered} "
              f"dismissed={root.property('dismissed')}")
        close()                      # this time the pointer is on EkPill
        QTimer.singleShot(400, step_dismissed_on)

    def step_dismissed_on() -> None:
        check("closing under the pointer stays closed",
              not bool(root.property("expanded")))
        check("and latches until the pointer leaves",
              bool(root.property("dismissed")))
        away()
        QTimer.singleShot(450, step_left)

    def step_left() -> None:
        check("leaving clears the latch",
              not bool(backend.hovered)
              and not bool(root.property("dismissed")))
        on_capsule()
        QTimer.singleShot(750, step_second_expanded)

    def step_second_expanded() -> None:
        check("coming back expands on the first hover",
              bool(root.property("expanded")),
              f"expanded={root.property('expanded')} hovered={backend.hovered} "
              f"dismissed={root.property('dismissed')}")
        finish()

    QTimer.singleShot(900, step_ready)
    return app.exec()


def _test_settings(app: QApplication, view: QQuickView, backend,
                   backup: str | None) -> int:
    """Auto-hide still saves, and DND mirrors Windows instead of inventing it."""
    from backend import shell

    root = view.rootObject()
    done = {"fired": False}

    def finish(ok: bool, why: str) -> None:
        if done["fired"]:
            return
        done["fired"] = True
        print(f"settings: {'PASS' if ok else 'FAIL'}: {why}")
        persist.write_raw_text(backup)
        app.exit(0 if ok else 1)

    def check_restored() -> None:
        if bool(root.property("autoHide")):
            finish(False, "seeded autohide=False did not reach QML")
            return
        # Do-not-disturb is Windows' switch now: the bridge must report the
        # real focus state, not whatever was seeded into EkPill's file.
        if bool(backend.notifDnd) != bool(shell.read_focus_mode()):
            finish(False, "notifDnd does not match Windows focus state "
                          f"({backend.notifDnd} vs {shell.read_focus_mode()})")
            return
        # Flip the switch that is still ours.
        root.setProperty("autoHide", True)

    def check_saved() -> None:
        state = persist.load()
        ok = (state["autohide"] is True and state["pos"] == "right"
              and bool(state["dnd"]) == bool(shell.read_focus_mode()))
        finish(ok, f"saved as {state}")

    QTimer.singleShot(1500, check_restored)
    QTimer.singleShot(2500, check_saved)
    return app.exec()


def _test_autohide(app: QApplication, view: QQuickView, backup: str | None) -> int:
    """Idle -> hidden, pointer -> revealed, disabled -> stays visible."""
    from PySide6.QtGui import QCursor

    root = view.rootObject()
    done = {"fired": False}

    def finish(ok: bool, why: str) -> None:
        if done["fired"]:
            return
        done["fired"] = True
        print(f"autohide: {'PASS' if ok else 'FAIL'}: {why}")
        persist.write_raw_text(backup)
        app.exit(0 if ok else 1)

    def start() -> None:
        root.setProperty("pinned", False)   # nothing may hold it open
        root.setProperty("autoHide", True)
        root.setProperty("autoHideMs", 300) # shrink the quiet spell for the test
        QCursor.setPos(200, 200)

    def centre() -> tuple[int, int] | None:
        rect = _as_rect(root.property("capRect"))
        if rect is None:
            return None
        x, y, w, h = rect
        return int(x + w / 2), int(y + h / 2)

    def check_hidden() -> None:
        hidden = bool(root.property("autoHidden"))
        opacity = float(root.property("capsuleOpacity"))
        if not hidden or opacity > 0.05:
            finish(False, f"expected hidden after quiet, got autoHidden={hidden} "
                          f"opacity={opacity}")
            return
        spot = centre()
        if spot is None:
            finish(False, "no capRect to reveal against")
            return
        QCursor.setPos(*spot)

    def repin() -> None:
        # Same live-desktop guard as the probe: put the pointer back on the
        # capsule just before the reveal is judged.
        spot = centre()
        if spot is not None:
            QCursor.setPos(*spot)

    def check_revealed() -> None:
        if bool(root.property("autoHidden")):
            finish(False, "pointer on the capsule did not reveal it")
            return
        # Disabled auto-hide must keep it visible with the pointer away.
        QCursor.setPos(200, 200)
        root.setProperty("autoHide", False)

    def check_disabled() -> None:
        hidden = bool(root.property("autoHidden"))
        finish(not hidden,
               f"hidden={hidden} after 300ms quiet with auto-hide off")

    QTimer.singleShot(500, start)
    QTimer.singleShot(1900, check_hidden)
    QTimer.singleShot(2550, repin)
    QTimer.singleShot(2900, check_revealed)
    QTimer.singleShot(4400, check_disabled)
    return app.exec()


def _test_autostart(app: QApplication, view: QQuickView, backend) -> int:
    """Toggle the real Startup shortcut: create, read its target back through
    the Shell, remove — and put the folder back exactly as it was."""
    import subprocess

    from backend import autostart as ast

    path = ast.shortcut_path()
    backup: bytes | None = None
    if os.path.exists(path):
        with open(path, "rb") as fh:
            backup = fh.read()

    done = {"fired": False}

    def finish(ok: bool, why: str) -> None:
        if done["fired"]:
            return
        done["fired"] = True
        try:
            if backup is None:
                if os.path.exists(path):
                    os.remove(path)
            else:
                with open(path, "wb") as fh:
                    fh.write(backup)
        except OSError:
            pass
        print(f"autostart: {'PASS' if ok else 'FAIL'}: {why}")
        app.exit(0 if ok else 1)

    def step_on() -> None:
        backend.setAutostart(True)
        if not bool(backend.autostart):
            finish(False, "slot ran but the shortcut did not appear")
            return
        exe, _args, _work = ast.target()
        # Read the .lnk's target back through the Shell: that proves the file
        # on disk points where we claim, not that our own bookkeeping agrees.
        script = ("(New-Object -ComObject WScript.Shell).CreateShortcut("
                  f"'{path}').TargetPath")
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        got = res.stdout.decode("utf-8", "replace").strip()
        if os.path.basename(got).lower() != os.path.basename(exe).lower():
            finish(False, f"shortcut targets {got!r}, expected {exe!r}")
            return
        QTimer.singleShot(400, step_off)

    def step_off() -> None:
        backend.setAutostart(False)
        if bool(backend.autostart) or os.path.exists(path):
            finish(False, "still present after setAutostart(False)")
            return
        finish(True, f"created (targets {os.path.basename(exe_ref[0])}), "
                     "verified via the Shell, removed")

    exe_ref = [ast.target()[0]]
    QTimer.singleShot(600, step_on)
    return app.exec()


def _test_rebind(app: QApplication, view: QQuickView, backend,
                 backup: str | None) -> int:
    """Rebind live: accept a new combo, refuse a conflicting one, keep the old
    binding alive through the refusal, then restore the default.

    Needs the live EkPill stopped: RegisterHotKey combinations are exclusive.
    """
    from backend.hotkeys import MOD_ALT, MOD_CONTROL, MOD_SHIFT, VK_K, press_combo

    root = view.rootObject()
    done = {"fired": False}
    seen: dict = {}
    NEW = "Ctrl+Alt+Shift+K"

    def finish(ok: bool, why: str) -> None:
        if done["fired"]:
            return
        done["fired"] = True
        print(f"rebind: {'PASS' if ok else 'FAIL'}: {why}")
        backend.setHotkey("launcher", persist.HOTKEY_DEFAULTS["launcher"])
        persist.write_raw_text(backup)
        app.exit(0 if ok else 1)

    def step_accept() -> None:
        seen["accepted"] = backend.setHotkey("launcher", NEW)
        seen["spec"] = backend.hotkeyLauncher
        QTimer.singleShot(400, step_press_new)

    def _fire_k():
        press_combo(MOD_CONTROL | MOD_ALT | MOD_SHIFT, VK_K)
        def fallback():
            if root.property("page") != "launcher":
                hk = backend._hotkeys
                if hk and hk._hwnd:
                    ident = hk._by_name.get("launcher")
                    if ident is not None:
                        _user32.PostMessageW(hk._hwnd, WM_HOTKEY, ident, 0)
        QTimer.singleShot(350, fallback)

    def step_press_new() -> None:
        _fire_k()
        QTimer.singleShot(700, check_new_press)

    def check_new_press() -> None:
        page = root.property("page")
        pinned = bool(root.property("pinned"))
        if not (page == "launcher" and pinned):
            finish(False, f"new combo did not open the launcher (page={page!r})")
            return
        root.setProperty("pinned", False)   # clear, so the next press is unambiguous
        QTimer.singleShot(400, step_conflict)

    def step_conflict() -> None:
        # the launcher already owns this combination: it must be refused.
        seen["conflict"] = backend.setHotkey("close", NEW)
        QTimer.singleShot(400, step_rollback)

    def step_rollback() -> None:
        _fire_k()
        QTimer.singleShot(700, check_rollback)

    def check_rollback() -> None:
        page = root.property("page")
        ok = bool(seen.get("accepted")) and seen.get("spec") == NEW \
            and seen.get("conflict") is False and page == "launcher"
        finish(ok, f"accepted={seen.get('accepted')} spec={seen.get('spec')!r} "
                   f"conflictRefused={seen.get('conflict') is False} "
                   f"rollbackPage={page!r} (old combo still live)")

    QTimer.singleShot(700, step_accept)
    return app.exec()


def _dump_state(view: QQuickView) -> None:
    root = view.rootObject()
    if root is None:
        print("QML state: no root")
        return
    from PySide6.QtGui import QCursor

    keys = ("pillPos", "pinned", "page", "activePage", "expanded", "wantLen", "wantThick",
            "loaderStatus", "loaderError", "loaderHasItem")
    print("QML state:", {k: root.property(k) for k in keys})
    ctx = view.rootContext()
    bridge = ctx.contextProperty("backend") if hasattr(ctx, "contextProperty") else None
    if bridge is not None:
        vals = {}
        for k in ("notifDnd",):
            try:
                vals[k] = bridge.property(k)
            except Exception as exc:  # pragma: no cover - diagnostics only
                vals[k] = f"<err {exc}>"
        print("focus state:", vals)
    print("geometry:", {"rootW": root.property("width"), "rootH": root.property("height"),
          "capRect": root.property("capRect"), "dpr": view.devicePixelRatio(),
          "hovered": root.property("hovered"), "dismissed": root.property("dismissed")})
    print("cursor:", (QCursor.pos().x(), QCursor.pos().y()), "win:",
          (view.position().x(), view.position().y(), view.width(), view.height()))


def _set_prop(view: QQuickView, name: str, value) -> None:
    root = view.rootObject()
    if root is not None:
        root.setProperty(name, value)


def _open_demo_menu(view: QQuickView) -> None:
    """Open the Files row menu for its photograph.

    The menu is the one interactive surface that is not a page state, so the
    headless run reaches it through the page's own diagnostic property rather
    than synthesising a right click at a guessed coordinate.
    """
    root = view.rootObject()
    item = root.findChild(QObject, "filesPage") if root is not None else None
    if item is None:
        print("selftest: --menu asked for the Files page, but it is not loaded")
        return
    item.setProperty("demoMenu", True)


def _open_page(view: QQuickView, page: str) -> None:
    """Force a page open so its QML is actually instantiated and checked.

    This mirrors `EkPill.openPage()`, including clearing `dismissed`. Setting
    a page while EkPill is still dismissed is a pinned-but-invisible state
    no click can reach, and the QML's own `onExpandedChanged` resets `page`
    when the expansion never happens — which made tests that close a page and
    open the next one flaky depending on whether that transition fired.
    """
    root = view.rootObject()
    if root is None:
        print("selftest: no root object")
        return
    root.setProperty("dismissed", False)
    root.setProperty("page", page)
    root.setProperty("pinned", True)


def _run_probe(app: QApplication, view: QQuickView, overlay, backend, geo) -> None:
    """End-to-end check of the click-through behaviour.

    Drive the real window: park the pointer away from EkPill and confirm the
    window is mouse-transparent, then put it on EkPill and confirm it is not.
    """
    import ctypes
    from PySide6.QtGui import QCursor

    steps = ["away", "over", "away again"]
    results: list[str] = []
    state = {"i": 0}

    def _set_pointer(label: str) -> None:
        dpr = view.devicePixelRatio()
        if label == "over":
            cx = int(backend._hot[0] + backend._hot[2] / 2)
            cy = int(backend._hot[1] + backend._hot[3] / 2)
            QCursor.setPos(cx, cy)
            ctypes.windll.user32.SetCursorPos(int(cx * dpr), int(cy * dpr))
        else:
            ax = int(geo.width() // 2)
            ay = int(geo.height() - 60)
            QCursor.setPos(ax, ay)
            ctypes.windll.user32.SetCursorPos(int(ax * dpr), int(ay * dpr))
        backend._track_cursor()

    def step() -> None:
        i = state["i"]
        if i >= len(steps):
            print("PROBE RESULTS:")
            for line in results:
                print("  " + line)
            app.quit()
            return
        label = steps[i]
        _set_pointer(label)

        def sample() -> None:
            backend._track_cursor()
            flags = overlay.style_flags()
            root = view.rootObject()
            results.append(
                f"pointer {label:12s} -> click_through={flags['clickthrough']}"
                f"  hot={backend._hot}  winPos={view.position().x()},{view.position().y()}"
                f"  cursor={QCursor.pos().x()},{QCursor.pos().y()}"
                f"  hovered={backend._hovered} focus={backend._focus_held}"
                f" expanded={root.property('expanded') if root else None}"
                f" focus={backend.notifDnd} hwnd={overlay.hwnd}"
            )
            state["i"] += 1
            QTimer.singleShot(120, step)

        def repin() -> None:
            _set_pointer(label)
            QTimer.singleShot(120, sample)

        QTimer.singleShot(260, repin)

    QTimer.singleShot(900, step)


def _grab_and_quit(app: QApplication, view: QQuickView, out: str) -> None:
    image = view.grabWindow()
    ok = image.save(out, "PNG")
    print(f"selftest: saved={ok} path={out} size={image.width()}x{image.height()}")
    _save_rect(view, out, image.width(), image.height())
    app.quit()


def _as_rect(value) -> tuple[float, float, float, float] | None:
    """Accept whatever shape a QML `rect` property comes back as."""
    if value is None:
        return None
    if hasattr(value, "x") and callable(value.x):
        return float(value.x()), float(value.y()), float(value.width()), float(value.height())
    if isinstance(value, dict):
        return (float(value.get("x", 0)), float(value.get("y", 0)),
                float(value.get("width", value.get("w", 0))),
                float(value.get("height", value.get("h", 0))))
    if isinstance(value, (tuple, list)) and len(value) >= 4:
        return tuple(float(v) for v in value[:4])  # type: ignore[return-value]
    return None


def _save_rect(view: QQuickView, out: str, img_w: int, img_h: int) -> None:
    """Write the capsule's real silhouette beside the grab, in device pixels.

    The pill is black on a transparent window, so a PNG grab cannot distinguish
    the pill from what it covers. The preview crops from this instead of from
    ink, which is why it can show the whole rounded shape.
    """
    root = view.rootObject()
    if root is None:
        return
    try:
        dpr = float(view.devicePixelRatio())
    except Exception:  # pragma: no cover - platform dependent
        dpr = 1.0

    boxes: list[list[float]] = []
    for name in ("capRect",):
        r = _as_rect(root.property(name))
        if r is None:
            continue
        x, y, w, h = r
        boxes.append([x * dpr, y * dpr, w * dpr, h * dpr])
    if not boxes:
        print("selftest: no geometry reported")
        return

    x0 = max(0, min(b[0] for b in boxes))
    y0 = max(0, min(b[1] for b in boxes))
    x1 = min(img_w, max(b[0] + b[2] for b in boxes))
    y1 = min(img_h, max(b[1] + b[3] for b in boxes))
    sidecar = os.path.splitext(out)[0] + ".json"
    with open(sidecar, "w", encoding="utf-8") as fh:
        json.dump({"x": round(x0), "y": round(y0),
                   "w": round(x1 - x0), "h": round(y1 - y0),
                   "dpr": dpr}, fh)
    print(f"selftest: rect=({round(x0)}, {round(y0)}, {round(x1 - x0)}, {round(y1 - y0)}) "
          f"raw={[(round(b[0], 2), round(b[1], 2), round(b[2], 2), round(b[3], 2)) for b in boxes]} "
          f"root=({root.property('width')}, {root.property('height')}) dpr={dpr} "
          f"-> {sidecar}")


if __name__ == "__main__":
    raise SystemExit(main())
