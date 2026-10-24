import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const websiteDir = path.resolve(__dirname, "..");
const repoRoot = path.resolve(websiteDir, "..");

let failures = 0;
let checks = 0;

function pass(msg) {
  checks++;
  console.log(`[PASS] ${msg}`);
}

function fail(msg) {
  checks++;
  failures++;
  console.error(`[FAIL] ${msg}`);
}

function checkFileNonEmpty(filePath, minBytes = 1024, label = "") {
  const display = label || path.relative(repoRoot, filePath);
  if (!fs.existsSync(filePath)) {
    fail(`Missing file: ${display}`);
    return false;
  }
  const stat = fs.statSync(filePath);
  if (stat.size < minBytes) {
    fail(`File too small (${stat.size}B < ${minBytes}B): ${display}`);
    return false;
  }
  pass(`Verified asset (${(stat.size / 1024).toFixed(1)} KB): ${display}`);
  return true;
}

console.log("====================================================");
console.log("EkPill Asset, Link & Zero-Emoji Integrity Verifier");
console.log("====================================================\n");

// 1. Verify Flagship Showcase Images & Dual-Format Recordings in docs/showcase & website/public/showcase
const showcasePngs = [
  "hero_dark.png",
  "hero_light.png",
  "bento_capsule_morph.png",
  "bento_quick_settings.png",
  "bento_audio_media.png",
  "bento_files_hub.png",
  "bento_launcher_hotkeys.png",
  "bento_screen_recorder.png",
];

const showcaseDemos = [
  "demo_hero_tour",
  "demo_capsule_morph",
  "demo_audio_media",
  "demo_files_launcher",
  "demo_recorder_radios",
];

for (const baseDir of [
  path.join(repoRoot, "docs", "showcase"),
  path.join(websiteDir, "public", "showcase"),
]) {
  for (const png of showcasePngs) {
    checkFileNonEmpty(path.join(baseDir, png), 10240);
  }
  for (const demo of showcaseDemos) {
    checkFileNonEmpty(path.join(baseDir, `${demo}.webm`), 10240);
    checkFileNonEmpty(path.join(baseDir, `${demo}.gif`), 10240);
  }
}

// 2. Verify 16 Paired Light/Dark Gallery Shots in website/public/shots
const galleryBases = [
  "capsule-top",
  "quick-settings",
  "media-player",
  "audio-mixer",
  "wifi-bluetooth",
  "files-hub",
  "app-launcher",
  "recorder-settings",
];

for (const base of galleryBases) {
  checkFileNonEmpty(path.join(websiteDir, "public", "shots", `${base}-light.png`), 5120);
  checkFileNonEmpty(path.join(websiteDir, "public", "shots", `${base}-dark.png`), 5120);
}
checkFileNonEmpty(path.join(websiteDir, "public", "shots", "bubble.png"), 1024);
checkFileNonEmpty(path.join(websiteDir, "public", "shots", "pip-light.png"), 1024);
checkFileNonEmpty(path.join(websiteDir, "public", "shots", "pip-dark.png"), 1024);

// 3. Parse README.md and verify all local relative image/doc links
const readmePath = path.join(repoRoot, "README.md");
if (checkFileNonEmpty(readmePath, 4096)) {
  const readmeText = fs.readFileSync(readmePath, "utf8");
  const attrRegex = /(?:src|srcset|href)=["']([^"']+)["']/g;
  const mdLinkRegex = /\]\(([^)]+)\)/g;

  const refs = new Set();
  let m;
  while ((m = attrRegex.exec(readmeText)) !== null) refs.add(m[1]);
  while ((m = mdLinkRegex.exec(readmeText)) !== null) refs.add(m[1]);

  for (const ref of refs) {
    if (ref.startsWith("http://") || ref.startsWith("https://") || ref.startsWith("#")) continue;
    const cleanRef = ref.split("#")[0].trim();
    if (!cleanRef) continue;
    const target = path.resolve(repoRoot, cleanRef);
    checkFileNonEmpty(target, 100, `README ref -> ${cleanRef}`);
  }
}

// 4. Parse website/index.html local relative asset references
const indexHtmlPath = path.join(websiteDir, "index.html");
if (checkFileNonEmpty(indexHtmlPath, 4096)) {
  const html = fs.readFileSync(indexHtmlPath, "utf8");
  const srcRegex = /(?:src|data-src|href)=["'](\.\/[^"']+)["']/g;
  let m;
  while ((m = srcRegex.exec(html)) !== null) {
    const rel = m[1].replace(/^\.\//, "");
    const inPublic = path.join(websiteDir, "public", rel);
    const inWebsite = path.join(websiteDir, rel);
    if (fs.existsSync(inPublic)) {
      checkFileNonEmpty(inPublic, 100, `index.html public ref -> ${rel}`);
    } else {
      checkFileNonEmpty(inWebsite, 100, `index.html src ref -> ${rel}`);
    }
  }
}

// 5. Verify Zero-Emoji Rule across README.md, website/index.html, website/src/main.js, website/src/style.css, website/src/config.js
const zeroEmojiTargets = [
  path.join(repoRoot, "README.md"),
  path.join(websiteDir, "index.html"),
  path.join(websiteDir, "src", "main.js"),
  path.join(websiteDir, "src", "config.js"),
  path.join(websiteDir, "src", "style.css"),
];

const emojiRegex = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu;
for (const file of zeroEmojiTargets) {
  const content = fs.readFileSync(file, "utf8");
  const matches = content.match(emojiRegex);
  const rel = path.relative(repoRoot, file);
  if (matches && matches.length > 0) {
    fail(`Found ${matches.length} forbidden Unicode emoji/dingbat(s) in ${rel}: ${[...new Set(matches)].join(" ")}`);
  } else {
    pass(`Zero Unicode emojis/dingbats in ${rel}`);
  }
}

// 6. Check dist/ build output (must exist after build)
const distIndex = path.join(websiteDir, "dist", "index.html");
if (checkFileNonEmpty(distIndex, 4096, "website/dist/index.html")) {
  const distHtml = fs.readFileSync(distIndex, "utf8");
  if (distHtml.includes('src="/assets/') || distHtml.includes('href="/assets/')) {
    fail("website/dist/index.html contains root-absolute /assets/ paths instead of relative ./assets/ paths");
  } else {
    pass("website/dist/index.html uses relative ./assets/ paths for GitHub Pages subpath hosting");
  }
}

console.log(`\n====================================================`);
console.log(`Verification Summary: ${checks - failures}/${checks} checks passed.`);
console.log(`====================================================`);

if (failures > 0) {
  process.exit(1);
}
