# PraisonAI Desktop — correct way to open the real UI (sidebar, Chat, Knowledge, Channels).
# Do NOT double-click praisonai-desktop.exe from a Temp/cursor-sandbox cache folder;
# that often shows Edge "127.0.0.1 refused to connect" instead of the app.

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $here "src-tauri")

Write-Host "Starting PraisonAI Desktop (Tauri dev). First compile can take 10–20 minutes." -ForegroundColor Cyan
Write-Host "When the window opens you should see the dark sidebar — not an Edge error page." -ForegroundColor Cyan
Write-Host ""

npx --yes @tauri-apps/cli@2 dev
