"""Build everything a user can double-click: assets, the exe, the installer.

    python build_packaged.py

Runs the three stages in order and stops at the first failure:

1.  `build_assets.py` — copies the tray icon and regenerates the multi-size
    .ico from ../app_art_assets.
2.  PyInstaller with `EkPill.spec` — the one-folder app in dist\\EkPill.
3.  Inno Setup (`ISCC.exe`) — dist\\EkPillSetup.exe, if the compiler is
    available. It is not something this repo can assume is installed, so a
    missing compiler prints where to get it instead of failing the build.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ISCC_CANDIDATES = (
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
)


def run(label: str, argv: list[str]) -> bool:
    print(f"== {label}: {' '.join(argv)}")
    result = subprocess.run(argv, cwd=HERE)
    print(f"== {label}: exit {result.returncode}")
    return result.returncode == 0


def find_iscc() -> str | None:
    override = os.environ.get("ISCC")
    if override and os.path.exists(override):
        return override
    found = shutil.which("ISCC") or shutil.which("ISCC.exe")
    if found:
        return found
    for path in ISCC_CANDIDATES:
        if os.path.exists(path):
            return path
    # A per-user install keeps ISCC under %TEMP% (this machine's copy lives in
    # %TEMP\is6), which no fixed candidate can guess — glob for it, newest first.
    temp = os.environ.get("TEMP") or os.environ.get("TMP")
    if temp:
        for hit in sorted(glob.glob(os.path.join(temp, "is*", "ISCC.exe")),
                          reverse=True):
            if os.path.exists(hit):
                return hit
    return None


def main() -> int:
    only_installer = "--installer-only" in sys.argv
    if not only_installer:
        if not run("assets", [sys.executable, "build_assets.py"]):
            return 1
        if not run("pyinstaller", [sys.executable, "-m", "PyInstaller",
                                   "--noconfirm", "EkPill.spec"]):
            return 1
    # The packaged app must run the same checks the source does; a green
    # PyInstaller log is not proof the frozen QML/WinRT imports survived.
    exe = os.path.join(HERE, "dist", "EkPill", "EkPill.exe")
    if not only_installer and not run("packaged selftest",
                                      [exe, "--selftest", "--page=quick"]):
        return 1

    iscc = find_iscc()
    if iscc is None:
        print("installer: ISCC.exe not found — install Inno Setup 6 "
              "(https://jrsoftware.org/isinfo.php) and re-run, or compile "
              "installer.iss by hand.")
        return 0          # the app is built; the installer is optional
    if not run("inno", [iscc, "installer.iss"]):
        return 1
    setup = os.path.join(HERE, "dist", "EkPillSetup.exe")
    size = os.path.getsize(setup) / (1024 * 1024) if os.path.exists(setup) else 0
    print(f"installer: {setup} ({size:.1f} MB)")
    output_dir = os.path.join(HERE, "Output")
    os.makedirs(output_dir, exist_ok=True)
    output_setup = os.path.join(output_dir, "EkPillSetup.exe")
    shutil.copy2(setup, output_setup)
    print(f"installer: mirrored to {output_setup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
