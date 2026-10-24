"""Desktop wallpapers: what is available, what is set, and setting it.

Panacea has a wallpaper carousel because its compositor owns the background.
Windows does not let an app own the desktop, so EkPill does the honest
version: it lists images from a folder the user can fill, plus the art the app
already ships, and hands the chosen path to ``SystemParametersInfoW`` — the
same call the Settings app makes. The fill mode lives in two registry values
beside it (``WallpaperStyle`` and ``TileWallpaper``), which is why the mode is
written there rather than remembered only by the app.

No Qt here: `--test-wallpaper` sets a generated image, reads it back from
Windows, and restores the user's wallpaper and both registry values.
"""

from __future__ import annotations

import os
import sys

IS_WINDOWS = sys.platform == "win32"

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLED = os.path.join(HERE, "assets", "wallpapers")

SPI_SETDESKWALLPAPER = 0x0014
SPI_GETDESKWALLPAPER = 0x0073
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02

DESKTOP_KEY = r"Control Panel\Desktop"

# Windows transcodes PNG/JPEG/BMP for the desktop; anything else has to fail
# visibly instead of being handed over and silently ignored.
WALL_EXTS = (".png", ".jpg", ".jpeg", ".bmp")

# WallpaperStyle / TileWallpaper pairs Windows itself writes.
MODES = {
    "fill": ("10", "0"),
    "fit": ("6", "0"),
    "center": ("0", "0"),
    "span": ("22", "0"),
}
DEFAULT_MODE = "fill"


# ------------------------------------------------------------------- folders
def pictures() -> str:
    return os.path.join(os.environ.get("USERPROFILE")
                        or os.path.expanduser("~"), "Pictures")


def folder() -> str:
    """Where the user's own wallpapers come from.

    ``Pictures\\Wallpapers`` if they made one, otherwise Pictures itself — the
    page never invents a folder under the user's nose.
    """
    custom = os.path.join(pictures(), "Wallpapers")
    return custom if os.path.isdir(custom) else pictures()


def images() -> list[dict]:
    """Bundled art first, then every wallpaper-sized image in the folder.

    Bundled images are marked so the page can label them; the folder is read
    top-level only, because a recursive walk of Pictures is exactly the kind of
    surprise a wallpaper picker should not do.
    """
    out: list[dict] = []
    for where, label in ((BUNDLED, "Bundled"), (folder(), "Pictures")):
        if not os.path.isdir(where):
            continue
        try:
            names = sorted(os.listdir(where))
        except OSError:
            continue
        for name in names:
            path = os.path.join(where, name)
            if not name.lower().endswith(WALL_EXTS) or not os.path.isfile(path):
                continue
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = 0.0
            out.append({
                "path": path,
                "url": "file:///" + path.replace("\\", "/"),
                "name": os.path.splitext(name)[0],
                "file": name,
                "label": label,
                "mtime": mtime,
                "bundled": label == "Bundled",
            })
    return out


# ------------------------------------------------------------------- readback
def current() -> str:
    """The path Windows says is the desktop wallpaper ("" for a solid colour)."""
    if not IS_WINDOWS:
        return ""
    import ctypes

    buffer = ctypes.create_unicode_buffer(1024)
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_GETDESKWALLPAPER, len(buffer), buffer, 0)
    return buffer.value if ok else ""


def mode() -> str:
    """The fill mode as Windows has it, inferred from the two registry values."""
    if not IS_WINDOWS:
        return DEFAULT_MODE
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DESKTOP_KEY) as key:
            style, _ = winreg.QueryValueEx(key, "WallpaperStyle")
            tile, _ = winreg.QueryValueEx(key, "TileWallpaper")
    except OSError:
        return DEFAULT_MODE
    style, tile = str(style), str(tile)
    for name, (want_style, want_tile) in MODES.items():
        if (style, tile) == (want_style, want_tile):
            return name
    return "stretch"                   # 2/0 is Windows' legacy stretch


# --------------------------------------------------------------------- write
def _write_registry(mode_name: str) -> None:
    import winreg

    style, tile = MODES.get(mode_name, MODES[DEFAULT_MODE])
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, DESKTOP_KEY) as key:
        winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, style)
        winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, tile)


def set_image(path: str, mode_name: str = DEFAULT_MODE) -> bool:
    """Make this image the desktop, in this fill mode. True if Windows took it."""
    path = os.path.abspath(os.path.expandvars(os.path.expanduser(str(path))))
    if not os.path.isfile(path) or not path.lower().endswith(WALL_EXTS):
        return False
    if not IS_WINDOWS:
        return False
    if mode_name not in MODES:
        mode_name = DEFAULT_MODE
    import ctypes

    try:
        _write_registry(mode_name)
    except OSError:
        return False
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, path,
        SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
    return bool(ok)


# ------------------------------------------------ registry values, for tests
def registry_state() -> dict:
    """The two values a test must restore, whether or not they exist."""
    if not IS_WINDOWS:
        return {}
    import winreg

    state = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DESKTOP_KEY) as key:
            for name in ("WallpaperStyle", "TileWallpaper"):
                try:
                    state[name] = winreg.QueryValueEx(key, name)[0]
                except OSError:
                    state[name] = None
    except OSError:
        pass
    return state


def restore(wallpaper_path: str, state: dict) -> bool:
    """Put back a wallpaper and the exact registry values found before a test."""
    if not IS_WINDOWS:
        return False
    import ctypes
    import winreg

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, DESKTOP_KEY) as key:
            for name, value in state.items():
                if value is None:
                    try:
                        winreg.DeleteValue(key, name)
                    except OSError:
                        pass
                else:
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, str(value))
    except OSError:
        return False
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, wallpaper_path or None,
        SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
    return bool(ok)
