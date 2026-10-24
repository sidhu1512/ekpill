"""Now-playing backend built on the Windows System Media Transport Controls.

Every media app that integrates with Windows (Spotify, browsers, VLC, the
Movies app, ...) publishes a *session*. `GlobalSystemMediaTransportControls
SessionManager` lets us read the current session's title, artist, album art and
position, and send play/pause/next/previous/seek requests.

The WinRT projection is async, so a dedicated asyncio loop lives on a worker
thread. One detail matters more than the rest: on some Windows builds
`RequestAsync()` does not complete until a media session exists, and awaiting
the operation directly parks the loop forever. Every WinRT operation here is
therefore created once, then its `status` is *polled* with a deadline, so a
missing session can never freeze the panel — it simply reports "nothing
playing" until a player shows up, then the next request resolves.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time

from .asyncloop import AsyncLoop  # shared off-thread asyncio runner

IS_WINDOWS = sys.platform == "win32"

try:  # pragma: no cover - platform dependent
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as SessionManager,
    )

    HAVE_WINRT = True
except Exception:  # pragma: no cover
    SessionManager = None  # type: ignore
    HAVE_WINRT = False


VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3

# GlobalSystemMediaTransportControlsSessionPlaybackStatus
STATUS_CLOSED = 0
STATUS_OPENED = 1
STATUS_CHANGING = 2
STATUS_STOPPED = 3
STATUS_PLAYING = 4
STATUS_PAUSED = 5

# How long one WinRT operation may stay pending before we abandon it. The
# operations themselves are cheap; the wait is only ever bounded by this.
OP_TIMEOUT = 1.6
# A RequestAsync that sees no media session can stay pending for minutes on
# Windows 11. Re-issue it periodically instead of trusting it forever.
REQUEST_RETRY = 6.0


def _send_vk_media(vk: int) -> None:
    """Synthesize hardware media keys so playback commands always work."""
    if IS_WINDOWS:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            sc = user32.MapVirtualKeyW(vk, 0)
            user32.keybd_event(vk, sc, 0x0001, 0)
            user32.keybd_event(vk, sc, 0x0001 | 0x0002, 0)
        except Exception:
            pass


def _fmt_time(seconds: float) -> str:
    if not seconds or seconds < 0:
        return "0:00"
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def _is_process_running(pattern: str) -> bool:
    """Check if any running process matches pattern (case-insensitive substring) via Win32 snapshot."""
    if not IS_WINDOWS:
        return True
    try:
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x00000002
        kernel32 = ctypes.windll.kernel32

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        hSnap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if hSnap == -1:
            return True
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        pat = pattern.lower().removesuffix(".exe")
        found = False
        try:
            if kernel32.Process32FirstW(hSnap, ctypes.byref(entry)):
                while True:
                    name = entry.szExeFile.lower()
                    if pat in name:
                        found = True
                        break
                    if not kernel32.Process32NextW(hSnap, ctypes.byref(entry)):
                        break
        finally:
            kernel32.CloseHandle(hSnap)
        return found
    except Exception:
        return True


class MediaService:
    """Polls the active media session and reports it through a callback."""

    def __init__(self, on_update) -> None:
        self.on_update = on_update
        self.available = HAVE_WINRT and IS_WINDOWS
        self.error: str = ""
        self._manager = None
        self._request_retry_at: float = 0.0
        self._props_key: str = ""
        self._props: dict = {}
        self._props_at: float = 0.0
        # Many apps (Chrome among them) report a timeline position that does
        # not advance between updates. Anchor it and add elapsed time locally
        # so the clock actually ticks.
        self._pos_base: float = 0.0
        self._pos_at: float = 0.0
        self._art_cache: dict[str, str] = {}
        self._temp_art_files: set[str] = set()
        self._last: dict = {}
        self._empty_since: float = 0.0
        self._purge_stale_art()
        self._loop = AsyncLoop()
        if self.available:
            self._loop.run(self._poll())

    @staticmethod
    def _purge_stale_art() -> None:
        """Clean up orphaned ekpill_art_*.img files from previous runs."""
        try:
            tdir = tempfile.gettempdir()
            for fname in os.listdir(tdir):
                if fname.startswith("ekpill_art_") and fname.endswith((".img", ".png")):
                    try:
                        os.remove(os.path.join(tdir, fname))
                    except Exception:
                        pass
        except Exception:
            pass


    @staticmethod
    def _is_session_alive(session) -> bool:
        if session is None:
            return False
        try:
            info = session.get_playback_info()
            if info is None:
                return False
            status = int(info.playback_status)
            if status == STATUS_CLOSED:
                return False
        except Exception:
            return False

        source = ""
        try:
            source = str(getattr(session, "source_app_user_model_id", "") or "").lower()
        except Exception:
            pass

        if not source:
            return True

        target = ""
        if ".exe" in source:
            target = source.split(".exe")[0].split("\\")[-1].split("/")[-1]
        elif "spotify" in source:
            target = "spotify"
        elif "chrome" in source:
            target = "chrome"
        elif "msedge" in source:
            target = "msedge"
        elif "vlc" in source:
            target = "vlc"
        elif "brave" in source:
            target = "brave"
        elif "firefox" in source:
            target = "firefox"
        elif "itunes" in source:
            target = "itunes"

        if target:
            if not _is_process_running(target):
                return False
        return True

    # ------------------------------------------------------------------ poll
    async def _poll(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception as exc:
                self.error = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(0.6)

    async def _ensure_manager(self) -> None:
        now = time.monotonic()
        if self._manager is not None:
            return
        if now < self._request_retry_at:
            return
        try:
            self._manager = await asyncio.wait_for(SessionManager.request_async(), timeout=2.5)
            self.error = ""
            def _on_changed(sender, args):
                self._props_at = 0.0
            try:
                self._manager.add_current_session_changed(_on_changed)
                self._manager.add_sessions_changed(_on_changed)
            except Exception:
                pass
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self._manager = None
            self._request_retry_at = now + REQUEST_RETRY

    async def _tick(self) -> None:
        await self._ensure_manager()
        if self._manager is None:
            self._push_empty()
            return

        session = self._session()
        if session is None or not self._is_session_alive(session):
            self._push_empty()
            return

        info = None
        try:
            info = session.get_playback_info()
        except Exception:
            info = None
        status = int(info.playback_status) if info is not None else STATUS_CLOSED
        playing = status == STATUS_PLAYING

        # Closed/Stopped or non-running session: clean up immediately
        if status in (STATUS_CLOSED, STATUS_STOPPED) and not playing:
            self._push_empty()
            return

        props = await self._props_for(session)
        title = str(props.get("title") or "")
        artist = str(props.get("artist") or "")
        if not title and not artist:
            self._push_empty()
            return

        timeline = None
        try:
            timeline = session.get_timeline_properties()
        except Exception:
            timeline = None

        reported = 0.0
        duration = 0.0
        if timeline is not None:
            try:
                reported = float(timeline.position.total_seconds())
                duration = float(timeline.end_time.total_seconds())
            except Exception:
                pass

        now = time.monotonic()
        if not playing:
            self._pos_base = reported
            self._pos_at = now
        elif (self._pos_at == 0.0
              or abs(reported - self._pos_base) > 0.75
              or (duration and reported >= duration - 0.5)):
            # A seek, a track change, or a fresh report: re-anchor.
            self._pos_base = reported
            self._pos_at = now
        position = self._pos_base + (now - self._pos_at) if playing else reported
        if duration > 0:
            position = min(position, duration)

        state = {
            "active": True,
            "title": title,
            "artist": artist,
            "playing": playing,
            "position": position,
            "positionText": _fmt_time(position),
            "duration": duration,
            "durationText": _fmt_time(duration),
            "art": str(props.get("art") or ""),
            "source": getattr(session, "source_app_user_model_id", "") or "",
        }
        # Only push when something that matters changed, to avoid re-emitting
        # a signal every second and re-running QML bindings.
        if self._significant(state) != self._significant(self._last):
            self._last = state
            self.on_update(state)

    def _push_empty(self) -> None:
        self._props = {}
        self._props_key = ""
        self._props_at = 0.0
        self._pos_base = 0.0
        self._pos_at = 0.0
        state = {"active": False, "title": "", "artist": "", "playing": False,
                 "position": 0.0, "positionText": "0:00", "duration": 0.0,
                 "durationText": "0:00", "art": "", "source": ""}
        if self._last.get("active") is not False:
            self._last = state
            self.on_update(state)

    async def _props_for(self, session) -> dict:
        """Media properties for the current session, fetched off the hot path."""
        key = ""
        try:
            key = str(session.source_app_user_model_id or "")
        except Exception:
            pass
        now = time.monotonic()
        if key == self._props_key and self._props.get("title") and now - self._props_at < 0.7:
            return self._props

        try:
            props = await asyncio.wait_for(session.try_get_media_properties_async(), timeout=3.0)
            if props:
                new_title = str(props.title or "")
                new_artist = str(props.artist or "")
                new_album = str(props.album_title or "")
                if new_title or new_artist:
                    self._props["title"] = new_title
                    self._props["artist"] = new_artist
                    self._props["album"] = new_album
                    self._props_key = key
                    self._props_at = time.monotonic()
                    try:
                        art_path = await self._art_for(props)
                        if art_path:
                            self._props["art"] = art_path
                    except Exception:
                        pass
                    return self._props
                elif key == self._props_key and self._props.get("title"):
                    return self._props
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            if key == self._props_key and self._props.get("title"):
                return self._props
        return self._props

    @staticmethod
    def _significant(state: dict) -> tuple:
        return (
            state.get("active"),
            state.get("title"),
            state.get("artist"),
            state.get("playing"),
            state.get("art"),
            state.get("durationText"),
            int(state.get("position", 0.0)),
        )

    # -------------------------------------------------------------- artwork
    async def _art_for(self, props) -> str:
        """Copy the session thumbnail into a temp PNG once and reuse the path."""
        title = props.title or ""
        artist = props.artist or ""
        album = props.album_title or ""
        key = f"{title}|{artist}|{album}"
        if key in self._art_cache:
            return self._art_cache[key]
        if not hasattr(props, "thumbnail") or props.thumbnail is None:
            self._art_cache[key] = ""
            return ""
        try:
            path = await self._read_thumbnail(props.thumbnail)
        except Exception:
            path = ""
        self._art_cache[key] = path
        return path

    async def _read_thumbnail(self, ref) -> str:
        from winrt.windows.storage.streams import DataReader

        try:
            stream = await asyncio.wait_for(ref.open_read_async(), timeout=1.8)
            if not stream:
                return ""
            size = int(stream.size)
            if size <= 0:
                return ""
            reader = DataReader(stream)
            await asyncio.wait_for(reader.load_async(size), timeout=1.8)
            data = bytes(reader.read_buffer(size))
            reader.close()
            stream.close()
            if not data:
                return ""
            fd, path = tempfile.mkstemp(prefix="ekpill_art_", suffix=".png")
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            if len(self._temp_art_files) >= 5:
                for stale in list(self._temp_art_files)[:-3]:
                    try:
                        if os.path.isfile(stale):
                            os.remove(stale)
                        self._temp_art_files.discard(stale)
                    except Exception:
                        pass
            self._temp_art_files.add(path)
            return path
        except Exception:
            return ""

    def cleanup(self) -> None:
        """Unlink any temp album art files on shutdown."""
        for f in list(self._temp_art_files):
            try:
                if os.path.isfile(f):
                    os.remove(f)
            except Exception:
                pass
        self._temp_art_files.clear()
        self._art_cache.clear()

    # ------------------------------------------------------------- controls
    def _session(self):
        if self._manager is None:
            return None
        cur = None
        try:
            cur = self._manager.get_current_session()
            if not self._is_session_alive(cur):
                cur = None
        except Exception:
            cur = None
            self._manager = None
            return None
        playing = None
        paused = None
        try:
            for s in list(self._manager.get_sessions()):
                try:
                    if not self._is_session_alive(s):
                        continue
                    info = s.get_playback_info()
                    if info:
                        st = int(info.playback_status)
                        if st == STATUS_PLAYING and playing is None:
                            playing = s
                        elif st == STATUS_PAUSED and paused is None:
                            paused = s
                except Exception:
                    pass
        except Exception:
            self._manager = None
            return None
        return playing or cur or paused

    async def _command_op(self, op) -> bool:
        try:
            done = await asyncio.wait_for(op, timeout=1.2)
            return bool(done)
        except Exception:
            return False

    def command(self, name: str) -> None:
        async def _do():
            handled = False
            session = self._session()
            if session is None:
                await self._ensure_manager()
                session = self._session()

            if session is not None:
                try:
                    if name == "toggle":
                        info = session.get_playback_info()
                        playing = (info is not None
                                   and int(info.playback_status) == STATUS_PLAYING)
                        op = (session.try_pause_async() if playing
                              else session.try_play_async())
                    elif name == "next":
                        op = session.try_skip_next_async()
                    elif name == "prev":
                        op = session.try_skip_previous_async()
                    else:
                        op = None
                    if op is not None:
                        handled = await self._command_op(op)
                except Exception:
                    handled = False

            if not handled:
                if name == "toggle":
                    _send_vk_media(VK_MEDIA_PLAY_PAUSE)
                elif name == "next":
                    _send_vk_media(VK_MEDIA_NEXT_TRACK)
                elif name == "prev":
                    _send_vk_media(VK_MEDIA_PREV_TRACK)
            # Pull a fresh snapshot right away instead of waiting for the next
            # poll: a skip changes the track, and the panel showed the old one
            # for up to a second.
            self._props_at = 0.0
            await asyncio.sleep(0.35)
            await self._tick()

        self._loop.run(_do())

    def seek(self, seconds: float) -> None:
        session = self._session()
        if session is None:
            return

        async def _do():
            try:
                ticks = int(max(0.0, seconds) * 10_000_000)
                op = session.try_change_playback_position_async(ticks)
                await self._command_op(op)
            except Exception:
                pass

        self._loop.run(_do())
