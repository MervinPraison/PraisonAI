# Run once so SlackApproval / TelegramApproval / DiscordApproval are available.
# Then: python slack_approval.py
$praisonaiPkg = (Resolve-Path (Join-Path $PSScriptRoot "..\..\src\praisonai")).Path
pip install -e $praisonaiPkg
