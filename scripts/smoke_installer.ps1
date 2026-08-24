param(
    [string]$InstallerPath = "",
    [int]$StartupSeconds = 30,
    [switch]$RequireStreamingPreview
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($InstallerPath)) {
    $versionSource = Get-Content -LiteralPath "src\version.py" -Raw
    $versionMatch = [regex]::Match(
        $versionSource,
        'APP_VERSION\s*=\s*[''"]([^''"]+)[''"]'
    )
    if (-not $versionMatch.Success) {
        throw "Could not read APP_VERSION from src\version.py"
    }
    $version = $versionMatch.Groups[1].Value
    $InstallerPath = Join-Path `
        "dist\installer" `
        "VoiceFlow-$version-Windows-x64.exe"
}
$resolvedInstaller = (Resolve-Path -LiteralPath $InstallerPath).Path
$temporaryRoot = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$smokeRoot = Join-Path $temporaryRoot (
    "VoiceFlow-installer-smoke-" + [guid]::NewGuid().ToString("N")
)
$installRoot = Join-Path $smokeRoot "install"
$localAppData = Join-Path $smokeRoot "localappdata"
$null = New-Item -ItemType Directory -Path $localAppData
if (-not $RequireStreamingPreview) {
    $stalePreview = Join-Path $installRoot "models\streaming-preview"
    $null = New-Item -ItemType Directory -Path $stalePreview -Force
    Set-Content `
        -LiteralPath (Join-Path $stalePreview "stale-internal-model.txt") `
        -Value "must be removed by the public installer"
}
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
        "docs\streaming-preview-model-review.md",
        "unins000.exe"
    )
    if ($RequireStreamingPreview) {
        $required += @(
            "models\streaming-preview\encoder-epoch-99-avg-1.int8.onnx",
            "models\streaming-preview\decoder-epoch-99-avg-1.onnx",
            "models\streaming-preview\joiner-epoch-99-avg-1.int8.onnx",
            "models\streaming-preview\tokens.txt"
        )
    }
    foreach ($relative in $required) {
        $target = Join-Path $installRoot $relative
        if (-not (Test-Path -LiteralPath $target)) {
            throw "Installed asset missing: $relative"
        }
    }
    $shippedHistory = @(
        Get-ChildItem `
            -LiteralPath $installRoot `
            -Filter "history.jsonl" `
            -Recurse `
            -File `
            -ErrorAction SilentlyContinue
    )
    if ($shippedHistory.Count -ne 0) {
        throw "Installer contains local dictation history"
    }
    if (Test-Path -LiteralPath (Join-Path $installRoot "models\sensevoice\.cache")) {
        throw "Installer contains a Hugging Face cache"
    }
    if (
        -not $RequireStreamingPreview -and
        (Test-Path -LiteralPath (Join-Path $installRoot "models\streaming-preview"))
    ) {
        throw "Public installer retained an experimental preview model"
    }
    & python scripts\scan_private_vocabulary.py --root $installRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Installed private-vocabulary scan failed with code $LASTEXITCODE"
    }

    $manifest = Get-Content -Raw (
        Join-Path $installRoot "model-manifest.json"
    ) | ConvertFrom-Json
    $modelIds = @("sensevoice-small-int8")
    if ($RequireStreamingPreview) {
        $modelIds += "streaming-zipformer-small-bilingual-zh-en-int8"
    }
    foreach ($modelId in $modelIds) {
        $model = $manifest.models.$modelId
        foreach ($entry in $model.files) {
            if (
                $entry.path.StartsWith("test_wavs/") -or
                $entry.PSObject.Properties.Name -contains "package" -and
                -not $entry.package
            ) {
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
                throw "Installed model size mismatch: $modelId/$($entry.path)"
            }
            if ($actualHash -ne $entry.sha256) {
                throw "Installed model SHA256 mismatch: $modelId/$($entry.path)"
            }
        }
    }

    $env:LOCALAPPDATA = $localAppData
    $smokeDataDir = Join-Path $localAppData "VoiceFlow"
    $instanceId = "installer-smoke-" + [guid]::NewGuid().ToString("N")
    $appProcess = Start-Process `
        -FilePath (Join-Path $installRoot "VoiceFlow.exe") `
        -ArgumentList @(
            "--instance-id", $instanceId,
            "--data-dir", $smokeDataDir
        ) `
        -WorkingDirectory $installRoot `
        -WindowStyle Hidden `
        -PassThru

    $runtimeState = Join-Path $smokeDataDir "runtime-state.json"
    $deadline = [DateTime]::UtcNow.AddSeconds($StartupSeconds)
    $state = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($appProcess.HasExited) {
            throw "Installed VoiceFlow exited early with code $($appProcess.ExitCode)"
        }
        if (Test-Path -LiteralPath $runtimeState) {
            try {
                $candidate = Get-Content -Raw $runtimeState | ConvertFrom-Json
                if (
                    $candidate.phase -eq "ready" -and
                    $candidate.hotkeys -eq "ready" -and
                    $candidate.worker -eq "ready" -and
                    $candidate.final_asr -eq "ready"
                ) {
                    $state = $candidate
                    break
                }
            }
            catch {
                # Atomic replacement can briefly race the reader; retry.
            }
        }
        Start-Sleep -Milliseconds 100
    }
    if ($null -eq $state) {
        throw "Installed VoiceFlow did not reach runtime ready state"
    }
    if ($state.runtime_mode -ne "frozen") {
        throw "Expected frozen runtime mode, got: $($state.runtime_mode)"
    }
    if ($RequireStreamingPreview -and $state.preview_asr -ne "ready") {
        throw "Installed VoiceFlow streaming preview did not become ready"
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
