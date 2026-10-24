import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const websiteDir = path.resolve(__dirname, "..");
const distDir = path.resolve(websiteDir, "dist");
const repoRoot = path.resolve(websiteDir, "..");

const isDryRun = process.argv.includes("--dry-run");

console.log("==========================================");
console.log("EkPill GitHub Pages Automated Deployment");
console.log("==========================================");

// Step 1: Build website
console.log("\n[1/3] Building website with Vite...");
execSync("npm run build", { cwd: websiteDir, stdio: "inherit" });

// Step 2: Validate dist output
if (!fs.existsSync(path.join(distDir, "index.html"))) {
  console.error("[ERROR] dist/index.html was not generated.");
  process.exit(1);
}

// Ensure .nojekyll exists
const nojekyllPath = path.join(distDir, ".nojekyll");
if (!fs.existsSync(nojekyllPath)) {
  fs.writeFileSync(nojekyllPath, "# Disable Jekyll processing on GitHub Pages\n");
}
console.log("[PASS] Verified dist/ build and .nojekyll");

// Run asset verifier
execSync("node scripts/verify-assets.mjs", { cwd: websiteDir, stdio: "inherit" });

// Step 3: Determine git remote
let remoteUrl = "https://github.com/sidhu1512/ekpill.git";
try {
  const detected = execSync("git config --get remote.origin.url", { cwd: repoRoot, encoding: "utf8" }).trim();
  if (detected) remoteUrl = detected;
} catch (_) {
  console.warn("[WARN] Could not detect git remote origin, falling back to:", remoteUrl);
}

console.log(`[INFO] Git Remote: ${remoteUrl}`);

if (isDryRun) {
  console.log("\n[PASS] Dry run complete. Build output verified in website/dist.");
  process.exit(0);
}

// Step 4: Push to gh-pages branch
console.log("\n[2/3] Deploying dist to gh-pages branch...");
const gitDir = path.join(distDir, ".git");
if (fs.existsSync(gitDir)) {
  fs.rmSync(gitDir, { recursive: true, force: true });
}

try {
  execSync("git init -b gh-pages", { cwd: distDir, stdio: "inherit" });
  execSync("git add -A", { cwd: distDir, stdio: "inherit" });
  const time = new Date().toISOString();
  execSync(`git commit -m "Deploy EkPill website [skip ci] - ${time}"`, { cwd: distDir, stdio: "inherit" });
  execSync(`git remote add origin ${remoteUrl}`, { cwd: distDir, stdio: "inherit" });
  console.log("[3/3] Pushing to origin/gh-pages (force)...");
  execSync("git push -f origin gh-pages", { cwd: distDir, stdio: "inherit" });
  console.log("\n[PASS] Successfully deployed to gh-pages branch.");
} catch (err) {
  console.error("\n[ERROR] Deployment failed:", err.message);
  process.exit(1);
} finally {
  if (fs.existsSync(gitDir)) {
    try {
      fs.rmSync(gitDir, { recursive: true, force: true });
    } catch (_) {}
  }
}
