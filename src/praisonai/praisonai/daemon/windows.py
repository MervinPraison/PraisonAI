"""
Windows service management for PraisonAI bots.

Uses Scheduled Task for per-user on-login start.
Falls back to Startup folder shortcut if the user's account lacks privileges.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from typing import Any, Dict

logger = logging.getLogger(__name__)

TASK_NAME = "PraisonAIGateway"


def _python_executable() -> str:
    """Get the Python executable path."""
    return shutil.which("python3") or shutil.which("python") or sys.executable


def _startup_folder() -> str:
    """Get the Windows startup folder path."""
    return os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")


def _startup_script_path() -> str:
    """Get the startup script path."""
    return os.path.join(_startup_folder(), f"{TASK_NAME}.cmd")


def _generate_startup_script(config_path: str) -> str:
    """Generate a startup script for the bot."""
    python = _python_executable()
    abs_config = os.path.abspath(config_path)
    
    return f"""@echo off
REM PraisonAI Bot Startup Script
cd /d "{os.path.dirname(abs_config)}"
"{python}" -m praisonai bot start --config "{abs_config}"
"""


def _create_scheduled_task(config_path: str) -> Dict[str, Any]:
    """Create a Windows Scheduled Task for the bot."""
    python = _python_executable()
    abs_config = os.path.abspath(config_path)
    # list2cmdline ensures Windows-safe escaping for command args (including config path).
    task_command = subprocess.list2cmdline(
        [python, "-m", "praisonai", "bot", "start", "--config", abs_config]
    )
    
    # Build schtasks command
    cmd = [
        "schtasks", "/Create",
        "/TN", TASK_NAME,
        "/SC", "ONLOGON",
        "/TR", task_command,
        "/RL", "LIMITED",
        "/F"  # Force overwrite if exists
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Scheduled task created: {result.stdout}")
        return {"ok": True, "message": f"Scheduled task '{TASK_NAME}' created successfully"}
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create scheduled task: {e.stderr}")
        return {"ok": False, "error": f"schtasks failed: {e.stderr.strip()}"}
    except Exception as e:
        logger.error(f"Unexpected error creating scheduled task: {e}")
        return {"ok": False, "error": str(e)}


def _create_startup_folder_entry(config_path: str) -> Dict[str, Any]:
    """Create a startup folder entry as fallback."""
    try:
        startup_folder = _startup_folder()
        os.makedirs(startup_folder, exist_ok=True)
        
        script_content = _generate_startup_script(config_path)
        script_path = _startup_script_path()
        
        with open(script_path, "w") as f:
            f.write(script_content)
        
        logger.info(f"Startup script created: {script_path}")
        return {"ok": True, "message": f"Startup script created at {script_path}"}
    except Exception as e:
        logger.error(f"Failed to create startup script: {e}")
        return {"ok": False, "error": str(e)}


def install(config_path: str = "bot.yaml", **kwargs: Any) -> Dict[str, Any]:
    """Install the bot as a Windows service/startup item."""
    # Try Scheduled Task first (more robust)
    task_result = _create_scheduled_task(config_path)
    if task_result["ok"]:
        return task_result
    
    # Fall back to Startup folder
    logger.warning("Scheduled task creation failed, trying startup folder")
    startup_result = _create_startup_folder_entry(config_path)
    
    if startup_result["ok"]:
        startup_result["message"] += " (fallback method - starts on next login)"
        return startup_result
    
    # Both methods failed
    return {
        "ok": False,
        "error": f"Both methods failed. Task: {task_result['error']}. Startup: {startup_result['error']}"
    }


def uninstall() -> Dict[str, Any]:
    """Uninstall the Windows service/startup item."""
    results = []
    success_count = 0
    
    # Try to remove scheduled task
    try:
        cmd = ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        results.append(f"Scheduled task removed: {result.stdout.strip()}")
        success_count += 1
    except subprocess.CalledProcessError as e:
        if "cannot find the file" in e.stderr.lower() or "does not exist" in e.stderr.lower():
            results.append("Scheduled task was not installed")
        else:
            results.append(f"Failed to remove scheduled task: {e.stderr.strip()}")
    except Exception as e:
        results.append(f"Error removing scheduled task: {str(e)}")
    
    # Try to remove startup script
    try:
        script_path = _startup_script_path()
        if os.path.exists(script_path):
            os.remove(script_path)
            results.append(f"Startup script removed: {script_path}")
            success_count += 1
        else:
            results.append("Startup script was not installed")
    except Exception as e:
        results.append(f"Error removing startup script: {str(e)}")
    
    if success_count > 0:
        return {"ok": True, "message": "; ".join(results)}
    else:
        return {"ok": False, "error": "Nothing to uninstall or all operations failed: " + "; ".join(results)}


def get_status() -> Dict[str, Any]:
    """Get the status of the Windows service/startup item."""
    status = {
        "installed": False,
        "running": False,
        "platform": "windows",
        "methods": []
    }
    
    # Check scheduled task
    try:
        cmd = ["schtasks", "/Query", "/TN", TASK_NAME]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if TASK_NAME in result.stdout:
            status["installed"] = True
            status["methods"].append("scheduled_task")
    except subprocess.CalledProcessError:
        # Task doesn't exist
        pass
    except Exception as e:
        status["error"] = f"Error checking scheduled task: {str(e)}"
    
    # Check startup script
    script_path = _startup_script_path()
    if os.path.exists(script_path):
        status["installed"] = True
        status["methods"].append("startup_script")
    
    # Check if bot process is running (simplified check)
    try:
        # Look for praisonai bot processes
        cmd = ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if "praisonai bot" in result.stdout or "praisonai.exe" in result.stdout:
            status["running"] = True
    except Exception:
        # Can't determine if running
        pass
    
    return status


def get_logs(lines: int = 50) -> str:
    """Get logs for the Windows service (limited functionality)."""
    # Windows doesn't have a unified log system like systemd/launchd
    # This is a placeholder for future implementation
    return f"Log viewing not yet implemented for Windows. Check Event Viewer for system logs."
