"""Win32 window plumbing for the EkPill overlay.

A Qt window cannot do all of this on its own, so a little ctypes goes a long way:

* WS_EX_LAYERED      - per-pixel alpha (transparent pixels are see-through)
* WS_EX_TOOLWINDOW   - keep EkPill out of Alt-Tab and the taskbar
* WS_EX_NOACTIVATE   - never steal focus from the app you are using
* WS_EX_TRANSPARENT  - whole-window click-through, toggled while the pointer is
                       away from the capsule so clicks reach the desktop behind it
* DWMWA_*            - square corners and no drop shadow on our transparent window

Everything degrades to a no-op off Windows so the QML can still be previewed.
"""

from __future__ import annotations

import sys

IS_WINDOWS = sys.platform == "win32"

GWL_EXSTYLE = -20

WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_APPWINDOW = 0x00040000

HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010

DWMWA_NCRENDERING_POLICY = 2
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_DONOTROUND = 1
DWMNCRP_DISABLED = 1

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

    _user32.GetWindowLongW.restype = ctypes.c_long
    _user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.SetWindowLongW.restype = ctypes.c_long
    _user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint,
    ]
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]


class Overlay:
    """Thin controller around a native window handle."""

    def __init__(self, hwnd: int) -> None:
        self.hwnd = int(hwnd)
        self._click_through = False
        self._no_activate = False

    # ------------------------------------------------------------------ flags
    def _ex_style(self) -> int:
        return _user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)

    def _set_ex_style(self, value: int) -> None:
        _user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, value)

    def apply_styles(self) -> None:
        style = self._ex_style()
        # Drop APPWINDOW if some launcher added it, or a toolwindow can still
        # show up in the taskbar.
        style = (style | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW
        self._set_ex_style(style)
        self._no_activate = True

        # Square, shadowless transient window: the capsule itself is the shape.
        try:
            policy = ctypes.c_int(DWMNCRP_DISABLED)
            _dwmapi.DwmSetWindowAttribute(
                self.hwnd, DWMWA_NCRENDERING_POLICY, ctypes.byref(policy), ctypes.sizeof(policy)
            )
            pref = ctypes.c_int(DWMWCP_DONOTROUND)
            _dwmapi.DwmSetWindowAttribute(
                self.hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(pref), ctypes.sizeof(pref)
            )
        except Exception:
            pass

        self.raise_topmost()

    def raise_topmost(self) -> None:
        _user32.SetWindowPos(
            self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )

    # ------------------------------------------------------------ click-through
    def set_click_through(self, enabled: bool) -> None:
        if enabled == self._click_through:
            return
        style = self._ex_style()
        if enabled:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        self._set_ex_style(style)
        self._click_through = enabled

    def style_flags(self) -> dict:
        """Current extended-style bits, for diagnostics."""
        style = self._ex_style()
        return {
            "layered": bool(style & WS_EX_LAYERED),
            "toolwindow": bool(style & WS_EX_TOOLWINDOW),
            "noactivate": bool(style & WS_EX_NOACTIVATE),
            "clickthrough": bool(style & WS_EX_TRANSPARENT),
            "raw": hex(style),
        }

    # ------------------------------------------------------------------ focus
    def set_accepts_focus(self, accepts: bool) -> None:
        """Toggle WS_EX_NOACTIVATE so text fields (launcher search) can type."""
        if self._no_activate == (not accepts):
            return
        style = self._ex_style()
        if accepts:
            style &= ~WS_EX_NOACTIVATE
        else:
            style |= WS_EX_NOACTIVATE
        self._set_ex_style(style)
        self._no_activate = not accepts

    def focus(self) -> None:
        _user32.SetForegroundWindow(self.hwnd)


# --------------------------------------------------------------------- no-op
class NullOverlay:
    """Used off Windows so the host still starts."""

    def __init__(self, hwnd: int = 0) -> None:
        self.hwnd = 0

    def apply_styles(self) -> None: ...
    def style_flags(self) -> dict: return {"raw": "0x0"}
    def raise_topmost(self) -> None: ...
    def set_click_through(self, enabled: bool) -> None: ...
    def set_accepts_focus(self, accepts: bool) -> None: ...
    def focus(self) -> None: ...


def make_overlay(hwnd: int) -> "Overlay | NullOverlay":
    return Overlay(hwnd) if IS_WINDOWS else NullOverlay(hwnd)
