"""Start-with-Windows, as a shortcut in the user's Startup folder.

The shortcut *is* the state: there is no second copy in settings.json to drift
out of step with it, so `is_enabled()` simply asks the filesystem. The folder
is per-user and needs no elevation, unlike a Run-key write under HKLM.

Creating a real `.lnk` needs the Shell's own writer (WScript.Shell), which is a
COM object; driving it through a hidden PowerShell keeps this a subprocess of
the same shape the ms-settings actions already use, and it works identically
under the packaged exe and the source tree.
"""

from __future__ import annotations

import os
import subprocess
import sys

IS_FROZEN = bool(getattr(sys, "frozen", False))
APP_NAME = "EkPill"


def startup_dir() -> str:
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                        "Programs", "Startup")


def shortcut_path() -> str:
    return os.path.join(startup_dir(), f"{APP_NAME}.lnk")


def target() -> tuple[str, str, str]:
    """(executable, arguments, working directory) for what should start."""
    if IS_FROZEN:
        # The frozen exe runs itself; there is no interpreter to call.
        return sys.executable, "", os.path.dirname(sys.executable)
    # From source: python main.py, with the script's own folder as cwd so the
    # relative qml/ and assets/ paths resolve.
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main_py = os.path.join(here, "main.py")
    return sys.executable, f'"{main_py}"', here


def is_enabled() -> bool:
    return os.path.exists(shortcut_path())


def set_enabled(on: bool) -> bool:
    path = shortcut_path()
    if not on:
        try:
            if os.path.exists(path):
                os.remove(path)
            return not os.path.exists(path)
        except OSError:
            return False

    exe, args, workdir = target()
    # WScript.Shell escapes: single quotes doubled inside the PS single-quoted
    # literals; nothing else in these paths can contain a quote.
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut("
        f"'{path.replace(chr(39), chr(39) * 2)}'); "
        f"$s.TargetPath = '{exe.replace(chr(39), chr(39) * 2)}'; "
        f"$s.Arguments = '{args.replace(chr(39), chr(39) * 2)}'; "
        f"$s.WorkingDirectory = '{workdir.replace(chr(39), chr(39) * 2)}'; "
        "$s.Save()"
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, creationflags=creationflags,
    )
    return result.returncode == 0 and os.path.exists(path)