param(
    [string]$InstallerPath = "",
    [string]$PreviousInstallerPath = "",
    [int]$StartupSeconds = 30,
    [switch]$RequireStreamingPreview,
    [switch]$RequirePunctuation,
    [switch]$DisableHotkeys
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
        -Value "untracked files must survive upgrade and uninstall"
}
$previousLocalAppData = $env:LOCALAPPDATA
$appProcess = $null

function Remove-SmokeRoot {
    if (-not (Test-Path -LiteralPath $smokeRoot)) {
        return
    }
    $resolvedSmokeRoot = (Resolve-Path -LiteralPath $smokeRoot).Path
    $resolvedTemporaryRoot = (Resolve-Path -LiteralPath $temporaryRoot).Path.TrimEnd('\') + '\'
    if (-not $resolvedSmokeRoot.StartsWith($resolvedTemporaryRoot, [StringComparison]::OrdinalIgnoreCase) -or
        (Split-Path -Leaf $resolvedSmokeRoot) -notmatch '^VoiceFlow-installer-smoke-[a-f0-9]{32}$') {
        throw "Refusing cleanup outside the owned installer smoke directory"
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
    $env:LOCALAPPDATA = $localAppData
    $smokeDataDir = Join-Path $localAppData "VoiceFlow"
    $previousInstaller = if ($PreviousInstallerPath) {
        (Resolve-Path -LiteralPath $PreviousInstallerPath).Path
    } else {
        $resolvedInstaller
    }
    $previousInstall = Start-Process `
        -FilePath $previousInstaller `
        -ArgumentList @(
            "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOICONS",
            "/DIR=$installRoot"
        ) `
        -WindowStyle Hidden -Wait -PassThru
    if ($previousInstall.ExitCode -ne 0) {
        throw "Previous installer exited with code $($previousInstall.ExitCode)"
    }
    $null = New-Item -ItemType Directory -Path (Join-Path $smokeDataDir "logs") -Force
    $null = New-Item -ItemType Directory -Path (Join-Path $smokeDataDir "knowledge-base") -Force
    $preservedFiles = @{
        "config.yaml" = (Get-Content -LiteralPath (Join-Path $installRoot "config.yaml") -Raw)
        "knowledge-base\user-dictionary.txt" = "UpgradeSentinelTerm"
        "logs\history.jsonl" = '{"timestamp":"2026-10-01T00:00:00","clean_text":"upgrade sentinel","session_id":"upgrade-sentinel"}'
    }
    $preservedHashes = @{}
    foreach ($relative in $preservedFiles.Keys) {
        $target = Join-Path $smokeDataDir $relative
        Set-Content -LiteralPath $target -Value $preservedFiles[$relative] -Encoding utf8
        $preservedHashes[$relative] = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    }
    $untrackedFile = Join-Path $installRoot "user-notes.txt"
    Set-Content -LiteralPath $untrackedFile -Value "Untracked upgrade sentinel" -Encoding utf8
    $untrackedHash = (Get-FileHash -LiteralPath $untrackedFile -Algorithm SHA256).Hash
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
    foreach ($relative in $preservedHashes.Keys) {
        $actual = (Get-FileHash -LiteralPath (Join-Path $smokeDataDir $relative) -Algorithm SHA256).Hash
        if ($actual -ne $preservedHashes[$relative]) {
            throw "Upgrade modified user data: $relative"
        }
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
    if (-not $RequireStreamingPreview) {
        if (-not (Test-Path -LiteralPath (Join-Path $stalePreview "stale-internal-model.txt"))) {
            throw "Upgrade removed an untracked model-directory file"
        }
        foreach ($weight in @("encoder-epoch-99-avg-1.int8.onnx", "decoder-epoch-99-avg-1.onnx", "joiner-epoch-99-avg-1.int8.onnx")) {
            if (Test-Path -LiteralPath (Join-Path $stalePreview $weight)) {
                throw "Installer unexpectedly bundled preview weights"
            }
        }
    }
    if ((Get-FileHash -LiteralPath $untrackedFile -Algorithm SHA256).Hash -ne $untrackedHash) {
        throw "Upgrade modified an untracked application-directory file"
    }
    & python scripts\scan_private_vocabulary.py --root $installRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Installed private-vocabulary scan failed with code $LASTEXITCODE"
    }

    $manifest = Get-Content -Raw (
        Join-Path $installRoot "model-manifest.json"
    ) | ConvertFrom-Json
    $modelIds = @("sensevoice-small-int8")
    if ($RequirePunctuation) {
        $modelIds += "ct-transformer-punctuation-int8"
    }
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
    $appArguments = @("--instance-id", $instanceId, "--data-dir", $smokeDataDir)
    if ($DisableHotkeys) { $appArguments += "--no-hotkeys" }
    $appProcess = Start-Process `
        -FilePath (Join-Path $installRoot "VoiceFlow.exe") `
        -ArgumentList $appArguments `
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
                    ($candidate.hotkeys -eq "ready" -or ($DisableHotkeys -and $candidate.hotkeys -eq "disabled_for_diagnostics")) -and
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
        if (Test-Path -LiteralPath $runtimeState) {
            Write-Output "Runtime state at startup failure:"
            Get-Content -LiteralPath $runtimeState
        }
        $runtimeLog = Join-Path $smokeDataDir "logs\runtime.jsonl"
        if (Test-Path -LiteralPath $runtimeLog) {
            Write-Output "Isolated installer-smoke runtime log:"
            Get-Content -LiteralPath $runtimeLog -Tail 20
        }
        throw "Installed VoiceFlow did not reach runtime ready state"
    }
    if ($state.runtime_mode -ne "frozen") {
        throw "Expected frozen runtime mode, got: $($state.runtime_mode)"
    }
    if ($RequireStreamingPreview -and $state.preview_asr -ne "ready") {
        throw "Installed VoiceFlow streaming preview did not become ready"
    }
    if (-not (Select-String -LiteralPath (Join-Path $smokeDataDir "logs\history.jsonl") -SimpleMatch "upgrade sentinel" -Quiet)) {
        throw "First startup lost preserved history"
    }
    if (-not (Select-String -LiteralPath (Join-Path $smokeDataDir "knowledge-base\user-dictionary.txt") -SimpleMatch "UpgradeSentinelTerm" -Quiet)) {
        throw "First startup lost preserved vocabulary"
    }

    Stop-Process -Id $appProcess.Id -Force
    Wait-Process -Id $appProcess.Id -Timeout 10 -ErrorAction SilentlyContinue
    $appProcess = $null

    $workerIds = @($state.worker_pids.PSObject.Properties | ForEach-Object { [int]$_.Value })
    $workerDeadline = [DateTime]::UtcNow.AddSeconds(5)
    do {
        $remainingWorkers = @($workerIds | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
        if ($remainingWorkers.Count -eq 0) { break }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $workerDeadline)
    if ($remainingWorkers.Count -ne 0) {
        throw "Native workers outlived the UI: $($remainingWorkers -join ', ')"
    }
    $uninstallHashes = @{}
    foreach ($relative in $preservedFiles.Keys) {
        $uninstallHashes[$relative] = (Get-FileHash -LiteralPath (Join-Path $smokeDataDir $relative) -Algorithm SHA256).Hash
    }

    $uninstall = Start-Process `
        -FilePath (Join-Path $installRoot "unins000.exe") `
        -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") `
        -WindowStyle Hidden `
        -Wait `
        -PassThru
    if ($uninstall.ExitCode -ne 0) {
        throw "Uninstaller exited with code $($uninstall.ExitCode)"
    }
    if (Test-Path -LiteralPath (Join-Path $installRoot "VoiceFlow.exe")) {
        throw "Uninstaller left the installed executable behind"
    }
    if ((Get-FileHash -LiteralPath $untrackedFile -Algorithm SHA256).Hash -ne $untrackedHash) {
        throw "Uninstaller removed or modified an untracked application-directory file"
    }
    if (-not (Test-Path -LiteralPath $runtimeState)) {
        throw "Uninstaller removed user-owned VoiceFlow data"
    }
    foreach ($relative in $uninstallHashes.Keys) {
        $actual = (Get-FileHash -LiteralPath (Join-Path $smokeDataDir $relative) -Algorithm SHA256).Hash
        if ($actual -ne $uninstallHashes[$relative]) {
            throw "Uninstaller modified user data: $relative"
        }
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
