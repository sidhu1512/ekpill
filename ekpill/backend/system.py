"""Battery and system-volume backends for EkPill.

Both read live OS state rather than a placeholder:

* battery  -> Win32 ``GetSystemPowerStatus``
* volume   -> Core Audio endpoint volume through ``pycaw`` (optional import)
"""

from __future__ import annotations

import ctypes
import sys

IS_WINDOWS = sys.platform == "win32"


# --------------------------------------------------------------------- battery
class _SystemPowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_byte),
        ("BatteryFlag", ctypes.c_byte),
        ("BatteryLifePercent", ctypes.c_byte),
        ("SystemStatusFlag", ctypes.c_byte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


def read_battery() -> tuple[int, bool, bool]:
    """Return (percent, charging, present)."""
    if not IS_WINDOWS:
        return (100, True, False)
    status = _SystemPowerStatus()
    ok = ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status))
    if not ok:
        return (100, True, False)
    present = status.BatteryFlag != 128  # 128 == no system battery
    pct = status.BatteryLifePercent
    if pct in (255, -1):  # unknown
        pct = 100
    charging = status.ACLineStatus == 1
    return (int(pct), bool(charging), bool(present))


# ---------------------------------------------------------------------- volume
class VolumeService:
    """Master output volume and mute via the Windows Core Audio API."""

    def __init__(self) -> None:
        self.available = False
        self._endpoint = None
        if not IS_WINDOWS:
            return
        try:
            from pycaw.pycaw import AudioUtilities  # type: ignore

            speakers = AudioUtilities.GetSpeakers()
            # pycaw >= 2024 exposes the endpoint directly; older builds wrapped
            # an interface pointer we still have to Activate().
            endpoint = getattr(speakers, "EndpointVolume", None)
            if endpoint is None:
                from ctypes import POINTER, cast

                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import IAudioEndpointVolume

                interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                endpoint = cast(interface, POINTER(IAudioEndpointVolume))
            self._endpoint = endpoint
            self.available = True
        except Exception:
            self.available = False

    def get(self) -> tuple[float, bool]:
        if not self.available or self._endpoint is None:
            return (0.5, False)
        scalar = self._endpoint.GetMasterVolumeLevelScalar()
        return (float(scalar), bool(self._endpoint.GetMute()))

    def set(self, value: float) -> None:
        if not self.available or self._endpoint is None:
            return
        value = max(0.0, min(1.0, float(value)))
        self._endpoint.SetMasterVolumeLevelScalar(value, None)

    def set_mute(self, muted: bool) -> None:
        if not self.available or self._endpoint is None:
            return
        self._endpoint.SetMute(bool(muted), None)
