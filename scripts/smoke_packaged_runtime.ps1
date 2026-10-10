param(
    [string]$AppDir = "dist\VoiceFlow",
    [int]$StartupTimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"
$resolvedAppDir = (Resolve-Path -LiteralPath $AppDir).Path
$executable = Join-Path $resolvedAppDir "VoiceFlow.exe"
if (-not (Test-Path -LiteralPath $executable)) {
    throw "VoiceFlow.exe missing: $executable"
}

$temporaryRoot = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$smokeRoot = Join-Path $temporaryRoot (
    "VoiceFlow-frozen-smoke-" + [guid]::NewGuid().ToString("N")
)
$null = New-Item -ItemType Directory -Path $smokeRoot
$previousLocalAppData = $env:LOCALAPPDATA
$env:LOCALAPPDATA = $smokeRoot
$process = $null

try {
    $process = Start-Process `
        -FilePath $executable `
        -WorkingDirectory $resolvedAppDir `
        -PassThru `
        -WindowStyle Hidden

    $runtimeRoot = Join-Path $smokeRoot "VoiceFlow"
    $runtimeState = Join-Path $runtimeRoot "runtime-state.json"
    $startupDeadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
    $state = $null
    while ($null -eq $state) {
        $process.Refresh()
        if ($process.HasExited) {
            throw "Packaged VoiceFlow exited before readiness with code $($process.ExitCode)"
        }
        if ([DateTime]::UtcNow -ge $startupDeadline) {
            throw (
                "Packaged VoiceFlow readiness timed out after " +
                "$StartupTimeoutSeconds seconds: $runtimeState"
            )
        }
        if (Test-Path -LiteralPath $runtimeState) {
            try {
                $candidate = Get-Content -Raw -LiteralPath $runtimeState | ConvertFrom-Json
                if ($candidate.phase -eq "ready" -and $candidate.worker -eq "ready" -and $candidate.final_asr -eq "ready" -and $candidate.hotkeys -eq "ready") {
                    $state = $candidate
                    break
                }
                if ($candidate.phase -in @("degraded", "error")) {
                    throw "Packaged VoiceFlow initialization failed: $($candidate.last_error_code)"
                }
            }
            catch [System.ArgumentException] {
                # Retry an incomplete read during atomic state replacement.
            }
        }
        Start-Sleep -Milliseconds 250
    }

    $required = @(
        "config.yaml",
        "runtime-state.json",
        "knowledge-base",
        "logs",
        "models"
    )
    foreach ($relative in $required) {
        $target = Join-Path $runtimeRoot $relative
        if (-not (Test-Path -LiteralPath $target)) {
            throw "Missing frozen runtime path: $target"
        }
    }

    $state = Get-Content -Raw (Join-Path $runtimeRoot "runtime-state.json") |
        ConvertFrom-Json
    if ($state.runtime_mode -ne "frozen") {
        throw "Expected frozen runtime mode, got: $($state.runtime_mode)"
    }
    if ($state.install_dir -ne $resolvedAppDir) {
        throw "Install directory mismatch: $($state.install_dir)"
    }

    Write-Output "Packaged runtime smoke: ok"
}
finally {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
        Wait-Process -Id $process.Id -Timeout 10 -ErrorAction SilentlyContinue
    }
    $env:LOCALAPPDATA = $previousLocalAppData
    if (Test-Path -LiteralPath $smokeRoot) {
        $checkedRoot = [System.IO.Path]::GetFullPath($smokeRoot)
        $checkedParent = [System.IO.Path]::GetFullPath($temporaryRoot).TrimEnd('\') + '\'
        if (-not $checkedRoot.StartsWith($checkedParent, [System.StringComparison]::OrdinalIgnoreCase) -or (Split-Path $checkedRoot -Leaf) -notlike "VoiceFlow-frozen-smoke-*") {
            throw "Refusing cleanup outside the exact temporary smoke directory"
        }
        for ($attempt = 1; $attempt -le 5; $attempt++) {
            try {
                Remove-Item -LiteralPath $smokeRoot -Recurse -Force
                break
            }
            catch {
                if ($attempt -eq 5) {
                    throw
                }
                Start-Sleep -Milliseconds 250
            }
        }
    }
}
