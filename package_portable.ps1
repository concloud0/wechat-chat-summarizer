$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$dist = Join-Path $root "dist"
$package = Join-Path $dist "WeChatChatSummarizerPortable"
$packageApp = Join-Path $package "wxchat_app"

New-Item -ItemType Directory -Force -Path $package | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $package "web") | Out-Null
if (Test-Path $packageApp) {
  Remove-Item -Recurse -Force $packageApp
}

Copy-Item -Force (Join-Path $root "wxchat_summarizer.py") $package
Copy-Item -Force (Join-Path $root "wxchat_webapp.py") $package
Copy-Item -Force (Join-Path $root "wechat_cli_bridge.py") $package
Copy-Item -Force (Join-Path $root "wxchat_desktop.py") $package
Copy-Item -Recurse -Force (Join-Path $root "wxchat_app") $package
Get-ChildItem -Path $packageApp -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Copy-Item -Force (Join-Path $root "run_app.bat") $package
Copy-Item -Force (Join-Path $root "README.md") $package
Copy-Item -Force (Join-Path $root "LICENSE") $package
Copy-Item -Force (Join-Path $root "sample_chat.txt") $package
Copy-Item -Force (Join-Path $root "web\index.html") (Join-Path $package "web")
Copy-Item -Force (Join-Path $root "web\styles.css") (Join-Path $package "web")
Copy-Item -Force (Join-Path $root "web\app.js") (Join-Path $package "web")

$zip = Join-Path $dist "WeChatChatSummarizerPortable.zip"
Compress-Archive -Path (Join-Path $package "*") -DestinationPath $zip -Force
Write-Host "Portable package created: $zip"
