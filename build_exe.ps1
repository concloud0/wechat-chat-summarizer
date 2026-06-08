param(
  [string]$PythonExe = "",
  [string]$PipIndexUrl = "https://pypi.tuna.tsinghua.edu.cn/simple"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $root ".venv-build"
$python = Join-Path $venv "Scripts\python.exe"
$pyinstaller = Join-Path $venv "Scripts\pyinstaller.exe"
$assetScript = Join-Path $root "scripts\generate_release_assets.ps1"
$iconPath = Join-Path $root "assets\WeChatChatSummarizer.ico"
$versionFile = Join-Path $root "build_version_info.txt"

if (-not $PythonExe) {
  $anacondaPython = Join-Path $env:USERPROFILE "anaconda3\python.exe"
  if (Test-Path $anacondaPython) {
    $PythonExe = $anacondaPython
  } else {
    $PythonExe = "python"
  }
}

if (-not (Test-Path $python)) {
  & $PythonExe -m venv $venv
}

if (-not (Test-Path $pyinstaller)) {
  & $python -m pip install --disable-pip-version-check --no-input --upgrade pip -i $PipIndexUrl --trusted-host "pypi.tuna.tsinghua.edu.cn"
  & $python -m pip install --disable-pip-version-check --no-input pyinstaller -i $PipIndexUrl --trusted-host "pypi.tuna.tsinghua.edu.cn"
}

& powershell -ExecutionPolicy Bypass -File $assetScript -OutputPath $iconPath

$pythonBase = (& $python -c "import sys; print(sys.base_prefix)").Trim()
$pythonLibraryBin = Join-Path $pythonBase "Library\bin"
$requiredRuntimeDlls = @(
  (Join-Path $pythonLibraryBin "sqlite3.dll")
  (Join-Path $pythonLibraryBin "tcl86t.dll")
  (Join-Path $pythonLibraryBin "tk86t.dll")
)
$pyinstallerArgs = @(
  "--noconfirm"
  "--onefile"
  "--windowed"
  "--icon"
  $iconPath
  "--version-file"
  $versionFile
  "--add-data"
  "$iconPath;assets"
  "--name"
  "WeChatChatSummarizer"
)

# Prefer the DLLs matching this Conda Python. Without this, dependency
# resolution can select an incompatible Tcl DLL from another PATH entry.
$env:PATH = "$pythonLibraryBin;$env:PATH"
foreach ($runtimeDll in $requiredRuntimeDlls) {
  if (Test-Path $runtimeDll) {
    $pyinstallerArgs += @("--add-binary", "$runtimeDll;.")
  } else {
    Write-Warning "Required runtime DLL was not found: $runtimeDll"
  }
}

$pyinstallerArgs += "wxchat_desktop.py"
& $pyinstaller @pyinstallerArgs

Write-Host "EXE created: $(Join-Path $root 'dist\WeChatChatSummarizer.exe')"
