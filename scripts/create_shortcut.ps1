param(
    [string]$ShortcutName = "VoiceFlow"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Pythonw = Join-Path $ProjectRoot "venv\Scripts\pythonw.exe"
$Launcher = Join-Path $ProjectRoot "scripts\launch_voiceflow.pyw"
$IconPath = Join-Path $ProjectRoot "assets\voiceflow.ico"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "$ShortcutName.lnk"

if (-not (Test-Path $Pythonw)) {
    throw "pythonw.exe not found: $Pythonw"
}

if (-not (Test-Path $Launcher)) {
    throw "launcher not found: $Launcher"
}

if (-not (Test-Path $IconPath)) {
    & (Join-Path $ProjectRoot "venv\Scripts\python.exe") (Join-Path $ProjectRoot "scripts\generate_icon.py")
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Pythonw
$Shortcut.Arguments = "`"$Launcher`""
$Shortcut.WorkingDirectory = $ProjectRoot
if (Test-Path $IconPath) {
    $Shortcut.IconLocation = $IconPath
}
$Shortcut.Description = "VoiceFlow local dictation"
$Shortcut.Save()

Write-Host "Created shortcut: $ShortcutPath"
