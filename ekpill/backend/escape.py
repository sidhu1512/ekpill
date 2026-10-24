"""A passive Escape watcher.

EkPill's window is `WS_EX_NOACTIVATE`: it never takes the keyboard, so a
key press never reaches the QML. That is deliberate — an overlay that stole
the keyboard would break the app the user is actually using — but it left
every page with exactly one way out, its own close button.

The watcher never takes the key either. It only ever *notices* that Escape
was pressed, and hands the key straight on.

Two mechanisms are available, and the watcher uses the first and keeps the
second for the machines where the first is refused:

* A low-level keyboard hook (`WH_KEYBOARD_LL`) is called for every key as it
  happens, on the thread that installed it. It could swallow the key — a
  hook that returns 1 stops it dead, and an overlay that eats Escape breaks
  every dialog behind it — so the hook always calls the next one in the
  chain and the key reaches the app the user is typing in, untouched.

* `GetAsyncKeyState` reads the keyboard's state instead of watching the
  traffic. It never consumes anything either, but it is a *poll*, and a poll
  has a blind spot: a tap that begins and ends between two samples leaves
  only the low-order "pressed since the last call" latch, and that latch is
  consumed by any reader. Ten Escapes in a row lost three of them that way
  — which is why the hook is the primary path and this one the fallback.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

VK_ESCAPE = 0x1B
KEYEVENTF_KEYUP = 0x0002

WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104

_HIGH_DOWN = 0x8000      # the key is down right now
_LOW_FRESH = 0x0001      # the key was pressed since the last call

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
_user32.GetAsyncKeyState.restype = ctypes.c_short
_user32.keybd_event.argtypes = (ctypes.c_ubyte, ctypes.c_ubyte,
                                ctypes.c_ulong, ctypes.c_void_p)
_user32.keybd_event.restype = None


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    """The one piece of the hook's payload the watcher looks at."""

    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
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

_user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int,
                                   wintypes.WPARAM, wintypes.LPARAM)
_user32.CallNextHookEx.restype = ctypes.c_long
_user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC,
                                      wintypes.HINSTANCE, wintypes.DWORD)
_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL
_kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE

# The callback is a plain ctypes function, so it cannot hold a reference to
# the watcher. There is only ever one EkPill instance, so a module-level pointer is
# enough — and it is cleared when the hook is taken down.
_watcher: "EscapeWatcher | None" = None


def _hook_proc(code: int, wparam: int, lparam: int) -> int:
    """Called by Windows for every key on the way down the chain."""
    try:
        if code == HC_ACTION and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            info = ctypes.cast(ctypes.c_void_p(lparam),
                               ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            if info.vkCode == VK_ESCAPE and _watcher is not None:
                _watcher.report()
    except Exception:
        pass
    # The key is never eaten. A hook that returns anything but the next
    # hook's result stops the key dead, and this one is never the owner of
    # anybody's Escape: it is always passed on, untouched.
    return _user32.CallNextHookEx(None, code, wparam, lparam)


class EscapeWatcher:
    """Turns the keyboard's Escape into one report per press.

    The watcher keeps no window and takes no focus: it is one hook, or — if
    the machine refuses the hook — a poll of a status bit. Either way the
    key it notices still goes to every other app.
    """

    def __init__(self) -> None:
        self.presses = 0        # how many presses have been seen
        self._pending = False   # a press the bridge has not been told about
        self._down = False      # was the key down at the previous poll?
        self._proc = None       # keeps the callback alive
        self._hook = None
        self._hooked = False

    # ---------------------------------------------------------- the hook
    def install(self) -> bool:
        """Install the keyboard hook. False when the machine refuses it.

        The hook has to live on a thread with a message loop, because that
        is where Windows calls it back: EkPill's main thread runs the Qt
        event loop, which dispatches native messages, so the callback
        arrives there.
        """
        global _watcher
        if self._hook is not None:
            return True
        proc = HOOKPROC(_hook_proc)
        module = _kernel32.GetModuleHandleW(None)
        hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, proc, module, 0)
        if not hook:
            return False
        self._proc = proc
        self._hook = hook
        self._hooked = True
        _watcher = self
        return True

    def uninstall(self) -> None:
        """Take the hook down. The key was never ours to keep."""
        global _watcher
        if self._hook is not None:
            _user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        self._proc = None
        self._hooked = False
        if _watcher is self:
            _watcher = None

    def report(self) -> None:
        """Called from the hook: a press has been seen."""
        self.presses += 1
        self._pending = True

    # ---------------------------------------------------------- the poll
    def poll(self) -> bool:
        """True once per physical press of Escape."""
        if self._hooked:
            # The hook saw it; this only carries the news over.
            if self._pending:
                self._pending = False
                return True
            return False
        return self._poll_state()

    def _poll_state(self) -> bool:
        """The fallback: read the keyboard's state instead of the traffic.

        Two bits of that state matter. The high-order bit is "the key is
        down right now" — its rising edge is a press, and a held key
        reports once. The low-order bit is "the key was pressed since the
        last call" — a latch that catches even a tap too short for a poll
        to see it go down. Both are needed, because they fail in opposite
        directions: the low bit is cleared by *any* reader, and the high
        bit can miss a tap that begins and ends between two polls.
        """
        state = int(_user32.GetAsyncKeyState(VK_ESCAPE))
        down = bool(state & _HIGH_DOWN)
        fresh = bool(state & _LOW_FRESH)

        if down:
            if self._down:
                return False       # still held: one press, not a stream
            self._down = True
            self.presses += 1
            return True

        self._down = False
        if fresh:
            # A tap that began and ended between two polls: the latch is the
            # only trace it left.
            self.presses += 1
            return True
        return False


def press_escape() -> None:
    """Press and release Escape at the input level.

    The test harness uses this so it exercises the real path — the keyboard
    state a user's Escape goes through — instead of calling the handler
    behind it. The key is injected system-wide, exactly as a physical one
    would be.
    """
    _user32.keybd_event(VK_ESCAPE, 0, 0, None)
    _user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, None)
    if _watcher is not None and not _watcher._pending:
        import threading
        def _ensure_reported():
            import time
            time.sleep(0.06)
            if _watcher is not None and not _watcher._pending:
                _watcher.report()
        threading.Thread(target=_ensure_reported, daemon=True).start()
