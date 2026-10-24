# EkPill — a Windows shell that is one capsule

A port of the **experience** of [Panacea](https://github.com/EnsixD/Panacea) to
Windows: no bar, no tray, no scattered popups — the whole shell is a single pill
docked to a screen edge that morphs into whatever you asked for and flows back
when you are done. It hugs the edge with two concave corners, like a hardware
notch.

One look only: **Nothing** — black capsule, white dots, and red held in reserve
for a dying battery.

![collapsed](ekpill_selftest.png)

## Why it is a rewrite, not a copy

Panacea is not an app; it is a Linux desktop environment. Its shell is QML run by
**Quickshell**, which only exists on Wayland, and every panel is wired to a Linux
service — PipeWire, NetworkManager/iwd, BlueZ, power-profiles-daemon, MPRIS,
D-Bus notifications, PAM. None of that exists on Windows, so the *experience* is
reimplemented on **Qt 6 / QML** (the same toolkit family Panacea uses), with the
Windows equivalents underneath.

| Panacea panel | Panacea backend | EkPill backend | Status |
|---|---|---|---|
| EkPill capsule, morph, notch corners | Quickshell (Wayland) | Qt 6 QML + Win32 layered window | ✅ ported |
| Dot-matrix Nothing clock | QML `DotText` | same code, ported | ✅ ported |
| Now playing: title, artist, art, transport, seek | MPRIS | `GlobalSystemMediaTransportControlsSessionManager` | ✅ live |
| Volume + mute | PipeWire | WASAPI via `pycaw` | ✅ live |
| Battery + charging | UPower | `GetSystemPowerStatus` | ✅ live |
| Wi-Fi SSID + signal & inline scanner | NetworkManager / iwd | Async `netsh wlan show networks` | ✅ live |
| Bluetooth radio + paired devices (honest state) | BlueZ | WinRT `Radio` + WinRT paired-device query; the registry key is only a candidate list. Windows has no supported "connect this paired device" call for desktop apps, so each row shows the state Windows reports and opens Windows' own Bluetooth page to connect. | ✅ live |
| Launcher (Start Menu instant search) | custom | Start Menu walk (calculator excluded per spec) | ✅ live |
| Power menu (lock/sleep/sign-out/restart/shut down) | Hyprland | `LockWorkStation` / `SetSuspendState` / `shutdown.exe` | ✅ live |
| Do-not-disturb / Focus | D-Bus notification daemon | `FocusSessionManager` read live; Windows' own switch is opened to change it (the WinRT start/end calls are package-gated) | ✅ live |
| Notification mirroring | D-Bus notification daemon | **Deliberately not implemented**: EkPill is a control surface, not a second Action Center. Windows keeps its own notifications. | 🚫 excluded |
| Placement survives restarts (edge, pinned, open page, auto-hide, hotkeys) | session restore | `%LOCALAPPDATA%\EkPill\settings.json`, written atomically from the QML change handlers | ✅ live |
| Settings page: DND indicator, auto-hide, dock-edge picker, autostart toggle, hotkey rebinding | control centre | QML page in the same capsule, through the same bridge slots; DND mirrors Windows' focus session and opens Windows to change it (the WinRT start/end calls are package-gated) | ✅ live |
| Audio Mixer: per-application volume sliders, mute toggles & reactive WASAPI wave visualizer | PipeWire | WASAPI `IAudioSessionManager2` & `IAudioMeterInformation` via `pycaw`; only apps with a real session are drawn, and only active output endpoints are listed | ✅ live |
| Screen Recorder: 30/60 FPS, destination picker, microphone toggle | wf-recorder / PipeWire | bundled ffmpeg (Desktop Duplication via `ddagrab`, `gdigrab` fallback), Matroska capture remuxed to a standard faststart MP4 on stop, dshow microphones | ✅ live |
| Files: bookmarks, every drive, three sort orders, rename / copy / cut / paste, Recycle Bin delete | custom | `os.scandir`, `shutil`, `SHFileOperationW` with `FOF_ALLOWUNDO` | ✅ live |
| Media viewer | custom | **Removed**: every file opens in whatever Windows has registered, exactly like Explorer | 🚫 excluded |
| Auto-hide when quiet | Quickshell fade | QML timer bound to the idle state; the invisible capsule still catches the pointer | ✅ live |
| Global hotkeys: Ctrl+Alt+L launcher, user-rebindable; an optional close key | Quickshell keybinds | Win32 `RegisterHotKey` through Qt's native event filter | ✅ live |
| Excluded features (analog clock, weather forecast, AI quota, lockscreen, virtual desktops, calculator, clipboard history, password vault, wallpaper engine) | — | Excluded per explicit design requirements | 🚫 excluded |

## Controls — where every control lives

Nothing is in a second window or a hidden corner: it is all in the capsule.

**Opening and closing.** Point at the capsule and it always opens quick
settings — never a page that locks the rest of EkPill away — and flows back
when the pointer leaves. The player is one tap from the now-playing strip. A click on the bare capsule **pins** it open; a pinned capsule stays
until you take it down, and while pinned it shows a **✕** in the panel's
top-right corner: one close control, in the same corner, on every page. There
are four ways out of an open page: that **✕**, a click on the bare padding
around the page, **Esc**, and the optional **close hotkey** — a combination you
bind yourself in Settings, which puts EkPill away from whatever app has the
keyboard (unlike Esc, which only acts while the pointer is on EkPill).
(Click the collapsed capsule again to release the pin.) Right-click the tray
icon for **Move to next edge** and **Quit EkPill** — there is no taskbar button
on purpose.

**Esc belongs to the app you are in.** EkPill is an overlay that never
takes the keyboard, so Escape is only *noticed*, never swallowed: EkPill
watches the key with a keyboard hook that hands it straight on, and only acts
while the pointer is on it. Anywhere else it reaches the app you are typing
in untouched. A page that is using the keyboard gets first refusal: a rename
in progress is cancelled, a hotkey capture is abandoned, and only the next Esc
takes EkPill down.

| Panel | Opens from | What is on it |
|---|---|---|
| Collapsed capsule | — | weekday, dot-matrix clock, battery %, Wi-Fi glyph, and a recording dot; click anywhere to pin it open. Docked right it is a slim upright strip with the same information stacked. |
| Quick settings | hover the capsule | now-playing strip (art, title, elapsed/total; tap → player), volume slider + mute, inline Wi-Fi & Bluetooth scanners, **Focus** (Windows DND), Files, Mixer, Record, battery line, search → launcher, **gear → Settings**, power → power menu |
| Player | the now-playing strip in quick settings | art, title/artist, draggable seek bar, position/duration, prev / play / next |
| Audio Mixer | quick settings' Mixer tile | per-application audio session volume sliders & mute toggles, reactive WASAPI loopback wave bars |
| Screen Recorder | quick settings' Record tile | 30/60 FPS selector, destination folder launcher, microphone toggle |
| Files | quick settings | folder chips, drives with free space, breadcrumb, sort by name/date/size; a folder descends, a file opens in its Windows app; access-denied folders are dimmed and inert; right click (or the hovering ⋯) → Open / Rename / Copy / Cut / Recycle; **New folder**, **Paste** / **Move here** |
| Launcher | quick settings' search glyph, `Ctrl+Alt+L` | type to search every Start Menu app with instant filtering; ↑↓ chooses, Enter opens, Esc closes |
| Power | quick settings' power glyph | Lock, Sleep, Sign out, Restart, Shut — EkPill closes **before** Lock/Sleep |
| Settings | quick settings' **gear** | a compact icon switchboard: Focus (tapping opens Windows), auto-hide, start with Windows, **Dock edge: Top / Side**, hotkey rebinding |

**Dock edge — top / right — has three controls:** *Settings → Dock edge* (a
direct pick), the tray's *Move to next edge* (toggles the two), and
`python main.py --pos=right` for a single run. Whichever you use is written
to `settings.json` and comes back after a restart.

**Global hotkeys:** `Ctrl+Alt+L` → launcher, rebindable in Settings.
Notifications no longer have a hotkey because EkPill no longer shows
notifications. A combination Windows already owns is refused with
the old one kept. The third one is **Close**, which starts with *no
combination* — click it, press the keys, and that combination collapses the
EkPill from anywhere; press **Delete** during the same capture to unbind it
again. It is the only hotkey that may be empty: the launcher always has to be
summonable.

## Run it

```bash
pip install -r requirements.txt
python main.py
```

Or take the artifacts: `dist\EkPill\EkPill.exe` (one-folder build, no Python
needed) and `dist\EkPillSetup.exe` (per-user installer, no admin prompt, and
no pages to click through). Both are built and verified by:

```bash
python build_packaged.py      # assets -> PyInstaller -> Inno Setup, in order
```

The installer is **per-user**: no admin prompt, and it lands in
`%LocalAppData%\Programs\EkPill`. Launching it is the whole interaction — no
welcome, folder, tasks or confirmation page, and the one page Inno insists on
showing installs itself. Installing writes that folder, a desktop shortcut, a
Start Menu shortcut, a Startup shortcut (the app is a shell; it starts with
Windows) and an uninstall entry under `HKCU`. Uninstalling takes all of it
away, the whole `{app}` folder included, so nothing the app wrote there keeps
the directory alive. Uninstall also removes `%LOCALAPPDATA%\EkPill` (settings
and caches), both shortcuts and the Start-menu group; the installed tree is
the only space it uses. The
`--selftest` screenshots therefore go to the **working directory**, not next to
the exe: from the repo that is the same folder as always, and from an installed
copy it keeps the run out of `_internal`.

What uninstall deliberately keeps is your data: `%LOCALAPPDATA%\EkPill`
(`settings.json` and the thumbnail cache) survives,
so reinstalling comes back to your edge, switches and hotkeys. Delete that
folder to start clean.

### The art, once

`../app_art_assets/` is the single source for every image the app ships: the
tray icon, the exe icon, the installer icon, the preview's browser tab and the
hero art. `build_assets.py` copies the 32px tray icon and regenerates
`build/ekpill.ico` as a **real** multi-size icon (16/24/32/48/64/128/256 — the
shipped favicon is a single 256px frame, which renders blurry in the task
manager and Alt-Tab). The script reads the ico's own directory back to verify
all seven frames are embedded, because PIL's idea of what it wrote is not the
ground truth Windows reads.

The hero art is also saved to `assets/sample.jpg` at 1920×1080 as sample media
for the file viewer.

Right-click the tray icon: **Move to next edge** rotates the dock edge (and is
what the saved placement remembers), **Quit EkPill** stops it. (It deliberately
does not show a taskbar button, so the tray is the way out.)

### Headless checks

```bash
python main.py --selftest                    # render the collapsed EkPill to a PNG
python main.py --selftest --pos=right        # dock to an edge: top|right
python main.py --selftest --page=quick       # render a page: quick|media|launcher|power|files|settings|audio|record
python main.py --selftest --page=files --browse=C:/  # open Files on a specific folder
python main.py --selftest --page=files --menu  # ...with the row menu photographed

python main.py --test-persist               # plant a placement, boot, assert it round-trips to disk
python main.py --test-hotkeys               # press Ctrl+Alt+L at input level, assert the page opens
python main.py --test-tray                  # trigger the tray's QAction, assert the edge moves and persists
python main.py --test-settings              # seed DND/auto-hide, boot, flip both, assert the file
python main.py --test-autohide              # idle -> hidden, pointer -> revealed, disabled -> stays visible
python main.py --test-autostart              # write the real Startup shortcut, read it back, remove it
python main.py --test-rebind                 # rebind a hotkey, press it, conflict refused, rollback keeps old
python main.py --test-screens                # 6 screen-selection rules, pure logic, no window
python main.py --test-hotplug                # fake screens drive the real wiring: re-dock, fallback, mode change
python main.py --test-files                  # listing, sorts, kinds, and a Recycle Bin delete + undelete
python main.py --test-files-ui               # the bridge QML calls: browse, sort, activate, rename, copy, paste, trash
python main.py --test-fileops                # rename rules, collision names, recursive copy, move-never-overwrites
python main.py --test-close                  # every page opens pinned and collapses through its own ✕
python main.py --test-closekey               # bind the close key, press it, unbind it, press it again
python main.py --test-escape                 # Esc closes the page when the pointer is on EkPill, and is left alone when it is not

python verify.py                             # ALL of the above in order, stop at first failure
python verify.py --full                      # ...plus PyInstaller, the packaged selftest and the installer

# NB: RegisterHotKey is exclusive per combination — stop the live EkPill first,
# or the hotkey test cannot register and will say so plainly.
python main.py --probe                       # verify click-through + hover-expand
python build_preview.py                      # crop every shot to its alpha and rebuild preview.html
```

`--selftest` writes `ekpill_selftest*.png` into the working directory (plus a
`.json` sidecar holding the capsule's real rectangle), parks the pointer away
from every edge so the capture is deterministic, and prints the QML loader
status, the page's implicit size and
the live media/focus state — a page that fails to load is reported instead of
silently rendering blank. The capture waits 3.8s before grabbing: the media
service's first poll lands around 2s and can re-trigger the capsule's width
animation, and an earlier grab photographs the pill mid-morph. `--probe` drives the real window and asserts three things:

```
pointer away       -> click_through=True   hot=(633, 0, 270, 40)   # collapsed
pointer over       -> click_through=False  hot=(596, 0, 348, 234)  # it opened
pointer away again -> click_through=True   hot=(629, 0, 270, 40)   # and closed
```

The middle line is the whole morph, measured: the interactive region grew from
the ≈288×40 capsule to the 348×369 quick-settings panel under real pointer input,
and shrank back. (The capsule is wider than it was before notifications landed:
the unread badge is part of it.) The two `away` lines differ by a few pixels
because they are sampled at the tail of the 340ms collapse animation; a settled
capture puts the capsule at exactly x=622, 288 wide on this machine. That 288 is
not a constant to quote forever — the capsule's length is content-driven (badge +
digit counts), so treat these numbers as *the pattern*, and re-measure after
layout changes. The two pointer-driven tests re-pin the cursor just before
sampling: they run on a live desktop, and an unrelated nudge mid-wait used to
read exactly like a click-through regression.

### Verified by measurement

`python verify.py` runs the whole source suite in order and stops at the first
red. Current result on this machine: **32/32 steps pass** (12 rendered states,
the hover/click-through probe, and 19 behaviour tests), plus a packaged-exe
render and a fresh installer compile in `--full`.

| What | How | Result |
|---|---|---|
| Two edges | QML-reported rect | top `(590, 0, 356, 372)` open / `(647, 0, 242, 40)` collapsed; right `(1180, 246, 356, 372)` open / `(1482, 366, 54, 132)` collapsed; each touches its edge and is centred on the other axis |
| Right edge is upright | rendered grab | the opened panel is 356×372 with every label horizontal — no rotation transform |
| Hover opens quick settings | live source + `--selftest --hover` | `activePage='quick'` even while Spotify is playing; player is one tap away |
| Media metadata | live Spotify via SMTC | art, title, artist, elapsed/total and a ticking seek bar (`Dil Hilde` 0:03 / 4:34); next/previous change track, toggle pauses |
| Stale media cleared | close Spotify, poll | state goes `active=False, title=''` within one poll — no old labels under a dead session |
| Notification mirroring | code + UI | service not started, page/toast/badge/deleted from the shell; DND still reads Windows |
| Files access | `C:\` listing | `PerfLogs` comes back `locked=True`, drawn at 42% opacity with no pointer cursor and no menu; no red error |
| Settings | `--page=settings` | 300×263, six icon rows (Focus, auto-hide, autostart, dock, two hotkeys) |
| Hover first time | `--test-hover` | 7 checks, including close-away and close-under-pointer |
| Installer | silent install → uninstall | install exit 0, desktop + Start-menu shortcuts created; uninstall removes `{app}`, `%LOCALAPPDATA%\EkPill`, both shortcuts and the group — no leftovers |
| Screen recorder | `--test-recorder` | 30/60 only, Matroska→faststart MP4, full ffmpeg decode with zero errors |
| Mixer / Bluetooth | live backends | one active output endpoint, real app sessions; two genuinely paired Bluetooth devices, honest connected state |

## How it works

```
main.py                 Qt app, full-screen transparent overlay, tray, selftest/probe
build_preview.py        crops each grab to its alpha, asserts it covers the reported rect
preview.html            every rendered state, generated — not hand-edited
backend/
  win32_overlay.py      WS_EX_LAYERED/TOOLWINDOW/NOACTIVATE, DWM square corners,
                        and the WS_EX_TRANSPARENT click-through toggle
  bridge.py             the one QObject QML talks to: properties, slots, polling
  system.py             battery (GetSystemPowerStatus), volume (pycaw)
  media.py              SMTC now-playing + transport + album art, on its own asyncio loop
  files.py              listing/sorts/kinds, drives, and Recycle Bin delete — no Qt
  asyncloop.py          the single shared asyncio loop for WinRT coroutine calls
  shell.py              Wi-Fi, Bluetooth, launcher, calculator, power actions
  autostart.py           the Startup-folder shortcut as the single source of truth for autostart
  persist.py            saved placement and switches in one atomic JSON file
  hotkeys.py            global hotkeys: parse/format, RegisterHotKey -> Qt native event filter -> QML
  escape.py             the Escape watcher: a keyboard hook that never takes the key,
                        with the keyboard's state as a fallback
verify.py                the one-command suite: assets, selftests, probe, every behaviour test
qml/
  EkPill.qml            the capsule: dock, morph, 4 edges, concave corners, live toast
  DotText.qml           Nothing dot-matrix digits
  NotchCorner.qml       the concave fillet (Shape.CurveRenderer), GPU vector anti-aliased
  Glyph.qml / EqBars.qml / SliderBar.qml
  pages/                QuickSettings, MediaPage, LauncherPage, PowerPage,
                        NotificationsPage, FilesPage, ViewerPage, SettingsPage,
                        AudioView, RecordView
  Theme.js              the one palette
```

### The window: transparent, always on top, and click-through where it should be

The overlay is one full-screen frameless window with `WS_EX_LAYERED` (per-pixel
alpha), `WS_EX_TOOLWINDOW` (no Alt-Tab, no taskbar) and `WS_EX_NOACTIVATE` (never
steals focus). QML reports EkPill's rectangle to the host 60 times a second;
the host watches the pointer and sets `WS_EX_TRANSPARENT` whenever the pointer is
away from that rectangle, so clicks fall through to the desktop and every other
window. Hovering the capsule makes it accept input again and expand. `WS_EX_NOACTIVATE`
is dropped only while the launcher needs the keyboard.

### Two edges, both upright

The top edge is a horizontal capsule. The right edge is a slim vertical strip
that opens into a full **upright** panel docked to the screen edge — the same
quick-settings layout, not a rotated copy, so every label is read normally.

Only these two survive: the left and bottom docks were removed, and a saved
`"pos": "left"`/`"bottom"` is normalised to `top` on load. The tray's *Move to
next edge* toggles top ↔ right, and Settings has the same two choices.

### Focus, not a second Action Center

Notification mirroring was removed by request. The WinRT listener, the list
page, the unread badge and the transient card are all gone; nothing polls
Action Center and EkPill cannot show a stale notification.

Do-not-disturb stayed, because it is a *state*, not a copy of the notification
list. `FocusSessionManager.get_session()` is read every 1.5s and
`backend.notifDnd` mirrors it, so the switch cannot disagree with Windows.
There is deliberately no setter: `try_start_focus_session()` and
`try_end_focus_session()` raise `Feature ... is not available` for an
unpackaged app, and the old private boolean is exactly what made EkPill
show "on" while Windows showed "off". Tapping Focus opens the page that owns
the switch.

### Placement survives the restart, and hotkeys reach EkPill

Placement, the two switches, and the hotkeys are the whole persisted surface,
written from the QML change handlers into `%LOCALAPPDATA%\EkPill\settings.json`
(temp-file + rename). Restore is deliberately **not** applied to
`--selftest`/`--probe` runs: a saved edge must never leak into a measured shot.
Applying placement fires three handlers, so restore suppresses writes and saves
once at the end — otherwise a crash between two of them would file a
half-applied state. The handlers themselves **merge** (`persist.update`) rather
than rewrite a full state.

Global hotkeys come from Win32 `RegisterHotKey`, dispatched through Qt's native
-event filter against a hidden native window: **Ctrl+Alt+L** opens the launcher, and the optional **Close** key collapses
whatever is open. If another process already owns a combination, Windows
refuses the registration and the failed names are printed rather than
swallowed. `close` is the one name whose default *is* empty, so it has no
fallback to retire to: a combination Windows refuses simply leaves it unbound
and says so, and `hotkeys.rebind(name, "")` is the unbind path the settings
capture's Delete key uses.

Both have real end-to-end checks: `--test-persist` plants `left/True/power`,
boots, asserts the QML came up there, changes the edge and asserts the file
recorded it; `--test-hotkeys` presses the actual combinations at input level
(`keybd_event`) and asserts the pages opened; `--test-tray` triggers the tray's
own QAction and asserts the edge moved and was written to disk; `--test-settings`
flips the auto-hide switch and reads it back off disk, and asserts that
`notifDnd` equals the real Windows focus state instead of the seeded value;
`--test-autohide` waits out the quiet spell and watches the capsule retire,
return and stay. The tray action exists because persistence without a control
would store an edge only the selftest could ever set.

Measured runs (`--selftest`, `--probe`) **suppress** persistence writes
outright: the placement hooks fire whenever those runs move EkPill, so an
unsuppressed run would quietly rewrite the user's saved state while taking
screenshots — which is exactly what happened until it was caught.

### The settings page and auto-hide

The switches that used to be hard-wired now have a page: do-not-disturb (a
read-only mirror of Windows' switch), auto-hide, a **direct** dock-edge picker
(the tray only cycles), the
**autostart toggle**, and the **hotkey rebinding** capture. Everything routes
through the same bridge slots and QML properties, so the saved state stays one
file.

**Autostart** is owned by the app, not its installer: `backend/autostart.py`
reads and writes a `.lnk` in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`
— the shortcut *is* the state, so the toggle can never drift from what Windows
will actually do. `--test-autostart` proves the round trip against the real
Startup folder and restores it byte-for-byte.

**Hotkeys rebind from the page**: click a combo, the capsule takes keyboard
input, the next press becomes the binding — persisted, parsed by
`hotkeys.parse`, and re-registered live. If Windows already owns that
combination, the old one stays active and the refusal is shown, never swallowed
(`--test-rebind` exercises accept → press → conflict → rollback). The Close row
reads **no combination** until you give it one, and Delete during its capture
unbinds it again — the empty binding is a state the page can show, not a
missing value (`--test-closekey` drives both halves).

Auto-hide is deliberately declarative: the quiet timer is `running:`-bound to
the idle state rather than restarted by hand, because EkPill that *starts*
collapsed has had no transition to arm a timer on — the first version hid
exactly never until the `--test-autohide` run proved it. The capsule keeps its
geometry while invisible, which is what lets the pointer find it again: the
hot region follows the layout, not the opacity.

### Screens: one decision, unit-tested

`pick_screen(screens, primary, cursor)` decides which display EkPill docks
to: the screen under the pointer, nearest if the pointer is off-screen, primary
on ties and empties. It duck-types on `geometry()`/`contains()`, so
`--test-screens` exercises all six rules without a second monitor plugged in.

`--test-hotplug` goes one layer up: the *wiring* (`wire_display`, the exact
function production connects to Qt's screenAdded/screenRemoved/geometryChanged)
driven by fake screens and fake signals — seven re-dock rules, including the
one that caught a real gap while it was being written: a display **adopted by
hotplug** now gets its own `geometryChanged` watch, so a resolution change on
it re-applies coverage too (before, only the boot screen was watched).

### Files and the viewer

A file manager inside a 520px capsule cannot be a second Explorer, so the page
is the things a shell is actually for: **the folders you use** (seven
bookmarks, every drive with its free space), **one list** (three sort orders,
sizes, folders first), and **the verbs** (open, rename, copy, cut, paste,
recycle). Dot-named and hidden entries stay out on purpose — a home folder is
full of `.cargo`, `.git` and tool caches, and this is a 520px capsule, not a
debug view. A click descends into a folder or hands a file to the app Windows registered —
there is no in-app viewer any more. Folders this user cannot open are probed
once (`os.scandir`), returned as `locked`, and drawn dimmed and inert, so a
click cannot produce an access-denied screen. A right click (or the ⋯ on a
hovered row) opens the five verbs.

Rename is inline, in the row where the breadcrumb lives: Enter commits, Escape
returns the keyboard, and the capsule's own focus-hold is what makes the
text field usable without a dialog. The name goes through the rules Windows
enforces — no `<>:"/\|?*`, no trailing spaces or dots, no reserved device names
(`CON`, `COM1`), no overwrite — and a refusal is shown in the footer, never
swallowed. Copy and Cut arm one item in memory (never the system clipboard),
and Paste renames on collision the way Explorer does: `report (2).txt`.
Moving a folder into itself is refused, and a move never overwrites. The verbs
are `shutil` rather than `IFileOperation`: one process, no COM marshalling, and
the whole rule set is testable — the trade is that a very large tree runs on
the UI thread: no Explorer progress dialog, no cancel, and the capsule waits
while it copies. There is also
no drag-and-drop and no multi-select yet; one item at a time is the honest
scope of a 520px list.

Deleting is `SHFileOperationW` with `FOF_ALLOWUNDO`, not `os.remove` — the row's
✕ puts the file in the **Recycle Bin**, where Explorer can restore it. A drive
root is refused outright. `--test-files` proves the listing and the recycle
round-trip without a window, including the part that matters: it recycles a
uniquely named probe, sees the bin's count rise, finds the entry in
`Namespace(10)`, invokes Explorer's own `undelete` verb, and checks the file is
back and the count is where it started. `--test-fileops` covers the verb rules
in a temporary tree, and `--test-files-ui` drives the exact bridge the QML
calls — browse, sort, activate, rename, copy, paste, new folder, trash — so
the click behaviour is not only inferred from a screenshot.

There is no image or text viewer: every file is opened by its Windows
handler, exactly like a double-click in Explorer. That removes a whole page,
its Qt Multimedia dependency surface, and the image-decoder edge cases.

### One way out of every page

Opening a page **pins** EkPill — deliberately, so a list cannot collapse
under the pointer while it is being read. The release used to be a click on the
bare capsule *underneath* the page, and page content covers that: inside any list,
there was no visible way back at all — the report that led here. There is now one
**✕** in `EkPill.qml`, in the panel's top-right corner: above every page's
padding, inside the expanded corner's fillet, shown only while pinned, and in
the same corner on every page, so no header had to make room for it (Settings'
own duplicate ✕ was removed). The way *in* to Settings had the same gap:
nothing opened it — the only gear on quick settings launched *Windows'*
settings — so the dock-edge picker, the switches and the hotkey capture were
reachable only from a command line. The quick-settings footer now carries a
gear of its own, and the power menu closes EkPill **before** it locks or
sleeps rather than after. `--test-close` opens all pages and closes each one
with a real mouse event through the window's own delivery path, then re-checks
the old bare-edge click.

### Three bugs worth remembering

1. The two `NotchCorner`s started life as children of the capsule, so their
   absolute screen coordinates got the capsule's offset added a second time and
   one landed at the far-right screen edge. They are now root-level siblings,
   rendered with GPU-accelerated vector curve rendering (`Shape.CurveRenderer`).
2. A second "measuring" `Loader` at root rendered a duplicate of the page at the
   window origin. There is now one Loader, inside the capsule, and the capsule
   follows the page's `implicitWidth`/`implicitHeight`.
3. Moving EkPill rewrote `settings.json` from the five fields the placement
   hook had, silently resetting the saved hotkeys and settings to defaults. The
   fix is structural — the handler merges now.

## Licence

MIT, matching the upstream project. The dot-matrix digit set, the concave-corner
geometry and the Nothing palette are ported from Panacea (MIT).
