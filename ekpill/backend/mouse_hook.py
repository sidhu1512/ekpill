"""A passive low-level mouse click watcher for Windows Light Dismiss.

When the EkPill capsule is expanded or a page is open, clicking anywhere
outside the capsule dismisses the panel and minimizes the capsule.

Crucially, this hook NEVER blocks, swallows, or delays mouse clicks. It always
calls CallNextHookEx, so background applications (Antigravity, Chrome, taskbar,
desktop, etc.) receive every mouse click and gain focus instantly without any
hindrance.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

WH_MOUSE_LL = 14
HC_ACTION = 0
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_NCLBUTTONDOWN = 0x00A1
WM_NCRBUTTONDOWN = 0x00A4

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
_HIGH_DOWN = 0x8000

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", _POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long,          # LRESULT
    ctypes.c_int,           # nCode
    wintypes.WPARAM,
    wintypes.LPARAM,
)

_user32.CallNextHookEx.argtypes = (
    wintypes.HHOOK,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
_user32.CallNextHookEx.restype = ctypes.c_long
_user32.SetWindowsHookExW.argtypes = (
    ctypes.c_int,
    HOOKPROC,
    wintypes.HINSTANCE,
    wintypes.DWORD,
)
_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL
_user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
_user32.GetAsyncKeyState.restype = ctypes.c_short
_user32.GetCursorPos.argtypes = (ctypes.POINTER(_POINT),)
_user32.GetCursorPos.restype = wintypes.BOOL
_kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE

_click_watcher: "ClickWatcher | None" = None


def _mouse_hook_proc(code: int, wparam: int, lparam: int) -> int:
    """Invoked by Windows for mouse messages across the system."""
    try:
        if code == HC_ACTION and wparam in (
            WM_LBUTTONDOWN,
            WM_RBUTTONDOWN,
            WM_NCLBUTTONDOWN,
            WM_NCRBUTTONDOWN,
        ):
            if lparam:
                info = ctypes.cast(
                    ctypes.c_void_p(lparam), ctypes.POINTER(_MSLLHOOKSTRUCT)
                ).contents
                if _click_watcher is not None:
                    _click_watcher.report(info.pt.x, info.pt.y)
    except Exception:
        pass
    # The click is NEVER eaten or intercepted. It is always passed on untouched.
    return _user32.CallNextHookEx(None, code, wparam, lparam)


class ClickWatcher:
    """Passively observes mouse clicks for light dismissal."""

    def __init__(self) -> None:
        self._proc = None
        self._hook = None
        self._hooked = False
        self._pending_clicks: list[tuple[int, int]] = []
        self._btn_down = False

    def install(self) -> bool:
        """Install WH_MOUSE_LL hook on the thread running the Qt event loop."""
        global _click_watcher
        if self._hook is not None:
            return True
        proc = HOOKPROC(_mouse_hook_proc)
        module = _kernel32.GetModuleHandleW(None)
        hook = _user32.SetWindowsHookExW(WH_MOUSE_LL, proc, module, 0)
        if not hook:
            hook = _user32.SetWindowsHookExW(WH_MOUSE_LL, proc, None, 0)
        if not hook:
            return False
        self._proc = proc
        self._hook = hook
        self._hooked = True
        _click_watcher = self
        return True

    def uninstall(self) -> None:
        """Unhook on exit."""
        global _click_watcher
        if self._hook is not None:
            _user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        self._proc = None
        self._hooked = False
        if _click_watcher is self:
            _click_watcher = None

    def report(self, x: int, y: int) -> None:
        """Called by the hook: a button-down was seen at screen coordinates (x, y)."""
        self._pending_clicks.append((int(x), int(y)))

    def pop_clicks(self) -> list[tuple[int, int]]:
        """Return all pending clicks. Also checks state poll for fresh taps if hook is not active."""
        if self._hooked:
            if self._pending_clicks:
                clicks = list(self._pending_clicks)
                self._pending_clicks.clear()
                return clicks
            return []

        # Fallback state poll ONLY if the WH_MOUSE_LL hook could not be installed:
        l_state = _user32.GetAsyncKeyState(VK_LBUTTON)
        r_state = _user32.GetAsyncKeyState(VK_RBUTTON)
        l_down = bool(l_state & _HIGH_DOWN)
        r_down = bool(r_state & _HIGH_DOWN)

        down = l_down or r_down

        if down and not self._btn_down:
            self._btn_down = True
            pt = _POINT()
            if _user32.GetCursorPos(ctypes.byref(pt)):
                return [(int(pt.x), int(pt.y))]
        elif not down:
            self._btn_down = False

        return []
