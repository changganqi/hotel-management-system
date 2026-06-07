param(
  [switch]$SkipInstall,
  [switch]$NoClean,
  [switch]$BundleBrowser,
  [switch]$Console
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$distName = "ShanhaiHotelSync"
$iconPath = Join-Path $PSScriptRoot "static\favicon.ico"

function Get-PlaywrightBrowsersDir {
  $script = @"
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    exe = Path(p.chromium.executable_path).resolve()

print(exe.parents[2])
"@

  $output = python -c $script
  if ($LASTEXITCODE -ne 0) {
    throw "Unable to resolve Playwright browser directory"
  }

  $pathText = ($output | Select-Object -Last 1).Trim()
  if (-not $pathText) {
    throw "Playwright browser directory is empty"
  }

  if (-not (Test-Path $pathText)) {
    throw "Playwright browser directory not found: $pathText"
  }

  return $pathText
}

if (-not $SkipInstall) {
  python -m pip install -r requirements.txt
  python -m pip install -r requirements-build.txt
  if ($BundleBrowser) {
    python -m playwright install chromium
  }
}

if (-not $NoClean) {
  if (Test-Path "build") {
    Remove-Item "build" -Recurse -Force
  }
  if (Test-Path "dist") {
    Remove-Item "dist" -Recurse -Force
  }
}

$pyInstallerArgs = @(
  "--noconfirm",
  "--clean",
  "--name", $distName,
  "--onedir",
  "--collect-all", "playwright",
  "--collect-all", "pystray",
  "--collect-all", "PIL",
  "--hidden-import", "pystray._win32",
  "--hidden-import", "six",
  "--add-data", "templates;templates",
  "--add-data", "static;static",
  "--add-data", "data;data",
  "--add-data", ".env.example;.",
  "run_system.py"
)

if (Test-Path $iconPath) {
  $pyInstallerArgs += @("--icon", $iconPath)
}

if ($Console) {
  $pyInstallerArgs += "--console"
} else {
  # Default to windowed exe so end-users do not see a black cmd window.
  $pyInstallerArgs += "--noconsole"
}

python -m PyInstaller @pyInstallerArgs
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller build failed"
}

$distRoot = Join-Path (Join-Path $PSScriptRoot "dist") $distName
$sessionsDir = Join-Path $distRoot "sessions"
if (-not (Test-Path $sessionsDir)) {
  New-Item -ItemType Directory -Path $sessionsDir | Out-Null
}

$bundledBrowsers = Join-Path $distRoot "ms-playwright"
$envTemplate = @"
LOGIN_BROWSER_CHANNEL=msedge
SYNC_BROWSER_CHANNEL=msedge
DATA_RETENTION_DAYS=31
AUTO_BACKUP_INTERVAL_HOURS=12
"@

if ($BundleBrowser) {
  if (Test-Path $bundledBrowsers) {
    Remove-Item $bundledBrowsers -Recurse -Force
  }

  $sourceBrowsers = Get-PlaywrightBrowsersDir
  Copy-Item -Path $sourceBrowsers -Destination $bundledBrowsers -Recurse -Force

  $envTemplate = @"
PLAYWRIGHT_BROWSERS_PATH=ms-playwright
LOGIN_BROWSER_CHANNEL=chromium
SYNC_BROWSER_CHANNEL=chromium
DATA_RETENTION_DAYS=31
AUTO_BACKUP_INTERVAL_HOURS=12
"@
} elseif (Test-Path $bundledBrowsers) {
  Remove-Item $bundledBrowsers -Recurse -Force
}

$envPath = Join-Path $distRoot ".env.example"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($envPath, $envTemplate, $utf8NoBom)

Write-Host "Build complete: $distRoot"
Write-Host "Start app: $distRoot\\ShanhaiHotelSync.exe"
if ($BundleBrowser) {
  Write-Host "Bundled browser: $bundledBrowsers"
} else {
  Write-Host "Browser mode: Edge channel (no bundled browser)"
}
if ($Console) {
  Write-Host "Exe mode: console (debug)"
} else {
  Write-Host "Exe mode: windowed (no black console window)"
}
Write-Host "Runtime settings template written: $distRoot\\.env.example"
