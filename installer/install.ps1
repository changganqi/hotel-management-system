$ErrorActionPreference = "Stop"

$appName = "山海宾馆房量同步台"
$installRoot = Join-Path $env:LOCALAPPDATA "ShanhaiHotelSync"
$payloadZip = Join-Path $PSScriptRoot "ShanhaiHotelSync-bundled.zip"
$tempRoot = Join-Path $env:TEMP ("ShanhaiHotelSync-install-" + [guid]::NewGuid().ToString("N"))

if (-not (Test-Path -LiteralPath $payloadZip)) {
  throw "Missing payload: $payloadZip"
}

if (Test-Path -LiteralPath $tempRoot) {
  Remove-Item -LiteralPath $tempRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $tempRoot | Out-Null

try {
  Expand-Archive -LiteralPath $payloadZip -DestinationPath $tempRoot -Force
  $payloadRoot = Join-Path $tempRoot "ShanhaiHotelSync"
  if (-not (Test-Path -LiteralPath (Join-Path $payloadRoot "ShanhaiHotelSync.exe"))) {
    throw "Invalid package: ShanhaiHotelSync.exe was not found."
  }

  if (Test-Path -LiteralPath $installRoot) {
    $backupRoot = $installRoot + ".old"
    if (Test-Path -LiteralPath $backupRoot) {
      Remove-Item -LiteralPath $backupRoot -Recurse -Force
    }
    Rename-Item -LiteralPath $installRoot -NewName (Split-Path -Leaf $backupRoot)
  }

  New-Item -ItemType Directory -Path (Split-Path -Parent $installRoot) -Force | Out-Null
  Move-Item -LiteralPath $payloadRoot -Destination $installRoot

  $dataDir = Join-Path $installRoot "data"
  $sessionsDir = Join-Path $installRoot "sessions"
  if (-not (Test-Path -LiteralPath $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir | Out-Null
  }
  if (-not (Test-Path -LiteralPath $sessionsDir)) {
    New-Item -ItemType Directory -Path $sessionsDir | Out-Null
  }

  $envPath = Join-Path $installRoot ".env"
  $envExample = Join-Path $installRoot ".env.example"
  if ((-not (Test-Path -LiteralPath $envPath)) -and (Test-Path -LiteralPath $envExample)) {
    Copy-Item -LiteralPath $envExample -Destination $envPath
  }

  $shell = New-Object -ComObject WScript.Shell
  $desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$appName.lnk"
  $shortcut = $shell.CreateShortcut($desktopShortcut)
  $shortcut.TargetPath = Join-Path $installRoot "ShanhaiHotelSync.exe"
  $shortcut.WorkingDirectory = $installRoot
  $shortcut.IconLocation = Join-Path $installRoot "static\favicon.ico"
  $shortcut.Save()

  $startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) $appName
  New-Item -ItemType Directory -Path $startMenuDir -Force | Out-Null
  $startShortcut = Join-Path $startMenuDir "$appName.lnk"
  $shortcut = $shell.CreateShortcut($startShortcut)
  $shortcut.TargetPath = Join-Path $installRoot "ShanhaiHotelSync.exe"
  $shortcut.WorkingDirectory = $installRoot
  $shortcut.IconLocation = Join-Path $installRoot "static\favicon.ico"
  $shortcut.Save()

  Start-Process -FilePath (Join-Path $installRoot "ShanhaiHotelSync.exe") -WorkingDirectory $installRoot
}
finally {
  if (Test-Path -LiteralPath $tempRoot) {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force
  }
}
