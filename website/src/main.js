import { SITE } from "./config.js";

const $ = (selector, parent = document) => parent.querySelector(selector);
const $$ = (selector, parent = document) => [...parent.querySelectorAll(selector)];
const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const currentAppTheme = "dark";

// ==========================================================================
// 1. CONFIG & METADATA BINDINGS
// ==========================================================================
$$("[data-version]").forEach((el) => (el.textContent = SITE.version));
$$("[data-size]").forEach((el) => (el.textContent = SITE.installerSize));
$$("[data-year]").forEach((el) => (el.textContent = String(new Date().getFullYear())));
if (SITE.sha256) $$("[data-sha]").forEach((el) => (el.textContent = SITE.sha256));

const bindLink = (attr, url) => {
  $$(`[${attr}]`).forEach((linkEl) => {
    if (url) {
      linkEl.href = url;
      linkEl.removeAttribute("aria-disabled");
    }
  });
};

bindLink("data-download", SITE.downloadUrl);
bindLink("data-releases", SITE.releasesPageUrl);
bindLink("data-source", SITE.repoUrl);
bindLink("data-support", `${SITE.repoUrl}/issues`);

// Toast Notification
export function showToast(message) {
  let toastEl = $(".site-toast");
  if (!toastEl) {
    toastEl = document.createElement("div");
    toastEl.className = "site-toast";
    document.body.appendChild(toastEl);
  }
  toastEl.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg><span>${message}</span>`;
  toastEl.classList.add("active");
  clearTimeout(toastEl._timer);
  toastEl._timer = setTimeout(() => toastEl.classList.remove("active"), 2600);
}

// Subtle Mechanical Keyboard Audio Click (Web Audio API)
let audioCtx = null;
function playKeyClick() {
  if (prefersReducedMotion) return;
  try {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === "suspended") {
      audioCtx.resume();
    }
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(650, audioCtx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(110, audioCtx.currentTime + 0.038);
    gain.gain.setValueAtTime(0.04, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.038);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + 0.04);
  } catch (_) {}
}

// ==========================================================================
// 2. FLOATING NAVBAR, MOBILE DRAWER & SCROLL REVEAL OBSERVER
// ==========================================================================
const navbar = $("#navbar");
const mobileToggle = $("#mobile-toggle");
const mobileDrawer = $("#mobile-drawer");

window.addEventListener(
  "scroll",
  () => {
    if (navbar) {
      navbar.classList.toggle("scrolled", window.scrollY > 20);
    }
  },
  { passive: true }
);

mobileToggle?.addEventListener("click", () => {
  const isOpen = mobileDrawer.classList.toggle("open");
  mobileToggle.setAttribute("aria-expanded", String(isOpen));
  mobileToggle.classList.toggle("open", isOpen);
});

$$("#mobile-drawer a").forEach((link) => {
  link.addEventListener("click", () => {
    mobileDrawer.classList.remove("open");
    mobileToggle.setAttribute("aria-expanded", "false");
    mobileToggle.classList.remove("open");
  });
});

// Scroll Reveal Observer
if ("IntersectionObserver" in window) {
  const revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("revealed");
          revealObserver.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.08 }
  );
  $$(".reveal-item").forEach((el) => {
    if (prefersReducedMotion) el.classList.add("revealed");
    else revealObserver.observe(el);
  });
} else {
  $$(".reveal-item").forEach((el) => el.classList.add("revealed"));
}

// Click on mini bubble triggers shortcut preview
const heroBubble = $("#hero-bubble");
heroBubble?.addEventListener("click", () => {
  selectShortcut("ctrl-alt-l");
  playKeyClick();
  showToast("Top-Edge Capsule clicked — expanding Quick Settings");
});

// ==========================================================================
// 3. ACETERNITY SPOTLIGHT CARDS DYNAMIC CURSOR
// ==========================================================================
$$(".spotlight-card").forEach((card) => {
  card.addEventListener("mousemove", (e) => {
    const rect = card.getBoundingClientRect();
    card.style.setProperty("--mouse-x", `${e.clientX - rect.left}px`);
    card.style.setProperty("--mouse-y", `${e.clientY - rect.top}px`);
  });
});

// ==========================================================================
// 4. BENTO GRID INTERACTIVE WIDGETS
// ==========================================================================

// --- Widget 1: Live Capsule State & Geometry Tokenizer
const nlpInput = $("#nlp-input");
const nlpClearBtn = $("#nlp-clear-btn");
const nlpChips = $("#nlp-chips");

function parseCapsuleCommand(text) {
  const chips = [];
  if (!text || !text.trim()) return chips;
  const lower = text.toLowerCase();

  if (lower.includes("edge:right") || lower.includes("right") || lower.includes("vertical")) {
    chips.push({ type: "date", label: "Edge: Right (68×198 Upright)" });
  } else {
    chips.push({ type: "date", label: "Edge: Top (354×50 Notch)" });
  }

  if (lower.includes("page:quick") || lower.includes("quick")) {
    chips.push({ type: "duration", label: "Panel: QuickSettings (426×213)" });
  } else if (lower.includes("page:settings") || lower.includes("setting")) {
    chips.push({ type: "duration", label: "Panel: SettingsSwitchboard (314×328)" });
  } else if (lower.includes("page:power") || lower.includes("power")) {
    chips.push({ type: "duration", label: "Panel: PowerMenu (426×150)" });
  } else if (lower.includes("page:media") || lower.includes("media") || lower.includes("smtc")) {
    chips.push({ type: "duration", label: "Panel: SMTC Media Player (466×228)" });
  } else if (lower.includes("page:files") || lower.includes("file")) {
    chips.push({ type: "duration", label: "Panel: FilesHub (650×608)" });
  } else if (lower.includes("page:launcher") || lower.includes("launcher")) {
    chips.push({ type: "duration", label: "Panel: AppLauncher (588×525)" });
  } else if (lower.includes("page:collapsed") || lower.includes("collapsed")) {
    chips.push({ type: "duration", label: "State: Collapsed Capsule (354×50)" });
  }

  if (lower.includes("spring")) {
    chips.push({ type: "tag", label: "#spring:3.8/0.32" });
  }
  if (lower.includes("60hz") || lower.includes("hit")) {
    chips.push({ type: "tag", label: "#WS_EX_TRANSPARENT:60Hz" });
  }
  if (lower.includes("!pinned")) {
    chips.push({
      type: "priority",
      label: "Pinned (Esc to close)",
    });
  }

  return chips;
}

function renderNlpChips(chips) {
  if (!nlpChips) return;
  if (!chips.length) {
    nlpChips.innerHTML = `<span style="font-size:0.75rem;color:var(--text-muted);font-style:italic;">Type state tokens (edge:top, page:quick, !pinned)...</span>`;
    return;
  }
  nlpChips.innerHTML = chips
    .map((c) => `<span class="nlp-chip ${c.type}">${c.label}</span>`)
    .join("");
}

if (nlpInput) {
  renderNlpChips(parseCapsuleCommand(nlpInput.value));
  nlpInput.addEventListener("input", (e) => {
    renderNlpChips(parseCapsuleCommand(e.target.value));
  });
}

nlpClearBtn?.addEventListener("click", () => {
  if (nlpInput) {
    nlpInput.value = "";
    nlpInput.focus();
    renderNlpChips([]);
  }
});

$$(".nlp-preset-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const val = btn.dataset.preset;
    if (nlpInput) nlpInput.value = val;
    renderNlpChips(parseCapsuleCommand(val));
    showToast(`Loaded capsule preset: ${btn.textContent}`);
  });
});

// --- Widget 2: Settings Switchboard & Power Hub Simulator
const simEdgeTop = $("#sim-edge-top");
const simEdgeRight = $("#sim-edge-right");
const simSettingsLabel = $("#sim-settings-label");
const settingsStatusTag = $("#settings-status-tag");
const spotifyEq = $("#spotify-eq");

simEdgeTop?.addEventListener("click", () => {
  simEdgeTop.classList.add("primary");
  simEdgeRight?.classList.remove("primary");
  if (simSettingsLabel) simSettingsLabel.textContent = "Active Edge: Top Hardware Notch (354×50)";
  if (settingsStatusTag) settingsStatusTag.textContent = "Top Docked";
  spotifyEq?.classList.add("active");
  showToast("Dock edge switched to Top Notch (354×50 px)");
});

simEdgeRight?.addEventListener("click", () => {
  simEdgeRight.classList.add("primary");
  simEdgeTop?.classList.remove("primary");
  if (simSettingsLabel) simSettingsLabel.textContent = "Active Edge: Right Upright Dock (68×198)";
  if (settingsStatusTag) settingsStatusTag.textContent = "Right Docked";
  spotifyEq?.classList.add("active");
  showToast("Dock edge switched to Right Upright Dock (68×198 px)");
});

$("#sim-pwr-lock")?.addEventListener("click", () => showToast("Power Menu: LockWorkStation invoked"));
$("#sim-pwr-sleep")?.addEventListener("click", () => showToast("Power Menu: SetSuspendState (Sleep) confirmed"));
$("#sim-pwr-restart")?.addEventListener("click", () => showToast("Power Menu: Restart confirmed (two-step verified)"));
$("#sim-pwr-shutdown")?.addEventListener("click", () => showToast("Power Menu: Shut down confirmed (two-step verified)"));

// --- Widget 3: WinRT SMTC & WaveBars Simulator
const whisperMic = $("#whisper-mic");
const whisperWaveBars = $$("#whisper-wave i");
const whisperText = $("#whisper-text");
let isRecording = false;
let waveTimer = null;
let typeStreamTimer = null;

const demoVoicePhrases = [
  "SMTC Session: Midnight City — M83 (01:42 / 04:03) · High-DPI album art cached",
  "WinRT SMTC: GlobalSystemMediaTransportControlsSession active · WaveBars 60fps",
  "Media Studio: Transport state Playing · 4-bar equalizer synchronized",
  "Quick Settings: Master volume 85% · WinRT SMTC session active",
];

whisperMic?.addEventListener("click", () => {
  if (isRecording) {
    clearInterval(waveTimer);
    clearInterval(typeStreamTimer);
    isRecording = false;
    whisperMic.classList.remove("recording");
    whisperWaveBars.forEach((b) => (b.style.height = "6px"));
    showToast("WaveBars equalizer paused");
  } else {
    isRecording = true;
    whisperMic.classList.add("recording");
    showToast("Polling WinRT SMTC media session...");

    waveTimer = setInterval(() => {
      whisperWaveBars.forEach((bar) => {
        bar.style.height = `${4 + Math.random() * 18}px`;
      });
    }, 120);

    const phrase = demoVoicePhrases[Math.floor(Math.random() * demoVoicePhrases.length)];
    if (whisperText) whisperText.textContent = '"';
    let charIdx = 0;

    typeStreamTimer = setInterval(() => {
      if (charIdx < phrase.length) {
        if (whisperText) whisperText.textContent += phrase[charIdx];
        charIdx++;
      } else {
        clearInterval(typeStreamTimer);
        clearInterval(waveTimer);
        isRecording = false;
        whisperMic.classList.remove("recording");
        whisperWaveBars.forEach((b) => (b.style.height = "6px"));
        if (whisperText) whisperText.textContent += '"';
        showToast("WinRT SMTC telemetry synchronized");
      }
    }, 35);
  }
});

// --- Widget 4: Wireless Radio Scan
$("#calendar-join-btn")?.addEventListener("click", () => {
  showToast("Scanned 5 WLAN networks & 4 Bluetooth devices via netsh/WinRT");
});

// --- Widget 5: Activity Matrix & Bento Tab Switcher
function buildHeatmap() {
  const container = $("#heatmap-grid");
  if (!container) return;

  const totalWeeks = 38;
  const daysPerWeek = 7;
  let html = "";
  const now = new Date();

  for (let w = 0; w < totalWeeks; w++) {
    html += '<div class="heatmap-col">';
    for (let d = 0; d < daysPerWeek; d++) {
      const daysAgo = (totalWeeks - 1 - w) * 7 + (6 - d);
      const cellDate = new Date(now.getTime() - daysAgo * 24 * 60 * 60 * 1000);
      const dateStr = cellDate.toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
      });

      let level = 0;
      const seed = (w * 7 + d * 13) % 100;
      if (w > totalWeeks - 8) {
        if (seed > 20) level = (seed % 4) + 1;
      } else if (w > totalWeeks - 20) {
        if (seed > 40) level = (seed % 3) + 1;
      } else {
        if (seed > 60) level = (seed % 2) + 1;
      }

      const opsCount = level === 0 ? 0 : level * 3 + (seed % 4);
      const tooltip = `${dateStr} · ${opsCount} capsule actions & file ops`;
      html += `<div class="heatmap-cell" data-level="${level}" title="${tooltip}"></div>`;
    }
    html += "</div>";
  }
  container.innerHTML = html;
}
buildHeatmap();

$$(".bento-tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".bento-tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const target = btn.dataset.bentoTab;

    $$(".bento-tab-content").forEach((c) => {
      c.classList.toggle("active", c.id === `tab-${target}`);
    });
  });
});

// ==========================================================================
// 5. ACETERNITY INTERACTIVE SCREEN RECORDING VIDEO PLAYER STUDIO
// ==========================================================================
const videoChapters = SITE.chapters.map((ch, idx) => ({
  name: ch.title,
  time: ch.duration,
  badge: ch.badge,
  heading: ch.heading,
  desc: ch.description,
  features: ch.bullets,
  webm: ch.webm,
  gif: ch.gif,
  label: ch.liveLabel,
  hotkey: `<kbd>${ch.hotkey}</kbd>`,
  actionPill: ch.title,
  cursorX: ["48%", "52%", "50%", "55%", "46%"][idx] || "50%",
  cursorY: ["38%", "32%", "46%", "44%", "35%"][idx] || "40%",
}));

const TOTAL_VIDEO_SECONDS = 30;
let currentVideoChapter = 0;
let videoCurrentSec = 0;
let videoPlaying = true;
let videoSpeed = 1.0;
let videoTimer = null;

const scrubberBar = $("#video-scrubber-bar");
const scrubberProgress = $("#video-scrubber-progress");
const scrubberHead = $("#video-scrubber-head");
const timeCur = $("#video-time-cur");
const videoPlayBtn = $("#video-play-btn");
const videoPlayIcon = $("#video-play-icon");
const videoPlayLabel = $("#video-play-label");
const videoSpeedBtn = $("#video-speed-btn");
const screencastCursor = $("#screencast-cursor");
const screencastRipple = $("#screencast-ripple");
const screencastHotkeyHud = $("#screencast-hotkey-hud");
const screencastActionPill = $("#screencast-action-pill");

function formatTime(sec) {
  const m = String(Math.floor(sec / 60)).padStart(2, "0");
  const s = String(Math.floor(sec % 60)).padStart(2, "0");
  return `${m}:${s}`;
}

function updateVideoTourStage(idx) {
  currentVideoChapter = idx;
  const data = videoChapters[idx];
  if (!data) return;

  const badge = $("#video-chapter-badge");
  const heading = $("#video-chapter-heading");
  const desc = $("#video-chapter-desc");
  const features = $("#video-chapter-features");
  const video = $("#video-screen-player");
  const img = $("#video-screen-img");
  const liveLabel = $("#video-live-label");

  if (badge) badge.textContent = data.badge;
  if (heading) heading.textContent = data.heading;
  if (desc) desc.innerHTML = data.desc;
  if (features) {
    features.innerHTML = data.features
      .map(
        (f) =>
          `<li><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg><span>${f}</span></li>`
      )
      .join("");
  }
  if (img) {
    img.setAttribute("data-src", data.gif);
  }
  if (video) {
    video.style.display = "block";
    if (img) img.style.display = "none";
    video.onerror = () => {
      video.style.display = "none";
      if (img) {
        img.style.display = "block";
        img.src = data.gif;
      }
    };
    const currentSrc = video.getAttribute("src") || "";
    if (!currentSrc.includes(data.webm.replace("./", ""))) {
      video.src = data.webm;
      video.playbackRate = videoSpeed;
      video.load();
      if (videoPlaying) {
        video.play().catch(() => {
          video.style.display = "none";
          if (img) {
            img.style.display = "block";
            img.src = data.gif;
          }
        });
      }
    }
  }
  if (img && video && video.style.display === "none") {
    img.alt = data.heading;
    img.src = data.gif;
  }
  if (liveLabel) liveLabel.textContent = data.label;

  if (screencastCursor) {
    screencastCursor.style.left = data.cursorX;
    screencastCursor.style.top = data.cursorY;
  }
  if (screencastRipple) {
    screencastRipple.classList.remove("pulse");
    void screencastRipple.offsetWidth;
    screencastRipple.classList.add("pulse");
  }
  if (screencastHotkeyHud) {
    screencastHotkeyHud.innerHTML = data.hotkey;
    screencastHotkeyHud.classList.add("visible");
    setTimeout(() => screencastHotkeyHud.classList.remove("visible"), 1800);
  }
  if (screencastActionPill) {
    screencastActionPill.innerHTML = `<span class="action-pill-dot"></span><span>${data.actionPill}</span>`;
  }

  $$(".video-chapter-tab").forEach((tab, i) => {
    const isActive = i === idx;
    tab.classList.toggle("active", isActive);
    tab.setAttribute("aria-selected", String(isActive));
  });
}

function updateTimelineUI() {
  const percent = (videoCurrentSec / TOTAL_VIDEO_SECONDS) * 100;
  if (scrubberProgress) scrubberProgress.style.width = `${percent}%`;
  if (scrubberHead) scrubberHead.style.left = `${percent}%`;
  if (timeCur) timeCur.textContent = formatTime(videoCurrentSec);

  const targetChapter = Math.min(
    Math.floor((videoCurrentSec / TOTAL_VIDEO_SECONDS) * videoChapters.length),
    videoChapters.length - 1
  );
  if (targetChapter !== currentVideoChapter) {
    updateVideoTourStage(targetChapter);
  }
}

function startVideoEngine() {
  if (prefersReducedMotion) return;
  clearInterval(videoTimer);
  videoTimer = setInterval(() => {
    if (!videoPlaying) return;
    videoCurrentSec += 0.25 * videoSpeed;
    if (videoCurrentSec >= TOTAL_VIDEO_SECONDS) {
      videoCurrentSec = 0;
    }
    updateTimelineUI();
  }, 250);
}

function seekToTime(sec) {
  videoCurrentSec = Math.max(0, Math.min(sec, TOTAL_VIDEO_SECONDS));
  updateTimelineUI();
}

scrubberBar?.addEventListener("click", (e) => {
  const rect = scrubberBar.getBoundingClientRect();
  const ratio = (e.clientX - rect.left) / rect.width;
  seekToTime(ratio * TOTAL_VIDEO_SECONDS);
});

$$(".video-chapter-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    const idx = parseInt(tab.dataset.chapter, 10);
    seekToTime(idx * 6);
    updateVideoTourStage(idx);
    videoPlaying = true;
    updateVideoControlsUI();
  });
});

function updateVideoControlsUI() {
  if (!videoPlayBtn) return;
  if (videoPlaying) {
    if (videoPlayIcon)
      videoPlayIcon.innerHTML =
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>';
    if (videoPlayLabel) videoPlayLabel.textContent = "Pause";
  } else {
    if (videoPlayIcon)
      videoPlayIcon.innerHTML =
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><polygon points="6 3 20 12 6 21 6 3"/></svg>';
    if (videoPlayLabel) videoPlayLabel.textContent = "Play";
  }
}

videoPlayBtn?.addEventListener("click", () => {
  videoPlaying = !videoPlaying;
  updateVideoControlsUI();
  const v = $("#video-screen-player");
  if (v) {
    if (videoPlaying) {
      v.play().catch(() => {});
    } else {
      v.pause();
    }
  }
  if (videoPlaying) startVideoEngine();
});

videoSpeedBtn?.addEventListener("click", () => {
  if (videoSpeed === 1.0) videoSpeed = 1.5;
  else if (videoSpeed === 1.5) videoSpeed = 2.0;
  else videoSpeed = 1.0;
  videoSpeedBtn.textContent = `${videoSpeed.toFixed(1)}x`;
  const v = $("#video-screen-player");
  if (v) v.playbackRate = videoSpeed;
  showToast(`Screencast speed: ${videoSpeed.toFixed(1)}x`);
});

$("#video-next-btn")?.addEventListener("click", () => {
  const next = (currentVideoChapter + 1) % videoChapters.length;
  seekToTime(next * 6);
  updateVideoTourStage(next);
});

$("#video-fullscreen-btn")?.addEventListener("click", () => {
  const box = $("#video-tour-box");
  if (!box) return;
  if (!document.fullscreenElement) {
    box.requestFullscreen?.().catch(() => {});
  } else {
    document.exitFullscreen?.().catch(() => {});
  }
});

updateVideoTourStage(0);

const tourBox = $("#video-tour-box");
if (tourBox && "IntersectionObserver" in window) {
  const tourObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          if (videoPlaying) {
            const v = $("#video-screen-player");
            v?.play().catch(() => {});
            startVideoEngine();
          }
        } else {
          clearInterval(videoTimer);
          const v = $("#video-screen-player");
          v?.pause();
        }
      });
    },
    { threshold: 0.15 }
  );
  tourObserver.observe(tourBox);
} else {
  startVideoEngine();
}

// ==========================================================================
// 6. 3D MECHANICAL KEYBOARD SHORTCUT STATION
// ==========================================================================
const shortcutConfig = {
  "ctrl-alt-l": {
    action: "Summon Instant App Launcher",
    latency: "< 6ms response",
    desc: "Triggers the Win32 RegisterHotKey listener from any application and focuses the Start Menu filter bar.",
    shot: "app-launcher",
    badge: "Ctrl + Alt + L",
  },
  escape: {
    action: "Collapse to Edge Capsule",
    latency: "< 4ms response",
    desc: "Unpins any active panel and springs back to the 332×50 top notch or 58×178 right vertical dock.",
    shot: "capsule-top",
    badge: "Escape",
  },
  "edge-hover": {
    action: "Expand Quick Settings Deck",
    latency: "16ms (60 Hz poll)",
    desc: "Hovering inside the collapsed capsule bounding box disables WS_EX_TRANSPARENT and expands Quick Settings.",
    shot: "quick-settings",
    badge: "Edge Hover",
  },
  "pill-click": {
    action: "Pin & Lock Active Panel",
    latency: "< 5ms response",
    desc: "Clicking the capsule pins the expanded utility open until you press Escape or click outside.",
    shot: "media-player",
    badge: "Pill Click",
  },
  "outside-click": {
    action: "Auto-Dismiss & Pass-Through",
    latency: "16ms (60 Hz poll)",
    desc: "Detects VK_LBUTTON clicks outside the live QML bounding box and collapses the active panel.",
    shot: "settings-switchboard",
    badge: "Outside Click",
  },
  "alt-e": {
    action: "Toggle Top / Right Edge Dock",
    latency: "< 8ms response",
    desc: "Switches between the Top Horizontal Notch (354×50) and the Right Upright Vertical Dock (68×198).",
    shot: "power-menu",
    badge: "Alt + E",
  },
};

function selectShortcut(key) {
  const info = shortcutConfig[key];
  if (!info) return;

  $$(".shortcut-row-card").forEach((card) => {
    card.classList.toggle("active", card.dataset.shortcut === key);
  });

  const titleEl = $("#shortcut-action-title");
  const latencyEl = $("#shortcut-latency");
  const descEl = $("#shortcut-desc");
  const badgeEl = $("#shortcut-badge");
  const imgEl = $("#shortcut-preview-img");

  if (titleEl) titleEl.textContent = info.action;
  if (latencyEl) latencyEl.textContent = info.latency;
  if (descEl) descEl.textContent = info.desc;
  if (badgeEl) badgeEl.textContent = info.badge;
  if (imgEl) {
    imgEl.src = `./shots/${info.shot}-${currentAppTheme}.png`;
  }
}

$$(".shortcut-row-card").forEach((card) => {
  card.addEventListener("click", () => {
    const key = card.dataset.shortcut;
    selectShortcut(key);
    playKeyClick();
    const keys = $$(".key-3d", card);
    keys.forEach((k) => k.classList.add("depressed"));
    setTimeout(() => keys.forEach((k) => k.classList.remove("depressed")), 220);
  });
});

window.addEventListener("keydown", (e) => {
  const activeTag = document.activeElement?.tagName?.toLowerCase();
  if (activeTag === "input" || activeTag === "textarea") return;
  const lb = $("#lightbox");
  if (lb && !lb.hidden) return;

  const isCtrl = e.ctrlKey;
  const isAlt = e.altKey;
  const keyUpper = e.key.toUpperCase();

  let matched = null;
  if (isCtrl && isAlt && keyUpper === "L") {
    matched = "ctrl-alt-l";
  } else if (e.key === "Escape") {
    matched = "escape";
  } else if (!isCtrl && isAlt && keyUpper === "E") {
    matched = "alt-e";
  }

  if (matched) {
    e.preventDefault();
    selectShortcut(matched);
    playKeyClick();
    const card = $(`[data-shortcut="${matched}"]`);
    if (card) {
      card.scrollIntoView({ behavior: "smooth", block: "nearest" });
      const keys = $$(".key-3d", card);
      keys.forEach((k) => k.classList.add("depressed"));
      setTimeout(() => keys.forEach((k) => k.classList.remove("depressed")), 300);
    }
    showToast(`Hotkey triggered: ${shortcutConfig[matched].badge}`);
  }
});

// ==========================================================================
// 7. GALLERY CONTROLS, BACKDROP SWITCHER & MULTI-IMAGE LIGHTBOX
// ==========================================================================
$$(".filter-chip").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".filter-chip").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const filter = btn.dataset.filter;

    $$("#gallery-grid .gallery-card").forEach((card) => {
      const cat = card.dataset.category;
      card.style.display = filter === "all" || cat === filter ? "" : "none";
    });
  });
});

const lightbox = $("#lightbox");
const lbImage = $("#lb-image");
const lbCaption = $("#lb-caption");
const lbPrev = $("#lb-prev");
const lbNext = $("#lb-next");

const galleryItems = SITE.gallery.map((g) => ({
  shot: g.id,
  caption: `${g.title} — ${g.desc}`,
}));

let currentLbIndex = 0;

function openLightbox(index) {
  if (!lightbox || !lbImage) return;
  currentLbIndex = (index + galleryItems.length) % galleryItems.length;
  const item = galleryItems[currentLbIndex];
  lbImage.src = `./shots/${item.shot}-${currentAppTheme}.png`;
  lbImage.alt = item.caption;
  if (lbCaption) lbCaption.textContent = item.caption;
  lightbox.hidden = false;
}

function closeLightbox() {
  if (lightbox) lightbox.hidden = true;
}

$$("#gallery-grid .gallery-card").forEach((card) => {
  card.addEventListener("click", () => {
    const idx = parseInt(card.dataset.idx, 10);
    openLightbox(isNaN(idx) ? 0 : idx);
  });
});

$("#hero-app-image")?.addEventListener("click", () => {
  openLightbox(0);
});

$("#shortcut-preview-img")?.addEventListener("click", () => {
  const activeShortcutCard = $(".shortcut-row-card.active");
  const activeKey = activeShortcutCard?.dataset?.shortcut;
  const shotId = activeKey && shortcutConfig[activeKey] ? shortcutConfig[activeKey].shot : null;
  const foundIdx = shotId ? galleryItems.findIndex((g) => g.shot === shotId) : 0;
  openLightbox(foundIdx >= 0 ? foundIdx : 0);
});

lbPrev?.addEventListener("click", () => openLightbox(currentLbIndex - 1));
lbNext?.addEventListener("click", () => openLightbox(currentLbIndex + 1));
$(".lightbox-close-btn", lightbox)?.addEventListener("click", closeLightbox);

lightbox?.addEventListener("click", (e) => {
  if (e.target === lightbox) closeLightbox();
});

window.addEventListener("keydown", (e) => {
  if (!lightbox || lightbox.hidden) return;
  if (e.key === "Escape") closeLightbox();
  if (e.key === "ArrowLeft") openLightbox(currentLbIndex - 1);
  if (e.key === "ArrowRight") openLightbox(currentLbIndex + 1);
});

// ==========================================================================
// 8. COPYABLE SHA-256 CHECKSUM & POWERSHELL VERIFICATION
// ==========================================================================
const copyShaBtn = $("#copy-sha-btn");
const shaTarget = $("#sha-target");
const psCmd = $("#ps-cmd");

async function copyChecksum() {
  const hash = shaTarget?.textContent?.trim() || SITE.sha256;
  try {
    await navigator.clipboard.writeText(hash);
    if (copyShaBtn) {
      copyShaBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg><span>Copied!</span>`;
      setTimeout(() => {
        copyShaBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg><span>Copy</span>`;
      }, 2000);
    }
    showToast("SHA-256 Checksum copied to clipboard!");
  } catch (_) {
    showToast("SHA-256 Checksum ready");
  }
}

copyShaBtn?.addEventListener("click", copyChecksum);
shaTarget?.addEventListener("click", copyChecksum);

psCmd?.addEventListener("click", async () => {
  const cmd = psCmd.textContent.trim();
  try {
    await navigator.clipboard.writeText(cmd);
    showToast("PowerShell verify command copied!");
  } catch (_) {
    showToast("Command copied");
  }
});

// ==========================================================================
// 9. FAQ ACCORDION CATEGORY FILTER
// ==========================================================================
$$(".faq-filter-btn").forEach((chip) => {
  chip.addEventListener("click", () => {
    $$(".faq-filter-btn").forEach((c) => c.classList.remove("active"));
    chip.classList.add("active");
    const filter = chip.dataset.faqFilter;

    $$(".faq-entry").forEach((item) => {
      const cat = item.dataset.faqCat;
      item.style.display = filter === "all" || cat === filter ? "" : "none";
    });
  });
});
