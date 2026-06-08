param(
  [switch]$SkipDefenderScan
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root
$python = Join-Path $root ".venv-build\Scripts\python.exe"
$archiveViewer = Join-Path $root ".venv-build\Scripts\pyi-archive_viewer.exe"
$buildScript = Join-Path $root "build_exe.ps1"
$distExe = Join-Path $root "dist\WeChatChatSummarizer.exe"

if (-not (Test-Path $python)) {
  throw "Build Python was not found: $python"
}

$version = (& $python -c "from wxchat_app.version import APP_VERSION; print(APP_VERSION)").Trim()
if ($version -ne "0.9.0") {
  throw "Unexpected release version: $version"
}

$releaseRoot = [System.IO.Path]::GetFullPath((Join-Path $root "release"))
$packageName = "WeChatChatSummarizer-$version-win64"
$packageDir = [System.IO.Path]::GetFullPath((Join-Path $releaseRoot $packageName))
$zipPath = [System.IO.Path]::GetFullPath((Join-Path $releaseRoot "$packageName.zip"))

if (-not $packageDir.StartsWith($releaseRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Unsafe release package path: $packageDir"
}

Write-Host "Running unit tests..."
& $python -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw "Unit tests failed." }

$compileFiles = @(
  "wxchat_desktop.py",
  "wxchat_summarizer.py",
  "wxchat_webapp.py",
  "wechat_cli_bridge.py",
  "wxchat_app\__init__.py",
  "wxchat_app\version.py",
  "wxchat_app\settings.py",
  "wxchat_app\desktop.py",
  "wxchat_app\service.py",
  "wxchat_app\summarizer.py",
  "wxchat_app\webapp.py",
  "wxchat_app\wechat_cli_bridge.py",
  "wxchat_app\cli.py"
)
Write-Host "Running syntax checks..."
& $python -m py_compile @compileFiles
if ($LASTEXITCODE -ne 0) { throw "Syntax checks failed." }

Write-Host "Building Windows executable..."
& powershell -ExecutionPolicy Bypass -File $buildScript
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $distExe)) {
  throw "EXE build failed."
}

$versionInfo = (Get-Item $distExe).VersionInfo
if (-not $versionInfo.FileVersion.StartsWith($version)) {
  throw "EXE FileVersion mismatch: $($versionInfo.FileVersion)"
}
if (-not $versionInfo.ProductVersion.StartsWith($version)) {
  throw "EXE ProductVersion mismatch: $($versionInfo.ProductVersion)"
}
if ($versionInfo.ProductName -ne "微信聊天摘要工具") {
  throw "EXE ProductName mismatch: $($versionInfo.ProductName)"
}

$exeBytes = [System.IO.File]::ReadAllBytes($distExe)
$peOffset = [BitConverter]::ToInt32($exeBytes, 0x3C)
$subsystem = [BitConverter]::ToUInt16($exeBytes, $peOffset + 24 + 68)
if ($subsystem -ne 2) {
  throw "EXE is not a Windows GUI subsystem binary: $subsystem"
}

$archiveList = & $archiveViewer -l $distExe
foreach ($runtime in @("sqlite3.dll", "tcl86t.dll", "tk86t.dll")) {
  if (-not ($archiveList | Select-String -SimpleMatch $runtime)) {
    throw "Required runtime is missing from EXE: $runtime"
  }
}

if (Test-Path $packageDir) {
  Remove-Item -LiteralPath $packageDir -Recurse -Force
}
if (Test-Path $zipPath) {
  Remove-Item -LiteralPath $zipPath -Force
}
New-Item -ItemType Directory -Force -Path $packageDir | Out-Null

Copy-Item -LiteralPath $distExe -Destination (Join-Path $packageDir "WeChatChatSummarizer.exe")
Copy-Item -LiteralPath (Join-Path $root "release_docs\快速开始.txt") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $root "release_docs\README.md") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $root "release_docs\隐私与风险说明.md") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $root "release_docs\第三方组件说明.md") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $root "release_docs\RELEASE_NOTES.md") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $root "LICENSE") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $root "sample_chat.txt") -Destination $packageDir

$hashTargets = Get-ChildItem -LiteralPath $packageDir -File | Sort-Object Name
$hashLines = foreach ($file in $hashTargets) {
  $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
  "$hash  $($file.Name)"
}
[System.IO.File]::WriteAllLines(
  (Join-Path $packageDir "SHA256SUMS.txt"),
  $hashLines,
  [System.Text.UTF8Encoding]::new($false)
)

$allowedFiles = @(
  "WeChatChatSummarizer.exe",
  "快速开始.txt",
  "README.md",
  "隐私与风险说明.md",
  "第三方组件说明.md",
  "RELEASE_NOTES.md",
  "LICENSE",
  "sample_chat.txt",
  "SHA256SUMS.txt"
)
$actualFiles = @(Get-ChildItem -LiteralPath $packageDir -File | Select-Object -ExpandProperty Name)
$unexpected = @($actualFiles | Where-Object { $_ -notin $allowedFiles })
$missing = @($allowedFiles | Where-Object { $_ -notin $actualFiles })
if ($unexpected.Count -or $missing.Count) {
  throw "Release whitelist mismatch. Unexpected: $($unexpected -join ', '); Missing: $($missing -join ', ')"
}

$textFiles = Get-ChildItem -LiteralPath $packageDir -File | Where-Object { $_.Extension -in @(".md", ".txt") }
$forbiddenPatterns = @(
  "C:\\Users\\",
  "D:\\",
  "sk-[A-Za-z0-9_-]{8,}",
  "NEXT_CHAT_HANDOFF",
  "\.venv-build",
  "__pycache__"
)
foreach ($pattern in $forbiddenPatterns) {
  $matches = $textFiles | Select-String -Pattern $pattern
  if ($matches) {
    throw "Forbidden release content matched '$pattern': $($matches.Path -join ', ')"
  }
}

$signature = Get-AuthenticodeSignature -LiteralPath $distExe
if ($signature.Status -ne "NotSigned") {
  Write-Warning "Expected an unsigned trial build, but signature status is $($signature.Status)."
}

if (-not $SkipDefenderScan) {
  if (-not (Get-Command Start-MpScan -ErrorAction SilentlyContinue)) {
    throw "Windows Defender scan command is unavailable."
  }
  Write-Host "Running Windows Defender custom scan..."
  Start-MpScan -ScanType CustomScan -ScanPath $distExe
}

Compress-Archive -Path (Join-Path $packageDir "*") -DestinationPath $zipPath -Force

$verifyDir = Join-Path $env:TEMP "wechat-summarizer-release-verify-$([Guid]::NewGuid().ToString('N'))"
try {
  Expand-Archive -LiteralPath $zipPath -DestinationPath $verifyDir -Force
  $expectedHash = (Get-FileHash -LiteralPath (Join-Path $packageDir "WeChatChatSummarizer.exe") -Algorithm SHA256).Hash
  $actualHash = (Get-FileHash -LiteralPath (Join-Path $verifyDir "WeChatChatSummarizer.exe") -Algorithm SHA256).Hash
  if ($expectedHash -ne $actualHash) {
    throw "ZIP verification failed: EXE hash mismatch."
  }
  $verifiedFiles = @(Get-ChildItem -LiteralPath $verifyDir -File | Select-Object -ExpandProperty Name)
  if (@($verifiedFiles | Where-Object { $_ -notin $allowedFiles }).Count -or
      @($allowedFiles | Where-Object { $_ -notin $verifiedFiles }).Count) {
    throw "ZIP verification failed: file whitelist mismatch."
  }
} finally {
  if (Test-Path $verifyDir) {
    Remove-Item -LiteralPath $verifyDir -Recurse -Force
  }
}

$exeHash = (Get-FileHash -LiteralPath $distExe -Algorithm SHA256).Hash.ToLowerInvariant()
$zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host ""
Write-Host "Release created successfully:"
Write-Host "  Directory: $packageDir"
Write-Host "  ZIP:       $zipPath"
Write-Host "  EXE SHA256: $exeHash"
Write-Host "  ZIP SHA256: $zipHash"
