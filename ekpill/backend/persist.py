"""Where EkPill lives between runs.

Three values survive a restart: the dock edge, whether EkPill is pinned
open, and which page was up. That is 120 bytes, so it is a plain JSON file
next to the app's other state instead of QSettings' platform indirection — the
file has to be readable by a human debugging a machine and by the test harness
that proves the round-trip.

Writes are atomic (temp file + rename): a crash mid-save must never leave a
half-written file that boots EkPill at a position that does not exist.
"""

from __future__ import annotations

import json
import os
import tempfile

POSITIONS = ("top", "right")
# Two edges now. Old files that say left/bottom fold into the top edge rather
# than making the capsule boot off-screen.
LEGACY_POSITIONS = {"left": "top", "bottom": "top"}
# "viewer" and "media" are deliberately absent: they need an active session/file,
# so a restart lands back on the normal capsule rather than trapped on media/viewer.
PAGES = ("", "quick", "launcher", "power", "settings",
         "files", "audio", "record")

# A copy of the defaults lives here rather than an import from hotkeys.py:
# persistence has to stay importable without pulling Qt into it.
#
# "close" is the third combination EkPill owns, and it is the only one
# with no default: an empty string means "no combination is bound", which is
# a state the map has to be able to hold.
HOTKEY_NAMES = ("launcher", "close")
HOTKEY_DEFAULTS = {"launcher": "Ctrl+Alt+L", "close": ""}

# What `--test-persist` plants before boot: deliberately not the defaults, so a
# pass proves restore ran rather than observing the default state.
TEST_SEED = {"pos": "right", "pinned": True, "page": "power", "dnd": False,
             "autohide": False, "hotkeys": dict(HOTKEY_DEFAULTS)}


_suppressed = False


def suppress(on: bool) -> None:
    """Hold off writes while restore applies properties one by one.

    Applying pillPos, pinned and page fires three change handlers; without this
    gate each would overwrite the file with a half-applied state, and a crash
    in between would lose the page. Restore writes once at the end instead.
    """
    global _suppressed
    _suppressed = bool(on)


def defaults() -> dict:
    return {"pos": "top", "pinned": False, "page": "", "dnd": False,
            "autohide": True, "hotkeys": dict(HOTKEY_DEFAULTS),
            # Escape closes EkPill by default; the switch exists for the
            # people who want Escape to belong to every app they open.
            "esc": True,
            # Whether the one-time "Esc closes" hint has already been shown.
            "hint": False,
            # Recorder preferences
            "rec_fps": 60, "rec_dir": "", "rec_sys_audio": True,
            "rec_mic": False, "rec_mic_device": ""}


def _clean_hotkeys(raw) -> dict:
    """Only our names, only strings: the parser judges the strings later.

    "close" is the one name that may be empty, and an empty combination is
    how "no close key" is spelled.
    """
    if not isinstance(raw, dict):
        return dict(HOTKEY_DEFAULTS)
    out = dict(HOTKEY_DEFAULTS)
    for name in HOTKEY_NAMES:
        value = raw.get(name)
        if not isinstance(value, str):
            continue
        value = value.strip()
        if value or name == "close":
            out[name] = value
    return out


def path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "EkPill", "settings.json")


def exists() -> bool:
    return os.path.exists(path())


def load() -> dict:
    """Validated state; anything unreadable or out of range falls back."""
    try:
        with open(path(), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception:
        return defaults()
    if not isinstance(raw, dict):
        return defaults()

    pos = str(raw.get("pos", ""))
    page = str(raw.get("page", ""))
    pinned = bool(raw.get("pinned", False))
    state = defaults()
    if pos in LEGACY_POSITIONS:
        pos = LEGACY_POSITIONS[pos]
    state["pos"] = pos if pos in POSITIONS else defaults()["pos"]
    # An unpinned capsule has no visible page to come back to.
    state["page"] = page if (pinned and page in PAGES) else ""
    state["pinned"] = pinned
    state["dnd"] = bool(raw.get("dnd", False))
    state["autohide"] = bool(raw.get("autohide", True))
    state["hotkeys"] = _clean_hotkeys(raw.get("hotkeys"))
    state["esc"] = bool(raw.get("esc", True))
    state["hint"] = bool(raw.get("hint", False))
    fps = raw.get("rec_fps", 60)
    state["rec_fps"] = int(fps) if fps in (30, 60) else 60
    state["rec_dir"] = str(raw.get("rec_dir", ""))
    state["rec_sys_audio"] = bool(raw.get("rec_sys_audio", True))
    state["rec_mic"] = bool(raw.get("rec_mic", False))
    state["rec_mic_device"] = str(raw.get("rec_mic_device", ""))
    return state


def save(state: dict) -> bool:
    """Write a full state; unknown keys are ignored, invalid values normalised."""
    if _suppressed:
        return True
    if not isinstance(state, dict):
        state = {}
    pos = str(state.get("pos", "top"))
    page = str(state.get("page", ""))
    pinned = bool(state.get("pinned", False))
    state = {
        "pos": LEGACY_POSITIONS.get(pos, pos) if (pos in POSITIONS or pos in LEGACY_POSITIONS) else "top",
        "pinned": pinned,
        "page": page if (pinned and page in PAGES) else "",
        "dnd": bool(state.get("dnd", False)),
        "autohide": bool(state.get("autohide", True)),
        "hotkeys": _clean_hotkeys(state.get("hotkeys")),
        "esc": bool(state.get("esc", True)),
        "hint": bool(state.get("hint", False)),
        "rec_fps": (int(state.get("rec_fps", 60))
                    if state.get("rec_fps", 60) in (30, 60) else 60),
        "rec_dir": str(state.get("rec_dir", "")),
        "rec_sys_audio": bool(state.get("rec_sys_audio", True)),
        "rec_mic": bool(state.get("rec_mic", False)),
        "rec_mic_device": str(state.get("rec_mic_device", "")),
    }
    target = path()
    folder = os.path.dirname(target)
    try:
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="settings.", suffix=".tmp", dir=folder)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
        os.replace(tmp, target)
        return True
    except Exception:
        return False


def update(**fields) -> bool:
    """Merge single fields into what is on disk (used for do-not-disturb)."""
    return save({**load(), **fields})


# --- raw access, used only by the round-trip test --------------------------

def read_raw() -> str | None:
    try:
        with open(path(), "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return None


def write_raw_text(text: str | None) -> None:
    """Put the file back exactly as it was — or remove what the test planted."""
    target = path()
    folder = os.path.dirname(target)
    try:
        if text is None:
            if os.path.exists(target):
                os.remove(target)
            return
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="settings.", suffix=".tmp", dir=folder)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, target)
    except Exception:
        pass
