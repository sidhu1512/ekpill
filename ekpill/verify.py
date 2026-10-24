"""One command that says yes or no.

    python verify.py            # everything that takes seconds
    python verify.py --full     # ...plus the packaged exe and the installer
    python verify.py --no-restart   # leave a live EkPill stopped

Every step's exit status is the command's own: nothing is filtered through a
pipeline that could mask a failure, and the run stops at the first red so the
first error is the one you read. Hotkey combinations are exclusive in Windows,
so the live EkPill is stopped for the duration and restarted afterwards.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

# name, argv — the measured states preview.html is built from.
SHOTS = (
    ("top", ["--selftest", "--pos=top"]),
    ("right", ["--selftest", "--pos=right"]),
    ("right_quick", ["--selftest", "--pos=right", "--page=quick"]),
    ("quick", ["--selftest", "--page=quick"]),
    ("media", ["--selftest", "--page=media"]),
    ("launcher", ["--selftest", "--page=launcher"]),
    ("power", ["--selftest", "--page=power"]),
    ("settings", ["--selftest", "--page=settings"]),
    ("files", ["--selftest", "--page=files"]),
    ("files_menu", ["--selftest", "--page=files", "--menu"]),
    ("audio", ["--selftest", "--page=audio"]),
    ("record", ["--selftest", "--page=record"]),
)

# Behaviour tests; each one restores whatever state it touches.
TESTS = (
    "--test-persist", "--test-hotkeys", "--test-tray", "--test-settings",
    "--test-autohide", "--test-autostart", "--test-rebind", "--test-screens",
    "--test-hotplug", "--test-files",
    "--test-files-ui", "--test-fileops", "--test-close",
    "--test-closekey", "--test-escape", "--test-hover",
    "--test-recorder", "--test-bluetooth",
)


def run(argv: list[str], timeout: int = 120, expect: tuple[str, ...] = ()) -> tuple[bool, str]:
    result = subprocess.run(argv, cwd=HERE, capture_output=True, text=True,
                            timeout=timeout)
    out = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        return False, f"exit {result.returncode}\n{out[-1500:]}"
    for needle in expect:
        if needle not in out:
            return False, f"missing {needle!r} in output:\n{out[-1500:]}"
    return True, out


def step(label: str, argv: list[str], expect: tuple[str, ...] = (), timeout: int = 120) -> bool:
    started = time.monotonic()
    ok, detail = run(argv, timeout=timeout, expect=expect)
    took = time.monotonic() - started
    print(f"[{'ok' if ok else 'FAIL'}] {label:34s} {took:5.1f}s", flush=True)
    if not ok:
        print(detail, flush=True)
    time.sleep(0.5)
    return ok


def live_ekpill_pids() -> list[str]:
    script = ("Get-CimInstance Win32_Process | Where-Object { "
              "($_.Name -eq 'EkPill.exe') -or "
              "(($_.Name -in 'python.exe', 'pythonw.exe') -and ($_.CommandLine -like '*main.py*')) "
              "} | ForEach-Object { $_.ProcessId }")
    try:
        res = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                             capture_output=True, text=True, timeout=30)
    except Exception:
        return []
    return [line.strip() for line in res.stdout.splitlines() if line.strip()]


def stop_live() -> list[str]:
    subprocess.run(["taskkill", "/F", "/IM", "EkPill.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "EkPillSetup.exe"], capture_output=True)
    pids = live_ekpill_pids()
    if not pids:
        return []
    for pid in pids:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Stop-Process -Id {pid} -Force"],
                       capture_output=True, timeout=30)
    print(f"verify: stopped live EkPill (pid {', '.join(pids)}) — "
          "RegisterHotKey combinations are exclusive")
    time.sleep(2)
    return pids


def restart_live() -> None:
    subprocess.Popen(
        [PYTHON, "main.py"], cwd=HERE,
        stdout=open(os.path.join(HERE, "ekpill_run.log"), "ab"),
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        close_fds=True,
    )
    print("verify: live EkPill restarted")


def main() -> int:
    full = "--full" in sys.argv
    results: list[tuple[str, bool]] = []

    def record(label: str, ok: bool) -> bool:
        results.append((label, ok))
        return ok

    record("assets", step("build_assets.py", [PYTHON, "build_assets.py"]))

    stopped = stop_live()
    try:
        for name, argv in SHOTS:
            if not record(f"shot {name}",
                          step(f"selftest {name}", [PYTHON, "main.py", *argv],
                               expect=("selftest: saved=True",))):
                return report(results)
        record("probe", step("hover probe", [PYTHON, "main.py", "--probe"],
                             expect=("click_through=True", "click_through=False")))

        for flag in TESTS:
            if flag in ("--test-hotkeys", "--test-rebind", "--test-closekey"):
                stop_live()
            if not record(flag, step(flag.removeprefix("--"), [PYTHON, "main.py", flag])):
                return report(results)
    finally:
        if stopped and "--no-restart" not in sys.argv:
            restart_live()

    record("preview", step("build_preview.py", [PYTHON, "build_preview.py"]))

    if full:
        record("pyinstaller", step("PyInstaller", [PYTHON, "-m", "PyInstaller",
                                                   "--noconfirm", "EkPill.spec"],
                                   timeout=600))
        exe = os.path.join(HERE, "dist", "EkPill", "EkPill.exe")
        record("packaged selftest",
               step("packaged exe selftest", [exe, "--selftest", "--page=quick"],
                    expect=("selftest: saved=True",), timeout=180))
        setup = os.path.join(HERE, "dist", "EkPillSetup.exe")
        t0 = os.path.getmtime(setup) if os.path.exists(setup) else 0
        compiled = step("Inno Setup compile",
                        [os.path.join(HERE, "build_installer.cmd")] if
                        os.path.exists(os.path.join(HERE, "build_installer.cmd"))
                        else [PYTHON, "build_packaged.py", "--installer-only"],
                        timeout=600)
        fresh = os.path.exists(setup) and os.path.getmtime(setup) > t0
        if compiled and not fresh:
            print("verify: the compiler produced no new EkPillSetup.exe "
                  "(ISCC missing or the compile was skipped) — not a pass")
        record("installer", compiled and fresh)
    return report(results)


def report(results: list[tuple[str, bool]]) -> int:
    failed = [label for label, ok in results if not ok]
    print()
    print(f"verify: {len(results) - len(failed)}/{len(results)} passed")
    if failed:
        print("verify: FAILED: " + ", ".join(failed))
        return 1
    print("verify: ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
