"""Global hotkeys, so EkPill can be summoned without hunting for it.

Windows has one API for a keystroke that arrives while another app has focus
without a low-level keyboard hook: `RegisterHotKey`. Its `WM_HOTKEY` message
goes to the window we hand it, and Qt runs `nativeEventFilter` **before** its
own message handling — so the wiring is: register against a hidden native
window, then dispatch the pressed id straight back to QML.

If a combination already belongs to another process Windows refuses the
registration. That is not an error to swallow or to crash over: the names that
failed are reported so the log says plainly what is *not* available.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes as wt

from PySide6.QtCore import QAbstractNativeEventFilter

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312

VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_SHIFT = 0x10
VK_LWIN = 0x5B
VK_K = 0x4B
VK_L = 0x4C
VK_N = 0x4E

KEYEVENTF_KEYUP = 0x0002

MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT,
        "shift": MOD_SHIFT, "win": MOD_WIN, "meta": MOD_WIN}

# Named keys a user can reasonably want. Letters, digits and F1..F24 are
# handled by shape, not by table.
_NAMED = {
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pgup": 0x21, "pgdn": 0x22,
    "insert": 0x2D, "delete": 0x2E,
}

DEFAULT_SPECS = {"launcher": "Ctrl+Alt+L",
                 # The close key has no default: an empty string means "no
                 # combination is bound", which is a state the map has to be
                 # able to hold.
                 "close": ""}


def parse_combo(spec: str) -> tuple[int, int] | None:
    """"Ctrl+Alt+L" -> (modifiers, vk); None when it is not usable.

    A modifier is required on purpose: a bare letter would collide with every
    application's normal typing.
    """
    if not isinstance(spec, str) or not spec.strip():
        return None
    parts = [p.strip().lower() for p in spec.replace("-", "+").split("+")]
    parts = [p for p in parts if p]
    if len(parts) < 2:
        return None
    mods = 0
    for token in parts[:-1]:
        bit = MODS.get(token)
        if bit is None or (mods & bit):
            return None          # unknown or repeated modifier
        mods |= bit
    key = parts[-1]
    if len(key) == 1 and ("a" <= key <= "z" or "0" <= key <= "9"):
        return mods, ord(key.upper())
    if len(key) in (2, 3) and key[0] == "f" and key[1:].isdigit():
        n = int(key[1:])
        if 1 <= n <= 24:
            return mods, 0x70 + (n - 1)
    vk = _NAMED.get(key)
    return (mods, vk) if vk is not None else None


def format_combo(mods: int, vk: int) -> str:
    """Canonical text, so the same combination always compares equal."""
    parts = []
    if mods & MOD_CONTROL:
        parts.append("Ctrl")
    if mods & MOD_ALT:
        parts.append("Alt")
    if mods & MOD_SHIFT:
        parts.append("Shift")
    if mods & MOD_WIN:
        parts.append("Win")
    for name, code in _NAMED.items():
        if code == vk:
            parts.append(name.capitalize())
            return "+".join(parts)
    if 0x70 <= vk <= 0x87:
        parts.append(f"F{vk - 0x70 + 1}")
    elif 0x41 <= vk <= 0x5A:
        parts.append(chr(vk))
    elif 0x30 <= vk <= 0x39:
        parts.append(chr(vk))
    else:
        parts.append(f"0x{vk:02X}")
    return "+".join(parts)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.RegisterHotKey.argtypes = (wt.HWND, ctypes.c_int, ctypes.c_uint, ctypes.c_uint)
_user32.RegisterHotKey.restype = ctypes.c_bool
_user32.UnregisterHotKey.argtypes = (wt.HWND, ctypes.c_int)
_user32.UnregisterHotKey.restype = ctypes.c_bool
_user32.keybd_event.argtypes = (ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ulong, wt.LPVOID)
_user32.keybd_event.restype = None


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wt.HWND),
        ("message", wt.UINT),
        ("wParam", wt.WPARAM),
        ("lParam", wt.LPARAM),
        ("time", wt.DWORD),
        ("pt", wt.POINT),
    ]


class Hotkeys(QAbstractNativeEventFilter):
    """Registers combinations on `hwnd` and reports each press to `on_hotkey`.

    Registrations are held per name, so a combination can be *rebound* at
    runtime: the new one is registered **before** the old one is released, so a
    refusal by Windows leaves the previous binding live instead of leaving the
    user with nothing.
    """

    def __init__(self, app, on_hotkey) -> None:
        super().__init__()
        self._app = app
        self._on_hotkey = on_hotkey
        self._ids: dict[int, str] = {}
        self._by_name: dict[str, int] = {}
        self._hwnd: wt.HWND | None = None
        self.specs: dict[str, str] = {}
        self.registered: list[str] = []
        self.failed: list[str] = []
        app.installNativeEventFilter(self)

    def _next_id(self) -> int:
        return max(self._ids, default=0) + 1

    def register_specs(self, hwnd: int, wanted: dict[str, str]) -> None:
        """`wanted` is name -> desired spec; each falls back to its default.

        A saved combination that another app now owns is not fatal: the default
        is tried, and the fallback is printed so the log says which binding is
        actually live.

        The one exception is a name whose default *is* empty — the close key.
        There is nothing to fall back to, so a combination Windows refuses
        leaves that name unbound and says so.
        """
        self._hwnd = wt.HWND(int(hwnd))
        for name, desired in wanted.items():
            default = DEFAULT_SPECS.get(name, "")
            candidates = [desired] if desired == default else [desired, default]
            # Every name gets an entry, even one that could not be
            # registered: an unbound name has to be *unbound*, not missing.
            self.specs[name] = ""
            for attempt, spec in enumerate(candidates):
                if spec == "":
                    # An empty spec is a *valid* state, not a failed
                    # registration: the close key is optional, and "no
                    # combination is bound" is what the user asked for.
                    self.specs[name] = ""
                    if attempt > 0:
                        print(f"hotkeys: {name} wanted {desired!r} (unavailable), "
                              f"using no combination")
                        self.failed.append(name)
                    break
                parsed = parse_combo(spec)
                if parsed is None:
                    continue
                mods, vk = parsed
                ident = self._next_id()
                if _user32.RegisterHotKey(self._hwnd, ident, mods | MOD_NOREPEAT, vk):
                    self._ids[ident] = name
                    self._by_name[name] = ident
                    self.specs[name] = format_combo(mods, vk)
                    self.registered.append(name)
                    if attempt > 0:
                        print(f"hotkeys: {name} wanted {desired!r} (unavailable), "
                              f"using {self.specs[name]!r}")
                    break
            else:
                print(f"hotkeys: {name} wanted {desired!r} (unavailable), "
                      f"using no combination")
                self.failed.append(name)

    def rebind(self, name: str, spec: str) -> bool:
        """Swap one binding; False leaves the previous one untouched."""
        if self._hwnd is None or name not in self.specs:
            return False
        spec = spec.strip() if isinstance(spec, str) else ""
        if spec == "":
            # Unbinding: the combination goes, the name stays. This is how
            # the close key is turned off again.
            old_id = self._by_name.get(name)
            if old_id is not None:
                _user32.UnregisterHotKey(self._hwnd, old_id)
                del self._ids[old_id]
                del self._by_name[name]
            self.specs[name] = ""
            if name in self.registered:
                self.registered.remove(name)
            if name in self.failed:
                self.failed.remove(name)
            return True
        parsed = parse_combo(spec)
        if parsed is None:
            return False
        mods, vk = parsed
        canonical = format_combo(mods, vk)
        if canonical == self.specs[name]:
            return True
        # Windows only arbitrates conflicts *between threads*; two of our own
        # bindings would happily shadow each other, so check that here.
        if canonical in [s for n, s in self.specs.items() if n != name and s]:
            return False
        new_id = self._next_id()
        if not _user32.RegisterHotKey(self._hwnd, new_id, mods | MOD_NOREPEAT, vk):
            return False          # some other process owns it; old stays live
        old_id = self._by_name.get(name)
        if old_id is not None:
            _user32.UnregisterHotKey(self._hwnd, old_id)
            del self._ids[old_id]
        self._ids[new_id] = name
        self._by_name[name] = new_id
        self.specs[name] = canonical
        if name not in self.registered:
            self.registered.append(name)
        if name in self.failed:
            self.failed.remove(name)
        return True

    def owns(self, name: str) -> bool:
        """True when this name currently holds a registered combination."""
        return name in self._by_name

    def unregister(self) -> None:
        if self._hwnd is not None:
            for ident in list(self._ids):
                _user32.UnregisterHotKey(self._hwnd, ident)
        self._ids.clear()
        self._by_name.clear()

    def nativeEventFilter(self, eventType, message):
        label = eventType if isinstance(eventType, (bytes, bytearray)) else str(eventType)
        if b"MSG" not in (label if isinstance(label, bytes) else label.encode("ascii", "ignore")):
            return False, 0
        try:
            msg = _MSG.from_address(int(message))
        except Exception:
            return False, 0
        if int(msg.message) != WM_HOTKEY:
            return False, 0
        name = self._ids.get(int(msg.wParam))
        if name is None:
            return False, 0
        self._on_hotkey(name)
        return True, 0


def press_combo(mods: int, vk: int) -> None:
    """Press <mods>+<vk> at input level — the test harnesses use this to
    exercise the real RegisterHotKey → Qt → QML path instead of calling the
    handler directly."""
    down: list[int] = []
    if mods & MOD_SHIFT:
        down.append(VK_SHIFT)
    if mods & MOD_CONTROL:
        down.append(VK_CONTROL)
    if mods & MOD_ALT:
        down.append(VK_MENU)
    if mods & MOD_WIN:
        down.append(VK_LWIN)
    for code in down:
        _user32.keybd_event(code, 0, 0, None)
    _user32.keybd_event(vk, 0, 0, None)
    _user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, None)
    for code in reversed(down):
        _user32.keybd_event(code, 0, KEYEVENTF_KEYUP, None)


def press_ctrl_alt(vk: int) -> None:
    """Kept for the existing tests: Ctrl+Alt+<vk>."""
    press_combo(MOD_CONTROL | MOD_ALT, vk)