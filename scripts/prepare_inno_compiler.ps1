param(
    [Parameter(Mandatory = $true)]
    [string]$ToolchainRoot
)

$ErrorActionPreference = "Stop"
$toolRoot = [IO.Path]::GetFullPath($ToolchainRoot)
if ($toolRoot.TrimEnd('\') -eq [IO.Path]::GetPathRoot($toolRoot).TrimEnd('\')) {
    throw "ToolchainRoot must name a dedicated build directory"
}
$download = Join-Path $toolRoot "innosetup-6.7.3.exe"
$portableRoot = Join-Path $toolRoot "inno-6.7.3"
if ((Test-Path -LiteralPath $download) -or (Test-Path -LiteralPath $portableRoot)) {
    throw "Compiler target already exists; use a fresh dedicated toolchain directory"
}
$null = New-Item -ItemType Directory -Path $toolRoot -Force
$url = "https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe"
$expected = "9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732"
Invoke-WebRequest -Uri $url -OutFile $download
$actual = (Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected -or (Get-Item -LiteralPath $download).Length -ne 10592232) {
    throw "Pinned Inno compiler installer integrity check failed"
}
$signature = Get-AuthenticodeSignature -LiteralPath $download
if ($signature.Status -ne "Valid" -or $signature.SignerCertificate.Subject -notmatch '(^|, )CN=Pyrsys B\.V\.,') {
    throw "Pinned Inno compiler installer publisher verification failed"
}
$arguments = @(
    "/PORTABLE=1", "/CURRENTUSER", "/VERYSILENT", "/SUPPRESSMSGBOXES",
    "/NORESTART", "/NOICONS", ('/DIR="' + $portableRoot + '"'),
    ('/LOG="' + (Join-Path $toolRoot "portable-extraction.log") + '"')
)
$process = Start-Process -FilePath $download -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0) {
    throw "Portable compiler extraction failed: $($process.ExitCode)"
}
$compiler = Join-Path $portableRoot "ISCC.exe"
$compilerHash = (Get-FileHash -LiteralPath $compiler -Algorithm SHA256).Hash.ToLowerInvariant()
if ($compilerHash -ne "0a8757031b33777e4c9cbffee40f11a5062b36d25cbe144c1db73b6102b80ad7") {
    throw "Extracted compiler integrity check failed"
}
if (@(Get-ChildItem -LiteralPath $portableRoot -Filter "unins*").Count -ne 0) {
    throw "Compiler extraction unexpectedly enabled an installed uninstaller"
}
$inventory = @(Get-ChildItem -LiteralPath $portableRoot -File -Recurse | ForEach-Object {
    [ordered]@{
        path = [IO.Path]::GetRelativePath($portableRoot, $_.FullName)
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
})
[ordered]@{
    version = "6.7.3"
    url = $url
    installer_sha256 = $actual
    signature = $signature.Status.ToString()
    signer = $signature.SignerCertificate.Subject
    compiler_sha256 = $compilerHash
    inventory = $inventory
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $toolRoot "compiler-verification.json") -Encoding utf8
Write-Output $compiler
