"""Shared Ollama daemon management utilities.

This module provides utilities to start and check Ollama daemon status,
fixing the blocking subprocess.run(["ollama", "serve"]) issue present
in multiple files.
"""
import contextlib
import shutil
import socket
import subprocess
import time
from typing import Optional


def _ollama_ready(host: str = "127.0.0.1", port: int = 11434, timeout: float = 0.2) -> bool:
    """Check if Ollama daemon is ready to accept connections.
    
    Args:
        host: Ollama host (default 127.0.0.1)
        port: Ollama port (default 11434)
        timeout: Connection timeout in seconds
        
    Returns:
        True if Ollama is ready, False otherwise
    """
    with contextlib.suppress(OSError):
        with socket.create_connection((host, port), timeout):
            return True
    return False


def ensure_ollama_running(max_wait_seconds: float = 5.0) -> Optional[subprocess.Popen]:
    """Ensure Ollama daemon is running, start it if necessary.
    
    Args:
        max_wait_seconds: Maximum time to wait for daemon to become ready
        
    Returns:
        Process object if we started the daemon, None if it was already running
        
    Raises:
        RuntimeError: If ollama CLI not found or daemon doesn't become ready
    """
    # Check if already running
    if _ollama_ready():
        return None
    
    # Check if ollama CLI is available
    if shutil.which("ollama") is None:
        raise RuntimeError("`ollama` CLI not found; install from https://ollama.com")
    
    # Start daemon in detached mode
    proc = subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # Detach from parent
    )
    
    # Poll until ready or timeout
    wait_interval = 0.1
    max_polls = int(max_wait_seconds / wait_interval)
    
    for _ in range(max_polls):
        if _ollama_ready():
            return proc
        time.sleep(wait_interval)
    
    # If we get here, daemon didn't become ready in time
    proc.terminate()
    raise RuntimeError(f"ollama serve did not become ready in {max_wait_seconds} seconds")


def create_and_push_ollama_model(ollama_model: str, model_parameters: str, modelfile_content: str) -> None:
    """Create and push an Ollama model with proper daemon management.
    
    Args:
        ollama_model: Name of the Ollama model
        model_parameters: Model parameters/tag
        modelfile_content: Content for the Modelfile
        
    Raises:
        RuntimeError: If ollama operations fail
        subprocess.CalledProcessError: If create/push commands fail
    """
    # Write Modelfile
    with open("Modelfile", "w") as f:
        f.write(modelfile_content)
    
    # Ensure daemon is running
    ensure_ollama_running()
    
    # Create and push model
    tag = f"{ollama_model}:{model_parameters}"
    
    subprocess.run(["ollama", "create", tag, "-f", "Modelfile"], check=True)
    subprocess.run(["ollama", "push", tag], check=True)