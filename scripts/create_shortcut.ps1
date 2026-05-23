param(
    [string]$ShortcutName = "VoiceFlow"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$StartBat = Join-Path $ProjectRoot "start.bat"
$IconPath = Join-Path $ProjectRoot "assets\voiceflow.ico"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "$ShortcutName.lnk"

if (-not (Test-Path $StartBat)) {
    throw "start.bat not found: $StartBat"
}

if (-not (Test-Path $IconPath)) {
    & (Join-Path $ProjectRoot "venv\Scripts\python.exe") (Join-Path $ProjectRoot "scripts\generate_icon.py")
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $StartBat
$Shortcut.WorkingDirectory = $ProjectRoot
if (Test-Path $IconPath) {
    $Shortcut.IconLocation = $IconPath
}
$Shortcut.Description = "VoiceFlow local dictation"
$Shortcut.Save()

Write-Host "Created shortcut: $ShortcutPath"
