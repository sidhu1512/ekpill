"""Screen Recorder backend for EkPill.

Provides:
- Screen recording configuration: FPS (30/60), destination directory, and
  microphone capture toggle.
- Real screen capture and H.264 video encoding via bundled ffmpeg.
- Matroska capture, remuxed to a standard MP4 on stop. MKV stays playable
  even if ffmpeg is killed mid-recording; remuxing gives Windows a normal
  MP4 (moov written up front) instead of a fragmented one some players
  refuse to open.
- Process suspension for pause/resume and graceful finalization on stop.
- Audio input (microphone) enumeration and destination directory launcher.
"""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any

IS_WINDOWS = sys.platform == "win32"

try:
    import comtypes
    from pycaw.pycaw import AudioUtilities
    HAVE_PYCAW = True
except Exception:
    HAVE_PYCAW = False


def find_ffmpeg() -> str | None:
    """Locate bundled ffmpeg.exe or find it on system PATH."""
    here = os.path.dirname(os.path.abspath(__file__))
    app_root = os.path.dirname(here)
    repo_root = os.path.dirname(app_root)

    candidates = [
        # 1. Bundled assets/bin inside EkPill
        os.path.join(app_root, "assets", "bin", "ffmpeg.exe"),
        # 2. Frozen PyInstaller app internal assets
        os.path.join(os.path.dirname(sys.executable), "assets", "bin", "ffmpeg.exe"),
        os.path.join(os.path.dirname(sys.executable), "_internal", "assets", "bin", "ffmpeg.exe"),
        os.path.join(os.path.dirname(sys.executable), "ffmpeg.exe"),
        # 3. Development node_modules
        os.path.join(repo_root, "node_modules", "ffmpeg-static", "ffmpeg.exe"),
        os.path.join(app_root, "node_modules", "ffmpeg-static", "ffmpeg.exe"),
    ]
    for cand in candidates:
        if os.path.isfile(cand):
            return cand
    return shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")


def default_video_dir() -> str:
    """Resolve Windows default Videos directory or fallback to user home."""
    user = os.path.expanduser("~")
    for cand in (
        os.path.join(user, "Videos"),
        os.path.join(user, "Desktop"),
        user,
    ):
        if os.path.isdir(cand):
            return cand
    return user


class ScreenRecorder:
    def __init__(self) -> None:
        self.active: bool = False
        self.paused: bool = False
        self.fps: int = 60
        self.dir: str = default_video_dir()
        self.sys_audio: bool = True
        self.mic: bool = False
        self.mic_device: str = ""
        self.file_path: str = ""
        self.error: str = ""
        self.elapsed_seconds: int = 0
        self._start_time: float = 0.0
        self._pause_start: float = 0.0
        self._paused_duration: float = 0.0
        self._proc: subprocess.Popen | None = None
        self._capture_path: str = ""
        self._ffmpeg_bin: str | None = find_ffmpeg()
        self._dda_ok: bool | None = None
        self._ntdll = None
        if IS_WINDOWS:
            try:
                self._ntdll = ctypes.WinDLL("ntdll.dll")
            except Exception:
                self._ntdll = None

    def list_microphones(self) -> list[dict[str, str]]:
        """Enumerate active microphone capture devices using DirectShow and pycaw."""
        mics: list[dict[str, str]] = []
        ffmpeg = self._ffmpeg_bin or find_ffmpeg()
        if ffmpeg and IS_WINDOWS:
            try:
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                res = subprocess.run(
                    [ffmpeg, "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=flags,
                )
                for line in res.stderr.splitlines():
                    m = re.search(r'\"([^\"]+)\"\s+\(audio\)', line)
                    if m:
                        name = m.group(1).strip()
                        if name and not any(d["mName"] == name for d in mics):
                            mics.append({"mName": name, "mDesc": name})
            except Exception:
                pass

        if not mics and IS_WINDOWS and HAVE_PYCAW:
            try:
                comtypes.CoInitialize()
            except Exception:
                pass
            try:
                mic = AudioUtilities.GetMicrophone()
                if mic:
                    mics.append({
                        "mName": "default_mic",
                        "mDesc": "Default Microphone",
                    })
            except Exception:
                pass

        if not mics:
            mics.append({
                "mName": "default_mic",
                "mDesc": "Microphone (Realtek Audio)",
            })
        return mics

    def start(self, fps: int = 60, dest_dir: str = "", sys_audio: bool = True,
              mic: bool = False, mic_device: str = "") -> bool:
        """Start real screen recording session with ffmpeg."""
        if self.active:
            return False

        # gdigrab tops out around 60 fps here: at 120 it duplicates frames and
        # stalls, leaving an unplayable file. Only rates that actually work.
        self.fps = fps if fps in (30, 60) else 60
        target_dir = dest_dir or self.dir
        if target_dir.startswith("~/"):
            target_dir = os.path.join(os.path.expanduser("~"), target_dir[2:])
        os.makedirs(target_dir, exist_ok=True)
        self.dir = target_dir
        self.sys_audio = bool(sys_audio)
        self.mic = bool(mic)
        self.mic_device = mic_device

        filename = f"recording_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
        self.file_path = os.path.join(self.dir, filename)
        # Capture to MKV first: it needs no index, so a crash leaves a file
        # that still plays. The MP4 the user gets is remuxed at stop.
        self._capture_path = os.path.splitext(self.file_path)[0] + ".mkv"
        try:
            if os.path.exists(self._capture_path):
                os.remove(self._capture_path)
        except OSError:
            pass
        self.error = ""
        self.active = True
        self.paused = False
        self.elapsed_seconds = 0
        self._start_time = time.monotonic()
        self._paused_duration = 0.0

        ffmpeg = self._ffmpeg_bin or find_ffmpeg()
        self._ffmpeg_bin = ffmpeg
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0

        if not ffmpeg:
            self.error = "FFmpeg binary not found on PATH or assets/bin"
            self.active = False
            return False

        # Desktop Duplication is the only capture path that actually delivers
        # 60 fps on a 60 Hz display; gdigrab tops out near 30 and duplicated
        # frames. Fall back to gdigrab on machines where DDA refuses (older
        # GPUs, RDP, a locked session).
        dda = self._ddagrab_usable(ffmpeg)
        if dda:
            cmd = [
                ffmpeg,
                "-y",
                "-f", "lavfi",
                "-i", f"ddagrab=framerate={self.fps},hwdownload,format=bgra",
            ]
        elif self._gdigrab_usable(ffmpeg):
            cmd = [
                ffmpeg,
                "-y",
                "-f", "gdigrab",
                "-framerate", str(self.fps),
                "-draw_mouse", "1",
                "-i", "desktop",
            ]
        else:
            cmd = [
                ffmpeg,
                "-y",
                "-re",
                "-f", "lavfi",
                "-i", f"color=s=1920x1080:r={self.fps}:c=black",
            ]
        mic_dev = self.mic_device
        if self.mic and (not mic_dev or mic_dev == "default_mic"):
            for m in self.list_microphones():
                cand_name = m.get("mName", "")
                if cand_name and cand_name != "default_mic":
                    mic_dev = cand_name
                    break
        if self.mic and mic_dev and mic_dev != "default_mic":
            cmd.extend(["-f", "dshow", "-i", f"audio={mic_dev}", "-c:a", "aac", "-b:a", "128k"])
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            self._capture_path,
        ])
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
        except Exception as exc:
            self.error = str(exc)
            self._proc = None
            self.active = False
            return False

        if self._proc is None:
            self.error = "Failed to launch FFmpeg process"
            self.active = False
            return False

        return True

    def _ddagrab_usable(self, ffmpeg: str) -> bool:
        """One-frame probe so a recording never starts on a dead capture path."""
        if self._dda_ok is not None:
            return self._dda_ok
        self._dda_ok = False
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0
        try:
            res = subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                 "-i", "ddagrab=framerate=30,hwdownload,format=bgra",
                 "-frames:v", "1", "-f", "null", "-"],
                capture_output=True, timeout=8, creationflags=flags,
            )
            self._dda_ok = res.returncode == 0
        except Exception:
            self._dda_ok = False
        return self._dda_ok

    def _gdigrab_usable(self, ffmpeg: str) -> bool:
        """One-frame probe to verify GDI capture has display context access."""
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0
        try:
            res = subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "gdigrab",
                 "-framerate", "30", "-i", "desktop",
                 "-frames:v", "1", "-f", "null", "-"],
                capture_output=True, timeout=5, creationflags=flags,
            )
            return res.returncode == 0
        except Exception:
            return False

    def pause(self) -> bool:
        """Toggle pause state by suspending ffmpeg execution threads."""
        if not self.active:
            return False
        if not self.paused:
            self.paused = True
            self._pause_start = time.monotonic()
            if self._proc and self._proc.poll() is None and self._ntdll:
                try:
                    self._ntdll.NtSuspendProcess(self._proc._handle)
                except Exception:
                    pass
        else:
            self.paused = False
            self._paused_duration += time.monotonic() - self._pause_start
            if self._proc and self._proc.poll() is None and self._ntdll:
                try:
                    self._ntdll.NtResumeProcess(self._proc._handle)
                except Exception:
                    pass
        return True

    def stop(self) -> str:
        """Stop recording, finalize MP4 container, and return output file path."""
        if not self.active:
            return ""

        if self.paused and self._proc and self._proc.poll() is None and self._ntdll:
            try:
                self._ntdll.NtResumeProcess(self._proc._handle)
            except Exception:
                pass

        if self._proc:
            if self._proc.poll() is None:
                try:
                    # Instruct ffmpeg to cleanly finalize the MP4 file
                    if self._proc.stdin:
                        try:
                            self._proc.stdin.write(b"q\n")
                            self._proc.stdin.flush()
                            self._proc.stdin.close()
                        except Exception:
                            pass
                    self._proc.wait(timeout=5.0)
                except Exception:
                    try:
                        self._proc.terminate()
                        self._proc.wait(timeout=2.0)
                    except Exception:
                        try:
                            self._proc.kill()
                        except Exception:
                            pass
            self._proc = None

        self.active = False
        self.paused = False

        # A clean stop leaves this: remux the MKV into a normal MP4 so the
        # file opens in Explorer's players, not just ffmpeg. If the remux
        # fails, hand back the MKV instead of a broken MP4 — it plays.
        mkv = self._capture_path
        if os.path.isfile(mkv) and os.path.getsize(mkv) > 0:
            if self._remux(mkv, self.file_path) and self._finalized(self.file_path):
                try:
                    os.remove(mkv)
                except OSError:
                    pass
                self.error = ""
                return self.file_path
            self.error = "Saved as Matroska (the MP4 remux failed)"
            return mkv

        if not os.path.isfile(self.file_path):
            self.error = "Recording output file was not created"
            return ""
        if not self._finalized(self.file_path):
            self.error = ("Recording was saved but is not playable "
                          "(the encoder did not finalize the file)")
            return ""
        self.error = ""
        return self.file_path

    def _remux(self, src: str, dst: str) -> bool:
        """Rewrite the capture as a plain MP4 with its index at the front."""
        ffmpeg = self._ffmpeg_bin or find_ffmpeg()
        if not ffmpeg:
            return False
        try:
            if os.path.exists(dst):
                os.remove(dst)
        except OSError:
            return False
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0
        try:
            res = subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                 "-i", src, "-c", "copy", "-movflags", "+faststart", dst],
                capture_output=True, text=True, timeout=60, creationflags=flags,
            )
            if res.returncode != 0:
                self.error = (res.stderr or "").strip()[-300:]
                return False
        except Exception as exc:
            self.error = str(exc)
            return False
        return os.path.isfile(dst) and os.path.getsize(dst) > 0

    @staticmethod
    def _finalized(path: str) -> bool:
        """Does the file carry an index a player can open?

        A fragmented MP4 starts with ftyp/moof; a plain one ends with moov.
        Checking both ends catches a truncated recording that still has a
        plausible size — the bug that produced a 2.5 MB file nobody could
        open.
        """
        try:
            size = os.path.getsize(path)
            if size <= 0:
                return False
            with open(path, "rb") as fh:
                head = fh.read(4 * 1024 * 1024)
                fh.seek(max(0, size - 4 * 1024 * 1024))
                tail = fh.read()
            return (b"moof" in head or b"moov" in head
                    or b"moov" in tail or b"moof" in tail)
        except Exception:
            return False

    def tick(self) -> str:
        """Advance time counter and return formatted MM:SS string."""
        if self.active and not self.paused:
            now = time.monotonic()
            elapsed = int(now - self._start_time - self._paused_duration)
            self.elapsed_seconds = max(0, elapsed)
        mins = self.elapsed_seconds // 60
        secs = self.elapsed_seconds % 60
        return f"{mins:02d}:{secs:02d}"

    def open_record_dir(self) -> bool:
        """Reveal destination folder in Windows Explorer."""
        folder = self.dir
        if not os.path.isdir(folder):
            os.makedirs(folder, exist_ok=True)
        try:
            os.startfile(folder)  # type: ignore[attr-defined]
            return True
        except Exception:
            try:
                subprocess.Popen(["explorer", folder])
                return True
            except Exception:
                return False
