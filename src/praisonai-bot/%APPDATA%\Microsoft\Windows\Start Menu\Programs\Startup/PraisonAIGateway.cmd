@echo off
REM PraisonAI Bot Startup Script
cd /d "/Users/praison/praisonai-package-worktrees/kanban-hooks/src/praisonai-bot"
"/Users/praison/bin/python3" -m praisonai_bot gateway start --config "/Users/praison/praisonai-package-worktrees/kanban-hooks/src/praisonai-bot/bot.yaml"
REM Honour the gateway fatal-config exit code (78, EX_CONFIG): do NOT relaunch
REM on a fatally broken config, otherwise a bad edit crash-loops forever.
if "%ERRORLEVEL%"=="78" (
    echo PraisonAI gateway stopped: fatal config error 78. Fix the config and re-start.
    exit /b 0
)
