"""Windows shell services: Wi-Fi, Bluetooth, focus mode, launcher, power.

* Wi-Fi      -> ``netsh wlan show interfaces`` (SSID + signal, no admin needed)
                plus inline scan, profile management, and connect/disconnect.
                A connect is only reported as succeeded once Windows actually
                says it is connected; netsh's exit code alone lies.
* Bluetooth  -> WinRT paired-device enumeration. The registry key everyone
                reaches for first keeps dead bonds forever, which is why a
                fresh machine can look like it has three paired devices.
* focus      -> reads the real Windows Do Not Disturb profile out of the
                CloudStore settings blob (no unsupported writes).
* launcher   -> walks the Start Menu for .lnk entries and shells them open
* calculator -> excluded per user requirement
* power      -> lock / sleep / sign out / restart / shut down
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import tempfile
import time
import winreg

IS_WINDOWS = sys.platform == "win32"

try:  # pragma: no cover
    from winrt.windows.devices.radios import Radio, RadioKind, RadioState

    HAVE_RADIOS = True
except Exception:  # pragma: no cover
    HAVE_RADIOS = False


# ----------------------------------------------------------------------- wifi
_SSID_RE = re.compile(r"^\s*SSID\s*:\s*(.+?)\s*$", re.MULTILINE)
_STATE_RE = re.compile(r"^\s*State\s*:\s*(.+?)\s*$", re.MULTILINE)
_SIGNAL_RE = re.compile(r"^\s*Signal\s*:\s*(\d+)%", re.MULTILINE)
_NAME_RE = re.compile(r"^\s*Name\s*:\s*(.+?)\s*$", re.MULTILINE)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def read_wifi() -> dict:
    """Return {'connected': bool, 'ssid': str, 'signal': int, 'iface': str}.

    ``netsh`` prints one block per adapter. Parsing the whole output with the
    first match meant a second, idle adapter could make a connected machine
    look disconnected (or the reverse). Each block is now judged on its own,
    and a connected one wins.
    """
    empty = {"connected": False, "ssid": "", "signal": 0, "iface": ""}
    if not IS_WINDOWS:
        return empty
    try:
        out = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True, timeout=4,
            creationflags=_NO_WINDOW,
        ).stdout
    except Exception:
        return empty

    blocks: list[list[str]] = []
    for block in re.split(r"\r?\n\s*\r?\n", out):
        if _STATE_RE.search(block):
            blocks.append(block.splitlines())
    if not blocks:
        return empty

    def parse(lines: list[str]) -> dict:
        text = "\n".join(lines)
        state = _STATE_RE.search(text)
        ssid = _SSID_RE.search(text)
        signal = _SIGNAL_RE.search(text)
        name = _NAME_RE.search(text)
        return {
            "connected": bool(state and state.group(1).strip().lower() == "connected"),
            "ssid": (ssid.group(1).strip() if ssid else ""),
            "signal": int(signal.group(1)) if signal else 0,
            "iface": (name.group(1).strip() if name else ""),
        }

    parsed = [parse(b) for b in blocks]
    for info in parsed:
        if info["connected"]:
            return info
    return parsed[0]


def _known_profiles() -> set[str]:
    """Return set of known Wi-Fi profile SSIDs."""
    if not IS_WINDOWS:
        return set()
    try:
        out = subprocess.run(
            ["netsh", "wlan", "show", "profiles"],
            capture_output=True, text=True, timeout=4,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
        return set(re.findall(r"All User Profile\s*:\s*(.+)$", out, re.MULTILINE))
    except Exception:
        return set()


def scan_wifi_networks() -> list[dict]:
    """Scan and return list of visible Wi-Fi networks."""
    if not IS_WINDOWS:
        return []
    current_info = read_wifi()
    cur_ssid = current_info.get("ssid", "")
    is_connected = current_info.get("connected", False)
    profiles = _known_profiles()

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run(
            ["netsh", "wlan", "show", "networks", "mode=bssid"],
            capture_output=True, text=True, timeout=6,
            creationflags=flags,
        ).stdout
    except Exception:
        return []

    networks: list[dict] = []
    current: dict | None = None
    for line in out.splitlines():
        line = line.strip()
        m_ssid = re.match(r"^SSID \d+\s*:\s*(.*)$", line)
        if m_ssid:
            if current and current.get("ssid"):
                networks.append(current)
            ssid = m_ssid.group(1).strip()
            current = {
                "ssid": ssid,
                "security": "Open",
                "signal": 0,
                "known": ssid in profiles,
                "connected": is_connected and (ssid == cur_ssid),
            }
        elif current:
            m_auth = re.match(r"^Authentication\s*:\s*(.+)$", line)
            if m_auth:
                current["security"] = m_auth.group(1).strip()
            m_sig = re.match(r"^Signal\s*:\s*(\d+)%", line)
            if m_sig:
                sig = int(m_sig.group(1))
                if sig > current["signal"]:
                    current["signal"] = sig
    if current and current.get("ssid"):
        networks.append(current)

    # Hidden networks show up as an empty SSID; they cannot be picked from a
    # list and would draw as a blank row.
    networks = [n for n in networks if n["ssid"]]
    # Sort: connected first, then known networks, then by signal strength descending
    networks.sort(key=lambda n: (not n["connected"], not n["known"], -n["signal"]))
    return networks


def connect_wifi(ssid: str, password: str = "") -> tuple[bool, str]:
    """Connect to a Wi-Fi network, generating a temporary profile if needed."""
    if not IS_WINDOWS:
        return False, "Not Windows"

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    ssid = ssid.strip()
    if not ssid:
        return False, "SSID cannot be empty"

    profiles = _known_profiles()
    if ssid in profiles:
        # A saved profile already knows the key; adding a second, hand-built
        # one would overwrite it with whatever was typed in EkPill.
        _run_netsh(["wlan", "connect", f"name={ssid}", f"ssid={ssid}"], flags)
        return _await_wifi(ssid)

    if not password:
        # Open network.
        pass

    import xml.sax.saxutils as xml_escape

    # Create profile XML. `enc` used to be missing here, so every attempt to
    # join a *new* network died with NameError before netsh ever ran.
    auth = "WPA2PSK" if password else "open"
    enc = "AES" if password else "none"
    xml_entities = {'"': "&quot;", "'": "&apos;"}
    esc_ssid = xml_escape.escape(ssid, entities=xml_entities)
    esc_password = xml_escape.escape(password, entities=xml_entities) if password else ""
    key_block = (
        f"<sharedKey><keyType>passPhrase</keyType><protected>false</protected>"
        f"<keyMaterial>{esc_password}</keyMaterial></sharedKey>"
        if password else ""
    )
    xml_content = (
        '<?xml version="1.0"?>\n'
        '<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">\n'
        f"    <name>{esc_ssid}</name>\n"
        "    <SSIDConfig>\n"
        "        <SSID>\n"
        f"            <name>{esc_ssid}</name>\n"
        "        </SSID>\n"
        "    </SSIDConfig>\n"
        "    <connectionType>ESS</connectionType>\n"
        "    <connectionMode>auto</connectionMode>\n"
        "    <MSM>\n"
        "        <security>\n"
        "            <authEncryption>\n"
        f"                <authentication>{auth}</authentication>\n"
        f"                <encryption>{enc}</encryption>\n"
        "                <useOneX>false</useOneX>\n"
        "            </authEncryption>\n"
        f"            {key_block}\n"
        "        </security>\n"
        "    </MSM>\n"
        "</WLANProfile>"
    )

    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as fh:
        fh.write(xml_content)
        tmp_path = fh.name

    try:
        add_res = subprocess.run(
            ["netsh", "wlan", "add", "profile", f"filename={tmp_path}", "user=current"],
            capture_output=True, text=True, timeout=8, creationflags=flags,
        )
        if add_res.returncode != 0:
            return False, _clean_netsh(add_res.stdout or add_res.stderr)

        _run_netsh(["wlan", "connect", f"name={ssid}", f"ssid={ssid}"], flags)
        ok, err = _await_wifi(ssid)
        if not ok:
            # Do not leave a profile with a rejected password behind: Windows
            # would keep offering it, and the next attempt would skip the
            # password prompt because the profile now "exists".
            _run_netsh(["wlan", "delete", "profile", f"name={ssid}"], flags)
        return ok, err
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


def _run_netsh(args: list[str], flags: int) -> tuple[int, str]:
    try:
        res = subprocess.run(["netsh"] + args, capture_output=True, text=True,
                             timeout=10, creationflags=flags)
        return res.returncode, (res.stdout or res.stderr or "")
    except Exception as exc:
        return 1, str(exc)


def _await_wifi(ssid: str, timeout: float = 12.0) -> tuple[bool, str]:
    """Wait for Windows to actually report the connection.

    ``netsh wlan connect`` returns 0 as soon as the request is queued, even
    for a wrong password. Trusting that exit code is what made EkPill
    announce a connection that never happened.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        info = read_wifi()
        if info.get("connected") and info.get("ssid") == ssid:
            return True, ""
        time.sleep(0.5)
    return False, f"Windows did not connect to {ssid} (wrong password or out of range)"


def _clean_netsh(text: str) -> str:
    """netsh prints a blank line before its message; drop the noise."""
    return " ".join(line.strip() for line in text.splitlines() if line.strip())


def disconnect_wifi() -> bool:
    """Disconnect from current Wi-Fi network and confirm it took effect."""
    if not IS_WINDOWS:
        return False
    _run_netsh(["wlan", "disconnect"], _NO_WINDOW)
    for _ in range(10):
        if not read_wifi().get("connected"):
            return True
        time.sleep(0.3)
    return False


def forget_wifi(ssid: str) -> bool:
    """Delete a saved Wi-Fi profile."""
    if not IS_WINDOWS:
        return False
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        res = subprocess.run(["netsh", "wlan", "delete", "profile", f"name={ssid}"],
                             capture_output=True, timeout=5, creationflags=flags)
        return res.returncode == 0
    except Exception:
        return False


# ------------------------------------------------------------------ bluetooth
# Bonds live here even after a device is removed from Settings on some
# machines, so this key is a *candidate list*, never a source of truth. Every
# entry is checked against the live Bluetooth API before it is shown.
_BOND_KEY = r"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices"


def _bond_candidates() -> list[tuple[int, str]]:
    """(address, registry name) for every remembered device."""
    if not IS_WINDOWS:
        return []
    out: list[tuple[int, str]] = []
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _BOND_KEY)
    except OSError:
        return out
    try:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(key, i)
            except OSError:
                break
            i += 1
            try:
                addr = int(sub, 16)
            except ValueError:
                continue
            name = ""
            try:
                sk = winreg.OpenKey(key, sub)
                try:
                    raw, _ = winreg.QueryValueEx(sk, "Name")
                    if isinstance(raw, bytes):
                        name = raw.decode("utf-8", "ignore").rstrip("\x00")
                    elif isinstance(raw, str):
                        name = raw.strip()
                finally:
                    winreg.CloseKey(sk)
            except OSError:
                pass
            out.append((addr, name))
    finally:
        winreg.CloseKey(key)
    return out


async def _probe_bond(address: int) -> dict | None:
    """Ask Windows whether this address is paired, and whether it is linked."""
    try:
        from winrt.windows.devices.bluetooth import (
            BluetoothConnectionStatus, BluetoothDevice,
        )
    except Exception:
        return None
    try:
        device = await BluetoothDevice.from_bluetooth_address_async(address)
    except Exception:
        return None
    if device is None:
        return None
    try:
        info = device.device_information
        if not bool(info.pairing.is_paired):
            # A stale bond: Windows remembers the key but the device is not
            # paired. Showing it is exactly the "three paired, none real" bug.
            return None
        connected = device.connection_status == BluetoothConnectionStatus.CONNECTED
        # class_of_device is a projected struct, not an int.
        cod = getattr(device, "class_of_device", None)
        raw = int(getattr(cod, "raw_value", 0) or 0)
        major = (raw >> 8) & 0x1F
        name = device.name or ""
        looks_audio = any(word in name.lower() for word in (
            "buds", "headphone", "headset", "speaker", "sound", "audio",
            "airpods", "earbud", "ult", "field", "wh-", "wf-",
        ))
        return {
            "name": name,
            "connected": bool(connected),
            "audio": major == 0x04 or looks_audio,
        }
    finally:
        try:
            device.close()
        except Exception:
            pass


async def list_bluetooth_devices_async() -> list[dict]:
    """Paired Bluetooth devices, with the connection state Windows reports."""
    if not IS_WINDOWS:
        return []
    candidates = _bond_candidates()
    probes = await asyncio.gather(
        *(_probe_bond(addr) for addr, _name in candidates), return_exceptions=True)
    devices: list[dict] = []
    for (addr, reg_name), probe in zip(candidates, probes):
        if not isinstance(probe, dict):
            continue
        mac_raw = f"{addr:012x}"
        mac = ":".join(mac_raw[i:i + 2] for i in range(0, 12, 2)).upper()
        name = probe["name"] or reg_name or "Bluetooth device"
        # A device with no name and no link is registry debris; hiding it is
        # better than drawing a row nobody can identify.
        if not probe["name"] and not reg_name and not probe["connected"]:
            continue
        devices.append({
            "id": mac_raw,
            "name": name,
            "mac": mac,
            "connected": probe["connected"],
            "paired": True,
            "type": "audio" if probe["audio"] else "device",
        })
    devices.sort(key=lambda d: (not d["connected"], d["name"].lower()))
    return devices


def list_bluetooth_devices() -> list[dict]:
    """Synchronous convenience wrapper (scripts, tests)."""
    try:
        return asyncio.run(list_bluetooth_devices_async())
    except Exception:
        return []


async def unpair_bluetooth(mac: str) -> bool:
    """Forget a device for real, through Windows' pairing API."""
    if not IS_WINDOWS:
        return False
    try:
        address = int(str(mac).replace(":", "").lower(), 16)
    except ValueError:
        return False
    try:
        from winrt.windows.devices.bluetooth import BluetoothDevice
        device = await BluetoothDevice.from_bluetooth_address_async(address)
        if device is not None:
            result = await device.device_information.pairing.unpair_async()
            # 0 == Unpaired (DeviceUnpairingResultStatus).
            if int(result.status) == 0:
                return True
    except Exception:
        pass
    # Win32 fallback, documented for desktop apps.
    try:
        import ctypes
        bthprops = ctypes.WinDLL("bthprops.cpl", use_last_error=True)
        addr = ctypes.c_ulonglong(address)
        bthprops.BluetoothRemoveDevice.argtypes = [ctypes.POINTER(ctypes.c_ulonglong)]
        bthprops.BluetoothRemoveDevice.restype = ctypes.c_ulong
        return int(bthprops.BluetoothRemoveDevice(ctypes.byref(addr))) == 0
    except Exception:
        return False


class BluetoothService:
    """Reports whether the Bluetooth radio is on and how many devices are paired."""

    def __init__(self, loop, on_update) -> None:
        self.loop = loop
        self.on_update = on_update
        self.available = HAVE_RADIOS and IS_WINDOWS
        self._last = None
        if self.available:
            self.loop.run(self._poll())

    async def _poll(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception:
                pass
            await asyncio.sleep(5.0)

    async def _tick(self) -> None:
        radios = await Radio.get_radios_async()
        state = {"available": True, "on": False, "count": 0}
        for radio in radios:
            if radio.kind == RadioKind.BLUETOOTH:
                state["on"] = int(radio.state) == 1
        if state["on"]:
            # Count what Windows calls paired, not what the registry remembers.
            state["count"] = len(await list_bluetooth_devices_async())

        if state != self._last:
            self._last = state
            self.on_update(state)

    async def set_radio_state(self, on: bool) -> bool:
        """Turn Bluetooth radio On or Off."""
        if not HAVE_RADIOS:
            return False
        try:
            radios = await Radio.get_radios_async()
            for radio in radios:
                if radio.kind == RadioKind.BLUETOOTH:
                    target_state = RadioState.ON if on else RadioState.OFF
                    await radio.set_state_async(target_state)
                    await self._tick()
                    return True
        except Exception:
            pass
        return False


# ----------------------------------------------------------------- focus mode
_FOCUS_KEY = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\CloudStore\Store\Cache"
              r"\DefaultAccount\$$windows.data.notifications.quiethourssettings\Current")


def _focus_session_active() -> bool | None:
    """Ask the shell's own focus session object (read-only is enough).

    This is the value the Quick Settings tile draws, and it is available to
    unpackaged apps for reading. `try_start_focus_session` is not — it raises
    "feature not available" — so EkPill can mirror the switch but not
    move it. Returning None means "this Windows build refused the query".
    """
    if not IS_WINDOWS:
        return None
    try:
        from winrt.windows.ui.shell import FocusSessionManager

        return bool(FocusSessionManager.get_default().is_focus_active)
    except Exception:
        return None


def read_focus_mode() -> bool:
    """True when Windows' Do Not Disturb is actually on.

    EkPill used to keep this as its own little boolean, so the switch and
    Windows disagreed the moment either side moved. The focus session object
    is authoritative; the CloudStore blob is the fallback for builds where
    that object is unavailable. It holds the selected quiet-hours profile by
    name; "Unrestricted" is off and every other profile is on.
    """
    if not IS_WINDOWS:
        return False

    active = _focus_session_active()
    if active is not None:
        return active

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _FOCUS_KEY) as key:
            data, _typ = winreg.QueryValueEx(key, "Data")
    except OSError:
        return False
    if not isinstance(data, (bytes, bytearray)):
        return False
    text = bytes(data).decode("utf-16-le", "ignore")
    match = re.search(r"QuietHoursProfile\.([A-Za-z]+)", text)
    if not match:
        return False
    return match.group(1).lower() != "unrestricted"


def open_focus_settings() -> None:
    """Windows owns this switch; take the user to the place that owns it."""
    if not IS_WINDOWS:
        return
    try:
        subprocess.Popen(["cmd", "/c", "start", "ms-settings:notifications"],
                         creationflags=_NO_WINDOW)
    except Exception:
        pass


# -------------------------------------------------------------------- launcher
def _start_menu_dirs() -> list[str]:
    dirs = []
    for base in (
        os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                     r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ.get("APPDATA", ""),
                     r"Microsoft\Windows\Start Menu\Programs"),
    ):
        if base and os.path.isdir(base):
            dirs.append(base)
    return dirs


def list_apps() -> list[dict]:
    """Every Start Menu .lnk, de-duplicated by display name."""
    seen: dict[str, dict] = {}
    for root_dir in _start_menu_dirs():
        for root, _dirs, files in os.walk(root_dir):
            for fn in files:
                if not fn.lower().endswith(".lnk"):
                    continue
                name = os.path.splitext(fn)[0]
                if name.lower().startswith(("uninstall", "деинстал")):
                    continue
                key = name.lower()
                if key not in seen:
                    seen[key] = {"name": name, "path": os.path.join(root, fn)}
    return sorted(seen.values(), key=lambda a: a["name"].lower())


def launch(path: str) -> bool:
    try:
        os.startfile(path)  # type: ignore[attr-defined]
        return True
    except Exception:
        return False


# ------------------------------------------------------------------ calculator
def calculate(expr: str) -> str:
    """Calculator functionality excluded per user requirement."""
    return ""


# ------------------------------------------------------------------ power menu
def power_action(name: str) -> None:
    if os.environ.get("EKPILL_PREVENT_POWER_ACTIONS") == "1":
        print(f"[PowerAction Protected] Skipped executing '{name}'")
        return
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        if name == "lock":
            import ctypes

            ctypes.windll.user32.LockWorkStation()
        elif name == "sleep":
            import ctypes

            ctypes.windll.powrprof.SetSuspendState(False, False, False)
        elif name == "signout":
            subprocess.Popen(["shutdown", "/l"], creationflags=flags)
        elif name == "restart":
            subprocess.Popen(["shutdown", "/r", "/t", "0"], creationflags=flags)
        elif name == "shutdown":
            subprocess.Popen(["shutdown", "/s", "/t", "0"], creationflags=flags)
    except Exception:
        pass
