"""WASAPI / pycaw per-app audio mixer and real-time reactive audio visualizer.

Provides:
- Per-application volume control and mute toggling via Windows Core Audio (WASAPI/pycaw)
- Master audio peak level monitoring via IAudioMeterInformation
- Reactive multi-band audio visualizer wave calculations
"""

from __future__ import annotations

import ctypes
import math
import os
import sys
import time
from ctypes import wintypes
from typing import Any

IS_WINDOWS = sys.platform == "win32"

# Resolves the *indirect* strings Windows stores for sessions with no process
# behind them (`@%SystemRoot%\System32\AudioSrv.Dll,-202`). Explorer uses the
# same call to draw the same row.
_shlwapi = None
if IS_WINDOWS:
    try:
        _shlwapi = ctypes.WinDLL("shlwapi", use_last_error=True)
        _shlwapi.SHLoadIndirectString.argtypes = (
            wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_uint, ctypes.c_void_p)
        _shlwapi.SHLoadIndirectString.restype = ctypes.c_long
    except Exception:
        _shlwapi = None

try:
    import comtypes
    from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume, IAudioEndpointVolume, IAudioMeterInformation
    HAVE_PYCAW = True
except Exception:
    HAVE_PYCAW = False


def _friendly_session_name(raw: str) -> str:
    """Turn a session's display name into a label a person can read.

    A session that is not an application has no process to name it after, so
    Windows reports `s.DisplayName` instead — and for the system-sounds session
    that is an *indirect* string, a pointer into AudioSrv.dll's resource table
    rather than a name. Drawn as-is it was the one row in the mixer that read
    like a crash ("@%SystemRoot%\\System32\\AudioSrv.Dll,-202"). Resolve it the
    way Explorer does, and fall back to plain words if the machine refuses.
    """
    if raw.startswith("@"):
        if _shlwapi is not None:
            buf = ctypes.create_unicode_buffer(256)
            try:
                if _shlwapi.SHLoadIndirectString(raw, buf, len(buf), None) == 0 and buf.value:
                    raw = buf.value
            except Exception:
                pass
        if raw.startswith("@") or ".dll" in raw.lower():
            return "System sounds" if "audiosrv" in raw.lower() else "System Audio"

    name = raw.strip()
    if name.lower().endswith(".exe"):
        name = name[:-4]
    # A bare DLL/indirect string that slipped through is never a name.
    if not name or name.startswith("@") or "\\" in name:
        return "System Audio"
    if name.islower() or name.isupper():
        name = name.capitalize()
    return name


class AudioService:
    def __init__(self) -> None:
        self._last_peak: float = 0.0
        self._meter = None
        self._device_name: str = "Default Output"
        if IS_WINDOWS and HAVE_PYCAW:
            try:
                speakers = AudioUtilities.GetSpeakers()
                if speakers:
                    self._device_name = getattr(speakers, "FriendlyName", "Default Output")
                    if hasattr(speakers, "_dev") and speakers._dev:
                        from ctypes import POINTER, cast
                        interface = speakers._dev.Activate(IAudioMeterInformation._iid_, comtypes.CLSCTX_ALL, None)
                        self._meter = cast(interface, POINTER(IAudioMeterInformation))
            except Exception:
                self._meter = None

    def get_device_name(self) -> str:
        """Return the friendly name of the active audio output endpoint.

        Resolved on each read: the cached name kept saying "Speakers (Realtek)"
        after the user switched to Bluetooth headphones.
        """
        if IS_WINDOWS and HAVE_PYCAW:
            try:
                speakers = AudioUtilities.GetSpeakers()
                name = getattr(speakers, "FriendlyName", "") if speakers else ""
                if name:
                    self._device_name = name
            except Exception:
                pass
        return self._device_name

    def list_output_devices(self) -> list[str]:
        """Enumerate active hardware audio output devices via WASAPI."""
        if not (IS_WINDOWS and HAVE_PYCAW):
            return [self._device_name]
        devs: list[str] = []
        try:
            for d in AudioUtilities.GetAllDevices():
                dev_id = getattr(d, "id", "")
                name = getattr(d, "FriendlyName", "")
                if not dev_id.startswith("{0.0.0.") or not name:
                    continue
                # 1 == DEVICE_STATE_ACTIVE. GetAllDevices also lists disabled
                # and unplugged endpoints — the "three outputs" that were
                # really one speaker plus two dead Bluetooth bonds.
                try:
                    if int(d._dev.GetState()) != 1:
                        continue
                except Exception:
                    pass
                if name not in devs:
                    devs.append(name)
        except Exception:
            pass
        return devs or [self._device_name]

    def list_streams(self) -> list[dict[str, Any]]:
        """List active per-application audio streams with name, volume, and mute state."""
        if not (IS_WINDOWS and HAVE_PYCAW):
            return []

        streams: list[dict[str, Any]] = []
        seen: set[str] = set()
        try:
            sessions = AudioUtilities.GetAllSessions()
            for s in sessions:
                try:
                    vol_ctl = s.SimpleAudioVolume
                    if vol_ctl is None:
                        continue
                    vol = float(vol_ctl.GetMasterVolume())
                    muted = bool(vol_ctl.GetMute())
                    pid = s.ProcessId or 0
                    p_name = ""
                    p_bin = ""
                    if s.Process:
                        p_name = s.Process.name()
                        p_bin = p_name
                    elif s.DisplayName:
                        p_name = s.DisplayName
                    else:
                        p_name = "System Audio"

                    # System sounds own a fixed, always-present session with
                    # no process. Drawing it put a permanent "System Sounds"
                    # slider at the bottom of the mixer that could not be
                    # tied to anything the user was doing; Windows' own mixer
                    # shows it under System, not as an app.
                    if not pid:
                        continue

                    display_name = _friendly_session_name(p_name)

                    # The id keeps the *raw* name: set_app_volume looks the
                    # session up again by it, and the resolved label would
                    # never match on the way back.
                    sid = f"{pid}_{p_bin or p_name}"
                    if sid in seen:
                        # One app can own several sessions (a browser with a
                        # few tabs); repeating its row with separate sliders
                        # is noise, not information.
                        continue
                    seen.add(sid)
                    streams.append({
                        "id": sid,
                        "pid": pid,
                        "name": display_name,
                        "binary": p_bin or p_name,
                        "volume": round(vol, 3),
                        "volume_pct": int(round(vol * 100)),
                        "muted": muted,
                    })
                except Exception:
                    continue
        except Exception:
            pass
        # Applications first, the system-sounds catch-all last.
        streams.sort(key=lambda s: (s["name"].lower().startswith("system sound"),
                                    s["name"].lower()))
        return streams

    def set_app_volume(self, stream_id: str, pct: int) -> bool:
        """Set volume percentage (0..100) for a given stream session."""
        if not (IS_WINDOWS and HAVE_PYCAW):
            return False

        target_vol = max(0.0, min(1.0, pct / 100.0))
        try:
            sessions = AudioUtilities.GetAllSessions()
            for s in sessions:
                pid = s.ProcessId or 0
                p_bin = s.Process.name() if s.Process else ""
                sid = f"{pid}_{p_bin or (s.DisplayName or 'System Audio')}"
                if sid == stream_id or str(pid) == stream_id or (p_bin and p_bin.lower() == stream_id.lower()):
                    s.SimpleAudioVolume.SetMasterVolume(target_vol, None)
                    return True
        except Exception:
            pass
        return False

    def toggle_app_mute(self, stream_id: str) -> bool:
        """Toggle mute state for a given stream session."""
        if not (IS_WINDOWS and HAVE_PYCAW):
            return False

        try:
            sessions = AudioUtilities.GetAllSessions()
            for s in sessions:
                pid = s.ProcessId or 0
                p_bin = s.Process.name() if s.Process else ""
                sid = f"{pid}_{p_bin or (s.DisplayName or 'System Audio')}"
                if sid == stream_id or str(pid) == stream_id or (p_bin and p_bin.lower() == stream_id.lower()):
                    cur = bool(s.SimpleAudioVolume.GetMute())
                    s.SimpleAudioVolume.SetMute(not cur, None)
                    return True
        except Exception:
            pass
        return False

    def get_peak(self) -> float:
        """Read master output peak level (0.0 to 1.0) using WASAPI IAudioMeterInformation."""
        if self._meter is not None:
            try:
                val = float(self._meter.GetPeakValue())
                self._last_peak = max(0.0, min(1.0, val))
                return self._last_peak
            except Exception:
                pass
        return 0.0

    def compute_wave_bars(self, active: bool, bar_count: int = 7) -> list[float]:
        """Generate smooth reactive equalizer bar levels [0.0..1.0]."""
        peak = self.get_peak()
        if not active and peak < 0.01:
            return [0.06] * bar_count

        t = time.monotonic() * 3.6
        levels: list[float] = []
        for i in range(bar_count):
            # Harmonic dual-sine wave matching Panacea's physical wave formula
            v = 0.45 + 0.34 * math.sin(t + i * 0.85) + 0.18 * math.sin(t * 1.7 + i * 1.9)
            if peak > 0.01:
                v = v * 0.35 + peak * 0.65
            levels.append(max(0.08, min(1.0, round(v, 3))))
        return levels
