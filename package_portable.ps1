$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$dist = [System.IO.Path]::GetFullPath((Join-Path $root "dist"))
$package = [System.IO.Path]::GetFullPath((Join-Path $dist "WeChatChatSummarizerPortable"))
$packageApp = Join-Path $package "wxchat_app"

if (-not $package.StartsWith($dist, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Unsafe portable package path: $package"
}
if (Test-Path $package) {
  Remove-Item -LiteralPath $package -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $package | Out-Null

Copy-Item -Force (Join-Path $root "wxchat_summarizer.py") $package
Copy-Item -Force (Join-Path $root "wechat_cli_bridge.py") $package
Copy-Item -Force (Join-Path $root "wxchat_desktop.py") $package
Copy-Item -Recurse -Force (Join-Path $root "wxchat_app") $package
Get-ChildItem -Path $packageApp -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Copy-Item -Force (Join-Path $root "run_app.bat") $package
Copy-Item -Force (Join-Path $root "README.md") $package
Copy-Item -Force (Join-Path $root "LICENSE") $package
Copy-Item -Force (Join-Path $root "sample_chat.txt") $package

$zip = Join-Path $dist "WeChatChatSummarizerPortable.zip"
Compress-Archive -Path (Join-Path $package "*") -DestinationPath $zip -Force
Write-Host "Portable package created: $zip"
