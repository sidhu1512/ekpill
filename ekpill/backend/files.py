"""Files under the pill: a directory listing, the usual folders, drives, and
the Recycle Bin.

Nothing here imports Qt. The listing, the sort orders, the drive list and the
recycle-bin delete are plain functions, so `--test-files` can drive them (and
undo its own delete) without a window.

Deleting goes through ``SHFileOperationW`` with ``FOF_ALLOWUNDO`` rather than
``os.remove``: a file manager whose only delete cannot be undone is a trap, so
EkPill offers the one Windows can put back.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import sys
from ctypes import wintypes

IS_WINDOWS = sys.platform == "win32"

UMBRELLA = os.environ.get("USERPROFILE") or os.path.expanduser("~")

# The bookmarks, in the order the page shows them. Only folders that exist on
# this machine are returned — a dead link in a shell is worse than no link.
BOOKMARKS = (
    ("Home", UMBRELLA, "\uE80F"),                # home
    ("Desktop", os.path.join(UMBRELLA, "Desktop"), "\uE8FC"),
    ("Documents", os.path.join(UMBRELLA, "Documents"), "\uE8A5"),
    ("Downloads", os.path.join(UMBRELLA, "Downloads"), "\uE896"),
    ("Pictures", os.path.join(UMBRELLA, "Pictures"), "\uEB9F"),
    ("Music", os.path.join(UMBRELLA, "Music"), "\uE8D6"),
    ("Videos", os.path.join(UMBRELLA, "Videos"), "\uE714"),
)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".svg"}
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".wmv", ".m4v"}
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".opus"}
TEXT_EXTS = {".txt", ".md", ".log", ".json", ".py", ".js", ".css", ".html",
             ".csv", ".ini", ".yml", ".yaml", ".toml", ".cfg", ".ps1", ".bat",
             ".cmd", ".sh", ".xml", ".qml"}

# A huge folder (Windows\WinSxS, a Downloads pile) must not stall the capsule
# for seconds; the listing reports the real total and shows the first slice.
LIST_LIMIT = 300

FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4

DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
DRIVE_REMOTE = 4
DRIVE_CDROM = 5
DRIVE_RAMDISK = 6

_DRIVE_KINDS = {
    DRIVE_REMOVABLE: "removable",
    DRIVE_FIXED: "fixed",
    DRIVE_REMOTE: "network",
    DRIVE_CDROM: "optical",
    DRIVE_RAMDISK: "ramdisk",
}


# ------------------------------------------------------------------ helpers
def human_size(size: int) -> str:
    """Bytes as the shortest unit that keeps one decimal place."""
    value = float(max(0, int(size)))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return ""


def kind_of(path: str) -> str:
    """Which viewer a file belongs to: image | video | audio | text | other."""
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in TEXT_EXTS:
        return "text"
    return "other"


def parent(path: str) -> str:
    """The folder above this one, or "" at a drive root."""
    path = os.path.abspath(path)
    above = os.path.dirname(path)
    return above if above and above != path else ""


def _hidden(path: str) -> bool:
    """Hidden, system, or dot-named.

    Windows does not give a dot-name the hidden attribute, but a home folder
    full of tool directories (``.agents``, ``.cargo``, ``.git``) reads as noise
    in a 500px capsule. Explorer would show them; a shell whose whole point is
    one clean capsule does not.
    """
    if os.path.basename(path).startswith("."):
        return True
    if not IS_WINDOWS:
        return False
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    except Exception:
        return False
    if attrs == -1:                      # INVALID_FILE_ATTRIBUTES
        return False
    return bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))


# Folders the signed-in user cannot actually open (C:\Documents and
# Settings, System Volume Information, another user's profile). Probing once
# per path keeps a folder listing from paying for the same denial twice, and
# lets the page dim the row instead of walking into a red error screen.
_ACCESS: dict[str, bool] = {}


def can_enter(path: str) -> bool:
    """True when the folder's contents can be listed by this user."""
    try:
        path = os.path.abspath(str(path))
        if path in _ACCESS:
            return _ACCESS[path]
        if not os.path.isdir(path):
            _ACCESS[path] = False
            return False
        with os.scandir(path) as scan:
            try:
                next(iter(scan), None)
            except (PermissionError, OSError):
                _ACCESS[path] = False
                return False
        ok = True
    except (PermissionError, OSError):
        ok = False
    _ACCESS[path] = ok
    return ok


def _entry(path: str, name: str, is_dir: bool) -> dict:
    try:
        stat = os.stat(path)
        size, mtime = stat.st_size, stat.st_mtime
    except OSError:
        size, mtime = 0, 0.0
    ext = "" if is_dir else os.path.splitext(name)[1].lower().lstrip(".")
    locked = bool(is_dir and not can_enter(path))
    return {
        "name": name,
        "path": path,
        "dir": is_dir,
        "locked": locked,
        "size": int(size),
        "sizeText": "" if is_dir else human_size(size),
        "mtime": float(mtime),
        "date": _date_text(mtime),
        "ext": ext,
        "kind": "folder" if is_dir else kind_of(name),
        "hidden": _hidden(path),
    }


def _date_text(mtime: float) -> str:
    import datetime

    if mtime <= 0:
        return ""
    try:
        return datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return ""


# --------------------------------------------------------------- bookmarks
def bookmarks() -> list[dict]:
    """The usual folders that actually exist here, with their glyphs."""
    out = []
    for name, path, glyph in BOOKMARKS:
        if os.path.isdir(path):
            p = os.path.abspath(path)
            out.append({"name": name, "path": p,
                        "glyph": glyph, "locked": not can_enter(p)})
    return out


# ------------------------------------------------------------------ drives
def drives() -> list[dict]:
    """Every ready drive, with its label and free space.

    Read straight from the Win32 API rather than shelling out to `wmic` or
    PowerShell: this is polled, and a drive list that costs a process launch
    every time is not a drive list you can afford.
    """
    if not IS_WINDOWS:
        return [{"name": "/", "path": "/", "label": "Root", "kind": "fixed",
                 "freeText": "", "sizeText": "", "freeFraction": 0.0, "locked": False}]

    kernel32 = ctypes.windll.kernel32
    buffer = ctypes.create_unicode_buffer(512)
    length = kernel32.GetLogicalDriveStringsW(512, buffer)
    if not length:
        return []

    out: list[dict] = []
    for drive in buffer[:length].split("\x00"):
        drive = drive.strip()
        if not drive:
            continue
        path = drive.rstrip("\\") + "\\"
        drv_type = kernel32.GetDriveTypeW(path)
        if drv_type not in _DRIVE_KINDS:
            continue

        label_buf = ctypes.create_unicode_buffer(261)
        kernel32.GetVolumeInformationW(path, label_buf, 261, None, None,
                                       None, None, 0)
        label = label_buf.value or ""

        free = ctypes.c_ulonglong(0)
        total = ctypes.c_ulonglong(0)
        ok = kernel32.GetDiskFreeSpaceExW(
            path, ctypes.byref(free), ctypes.byref(total), None)
        free_bytes = int(free.value) if ok else 0
        total_bytes = int(total.value) if ok else 0
        out.append({
            "name": drive,
            "path": path,
            "label": label,
            "kind": _DRIVE_KINDS[drv_type],
            "freeText": human_size(free_bytes) if ok else "",
            "sizeText": human_size(total_bytes) if ok else "",
            "freeFraction": (free_bytes / total_bytes) if total_bytes else 0.0,
            "locked": not can_enter(path),
        })
    return out


# ------------------------------------------------------------------ listing
SORTS = ("name", "date", "size")


def list_dir(path: str, sort: str = "name", dirs_first: bool = True,
             limit: int = LIST_LIMIT) -> dict:
    """Read one folder for the page.

    Returns the folder's own facts alongside the entries so a single call can
    describe the whole view — the page never has to keep two sources of truth
    about where it is. An unreadable folder comes back as an error *in the
    result*, not an exception: the UI has somewhere to show it.
    """
    path = os.path.abspath(os.path.expandvars(os.path.expanduser(str(path))))
    result = {
        "path": path,
        "name": os.path.basename(path) or path,
        "parent": parent(path),
        "items": [],
        "total": 0,
        "shown": 0,
        "error": "",
        "denied": False,
    }
    if not os.path.isdir(path):
        result["error"] = "Folder not found"
        return result

    entries: list[dict] = []
    try:
        with os.scandir(path) as scan:
            for entry in scan:
                try:
                    is_dir = entry.is_dir()
                except OSError:
                    continue
                item = _entry(entry.path, entry.name, is_dir)
                if item["hidden"]:
                    continue
                entries.append(item)
    except PermissionError:
        result["error"] = "No access"
        result["denied"] = True
        return result
    except OSError:
        result["error"] = "This folder could not be opened"
        return result

    if sort not in SORTS:
        sort = "name"

    def order(item: dict):
        if sort == "date":
            return (-item["mtime"], item["name"].casefold())
        if sort == "size":
            # Folders have no meaningful size; keep them alphabetical among
            # themselves and ahead of the files when dirs_first is on.
            return (-item["size"] if not item["dir"] else 0,
                    item["name"].casefold())
        return item["name"].casefold()

    if dirs_first:
        entries.sort(key=lambda i: (not i["dir"], order(i)))
    else:
        entries.sort(key=order)

    result["total"] = len(entries)
    result["items"] = entries[:max(0, int(limit))]
    result["shown"] = len(result["items"])
    return result


# ------------------------------------------------------------------ actions
def open_path(path: str) -> bool:
    """Open with whatever Windows has registered — the honest default."""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return False
    try:
        os.startfile(path)             # noqa: S606 - the point of the action
        return True
    except OSError:
        return False


def read_text(path: str, limit: int = 8000) -> str:
    """The first `limit` characters of a text file, for the viewer."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


FO_DELETE = 0x0003
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400


INVALID_NAME_CHARS = set('<>:"/\\|?*')
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _name_error(name: str) -> str:
    """Why Windows would refuse this file name, or "" if it would take it."""
    if not name or name in (".", ".."):
        return "The name is empty"
    if len(name) > 255:
        return "That name is too long"
    if name != name.rstrip(" ."):
        return "Windows drops trailing spaces and dots"
    bad = sorted({ch for ch in name if ch in INVALID_NAME_CHARS or ord(ch) < 32})
    if bad:
        return "A name cannot contain " + " ".join(bad)
    if name.split(".")[0].upper() in RESERVED_NAMES:
        return f"{name.split('.')[0].upper()} is reserved by Windows"
    return ""


def _unique(dest_dir: str, name: str, is_dir: bool) -> str:
    """Explorer's collision answer: `report (2).txt`, `holiday (2)`."""
    base, ext = (name, "") if is_dir else os.path.splitext(name)
    candidate = name
    number = 2
    while os.path.exists(os.path.join(dest_dir, candidate)):
        candidate = f"{base} ({number}){ext}"
        number += 1
    return candidate


def rename(path: str, new_name: str) -> tuple[bool, str]:
    """Rename in place. False carries the reason Windows would give."""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return False, "That item no longer exists"
    new_name = str(new_name)
    error = _name_error(new_name)
    if error:
        return False, error
    target = os.path.join(os.path.dirname(path), new_name)
    if os.path.normcase(target) == os.path.normcase(path):
        return True, ""                 # not a change, not an error
    if os.path.exists(target):
        return False, "Something with that name already exists"
    try:
        os.rename(path, target)
        return True, ""
    except OSError as exc:
        return False, exc.strerror or str(exc)


def _copy_file_responsive(src: str, dst: str) -> None:
    """Copy file data in 1MB chunks and pump UI events if executing on the Qt thread."""
    with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
        while True:
            buf = fsrc.read(1024 * 1024)
            if not buf:
                break
            fdst.write(buf)
            try:
                from PySide6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    app.processEvents()
            except Exception:
                pass
    shutil.copystat(src, dst)


def copy(src: str, dest_dir: str) -> tuple[str | None, str]:
    """Copy a file or a folder tree into `dest_dir`; returns its new path."""
    src = os.path.abspath(str(src))
    dest_dir = os.path.abspath(str(dest_dir))
    if not os.path.exists(src):
        return None, "That item no longer exists"
    if not os.path.isdir(dest_dir):
        return None, "That folder does not exist"
    is_dir = os.path.isdir(src)
    if is_dir:
        a, b = os.path.normcase(src), os.path.normcase(dest_dir)
        if b == a or b.startswith(a + os.sep):
            return None, "A folder cannot be copied into itself"
    target = os.path.join(dest_dir, _unique(dest_dir, os.path.basename(src), is_dir))
    try:
        if is_dir:
            shutil.copytree(src, target, copy_function=_copy_file_responsive)
        else:
            _copy_file_responsive(src, target)
        return target, ""
    except (OSError, shutil.Error) as exc:
        return None, str(exc)


def move(src: str, dest_dir: str) -> tuple[str | None, str]:
    """Move a file or folder into `dest_dir`; never overwrites."""
    src = os.path.abspath(str(src))
    dest_dir = os.path.abspath(str(dest_dir))
    if not os.path.exists(src):
        return None, "That item no longer exists"
    if not os.path.isdir(dest_dir):
        return None, "That folder does not exist"
    is_dir = os.path.isdir(src)
    if is_dir:
        a, b = os.path.normcase(src), os.path.normcase(dest_dir)
        if b == a or b.startswith(a + os.sep):
            return None, "A folder cannot be moved into itself"
    if os.path.normcase(os.path.dirname(src)) == os.path.normcase(dest_dir):
        return None, "It is already in this folder"
    target = os.path.join(dest_dir, _unique(dest_dir, os.path.basename(src), is_dir))
    try:
        shutil.move(src, target)
        return target, ""
    except (OSError, shutil.Error) as exc:
        return None, str(exc)


def new_folder(parent_dir: str, base: str = "New folder") -> tuple[str | None, str]:
    """Create a folder with a name that cannot collide."""
    parent_dir = os.path.abspath(str(parent_dir))
    if not os.path.isdir(parent_dir):
        return None, "That folder does not exist"
    target = os.path.join(parent_dir, _unique(parent_dir, base, True))
    try:
        os.mkdir(target)
        return target, ""
    except OSError as exc:
        return None, exc.strerror or str(exc)


def trash(path: str) -> bool:
    """Send a file or folder to the Recycle Bin; True only if it went.

    A drive root is refused outright: `FOF_ALLOWUNDO` on `C:\\` is a very
    expensive way to learn that a file manager should not offer it.
    """
    path = os.path.abspath(path)
    if not os.path.exists(path) or parent(path) == "":
        return False
    if not IS_WINDOWS:
        try:
            os.remove(path)
            return True
        except OSError:
            return False
    op = _SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = FO_DELETE
    op.pFrom = path + "\0\0"           # double-NUL-terminated list
    op.pTo = None
    op.fFlags = FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    return result == 0 and not op.fAnyOperationsAborted and not os.path.exists(path)
