"""Clipboard history — EkPill's own copy of what you copied.

Windows keeps the Win+V history inside the shell and hands none of it to other
apps, so EkPill records its own: text only, newest first, deduplicated,
capped. State lives in a file *beside* settings.json rather than inside it —
this is user content, not configuration, and deleting `clipboard.json` is
deleting the history, which should be one file gone and nothing else to reset.

Recording is **off by default**: clipboards routinely carry secrets (password
managers put them there), and nothing should write those to disk before the
user has asked for it. `bridge.py` owns the OS signal; this module owns the
state and stays Qt-free so it can be tested on its own.
"""

from __future__ import annotations

import json
import os
import tempfile
import time

CAP = 50             # entries kept, newest first
ENTRY_MAX = 1500     # characters stored per entry (the page shows one row)


def path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "EkPill", "clipboard.json")


class History:
    def __init__(self, cap: int = CAP):
        self.cap = int(cap)
        self.items: list[dict] = []      # {"text": str, "time": float}

    # ------------------------------------------------------------- mutation
    def add(self, text, when=None) -> bool:
        """Put *text* at the front. Blank/non-string input is ignored and a
        repeat copy moves its existing entry up instead of duplicating it.
        Returns True when the visible list changed."""
        if not isinstance(text, str) or not text.strip():
            return False
        stored = text if len(text) <= ENTRY_MAX else text[:ENTRY_MAX] + "…"
        kept = [i for i in self.items if i["text"] != stored]
        kept.insert(0, {"text": stored, "time": float(when or time.time())})
        self.items = kept[: self.cap]
        return True

    def remove(self, index) -> bool:
        if isinstance(index, int) and 0 <= index < len(self.items):
            del self.items[index]
            return True
        return False

    def clear(self) -> bool:
        if not self.items:
            return False
        self.items.clear()
        return True

    # ------------------------------------------------------------- the file
    def load(self) -> None:
        """Read the store; unreadable or malformed simply starts empty — a
        corrupt history file must never take the shell down with it."""
        try:
            with open(path(), "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception:
            return
        if not isinstance(raw, list):
            return
        items: list[dict] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            text = entry.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            try:
                when = float(entry.get("time", 0) or 0)
            except (TypeError, ValueError):
                when = 0.0
            items.append({"text": text[: ENTRY_MAX + 1], "time": when})
            if len(items) >= self.cap:
                break
        self.items = items

    def save(self) -> bool:
        """Atomic temp-file + rename, like persist.save: a crash mid-write must
        not leave a half-written history behind."""
        target = path()
        folder = os.path.dirname(target)
        try:
            os.makedirs(folder, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix="clipboard.", suffix=".tmp", dir=folder)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.items, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, target)
            return True
        except Exception:
            return False