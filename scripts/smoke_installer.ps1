param(
    [string]$InstallerPath = "dist\installer\VoiceFlow-Setup-0.2.0-beta.1-x64.exe",
    [int]$StartupSeconds = 8
)

$ErrorActionPreference = "Stop"
$resolvedInstaller = (Resolve-Path -LiteralPath $InstallerPath).Path
$temporaryRoot = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$smokeRoot = Join-Path $temporaryRoot (
    "VoiceFlow-installer-smoke-" + [guid]::NewGuid().ToString("N")
)
$installRoot = Join-Path $smokeRoot "install"
$localAppData = Join-Path $smokeRoot "localappdata"
$null = New-Item -ItemType Directory -Path $localAppData
$previousLocalAppData = $env:LOCALAPPDATA
$appProcess = $null

function Remove-SmokeRoot {
    if (-not (Test-Path -LiteralPath $smokeRoot)) {
        return
    }
    for ($attempt = 1; $attempt -le 8; $attempt++) {
        try {
            Remove-Item -LiteralPath $smokeRoot -Recurse -Force
            return
        }
        catch {
            if ($attempt -eq 8) {
                throw
            }
            Start-Sleep -Milliseconds 250
        }
    }
}

try {
    $install = Start-Process `
        -FilePath $resolvedInstaller `
        -ArgumentList @(
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/NOICONS",
            "/DIR=$installRoot"
        ) `
        -WindowStyle Hidden `
        -Wait `
        -PassThru
    if ($install.ExitCode -ne 0) {
        throw "Installer exited with code $($install.ExitCode)"
    }

    $required = @(
        "VoiceFlow.exe",
        "config.yaml",
        "model-manifest.json",
        "models\sensevoice\model.int8.onnx",
        "models\sensevoice\tokens.txt",
        "licenses\FunASR-MODEL-LICENSE.txt",
        "licenses\Qt-LGPL-3.0-only.txt",
        "licenses\GPL-3.0-only.txt",
        "licenses\Chromium-BSD.txt",
        "docs\sensevoice-redistribution-decision.md",
        "docs\qt-lgpl-compliance.md",
        "unins000.exe"
    )
    foreach ($relative in $required) {
        $target = Join-Path $installRoot $relative
        if (-not (Test-Path -LiteralPath $target)) {
            throw "Installed asset missing: $relative"
        }
    }
    if (Test-Path -LiteralPath (Join-Path $installRoot "models\sensevoice\.cache")) {
        throw "Installer contains a Hugging Face cache"
    }

    $manifest = Get-Content -Raw (
        Join-Path $installRoot "model-manifest.json"
    ) | ConvertFrom-Json
    $model = $manifest.models.'sensevoice-small-int8'
    foreach ($entry in $model.files) {
        if ($entry.path -notin @("model.int8.onnx", "tokens.txt")) {
            continue
        }
        $target = Join-Path (
            Join-Path $installRoot $model.target_dir
        ) $entry.path
        $file = Get-Item -LiteralPath $target
        $actualHash = (
            Get-FileHash -LiteralPath $target -Algorithm SHA256
        ).Hash.ToLowerInvariant()
        if ($file.Length -ne [int64]$entry.size) {
            throw "Installed model size mismatch: $($entry.path)"
        }
        if ($actualHash -ne $entry.sha256) {
            throw "Installed model SHA256 mismatch: $($entry.path)"
        }
    }

    $env:LOCALAPPDATA = $localAppData
    $appProcess = Start-Process `
        -FilePath (Join-Path $installRoot "VoiceFlow.exe") `
        -WorkingDirectory $installRoot `
        -WindowStyle Hidden `
        -PassThru
    Start-Sleep -Seconds $StartupSeconds
    if ($appProcess.HasExited) {
        throw "Installed VoiceFlow exited early with code $($appProcess.ExitCode)"
    }

    $runtimeState = Join-Path $localAppData "VoiceFlow\runtime-state.json"
    if (-not (Test-Path -LiteralPath $runtimeState)) {
        throw "Installed VoiceFlow did not create runtime-state.json"
    }
    $state = Get-Content -Raw $runtimeState | ConvertFrom-Json
    if ($state.runtime_mode -ne "frozen") {
        throw "Expected frozen runtime mode, got: $($state.runtime_mode)"
    }

    Stop-Process -Id $appProcess.Id -Force
    Wait-Process -Id $appProcess.Id -Timeout 10 -ErrorAction SilentlyContinue
    $appProcess = $null

    $uninstall = Start-Process `
        -FilePath (Join-Path $installRoot "unins000.exe") `
        -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") `
        -WindowStyle Hidden `
        -Wait `
        -PassThru
    if ($uninstall.ExitCode -ne 0) {
        throw "Uninstaller exited with code $($uninstall.ExitCode)"
    }
    if (Test-Path -LiteralPath $installRoot) {
        throw "Uninstaller left the application directory behind"
    }
    if (-not (Test-Path -LiteralPath $runtimeState)) {
        throw "Uninstaller removed user-owned VoiceFlow data"
    }

    Write-Output "Installer smoke: ok"
}
finally {
    if ($appProcess -and -not $appProcess.HasExited) {
        Stop-Process -Id $appProcess.Id -Force
        Wait-Process -Id $appProcess.Id -Timeout 10 -ErrorAction SilentlyContinue
    }
    $env:LOCALAPPDATA = $previousLocalAppData
    Remove-SmokeRoot
}
