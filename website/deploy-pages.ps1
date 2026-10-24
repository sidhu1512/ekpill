<#
.SYNOPSIS
Deploy EkPill website to GitHub Pages (gh-pages branch).

.DESCRIPTION
Builds the website using Vite, validates output and relative asset paths,
and pushes the dist/ directory to the gh-pages branch.

.PARAMETER DryRun
Runs the build and validation without pushing to remote repository.
#>

param(
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "EkPill GitHub Pages Deployment (PowerShell)" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

if ($DryRun) {
  node scripts/deploy-gh-pages.mjs --dry-run
} else {
  node scripts/deploy-gh-pages.mjs
}
