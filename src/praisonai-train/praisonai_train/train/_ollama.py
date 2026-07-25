"""Shared Ollama daemon management utilities.

This module provides utilities to start and check Ollama daemon status,
fixing the blocking subprocess.run(["ollama", "serve"]) issue present
in multiple files.
"""
import contextlib
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from typing import Optional


def _ollama_ready(host: str = "127.0.0.1", port: int = 11434, timeout: float = 0.2) -> bool:
    """Check if Ollama daemon is accepting connections AND serving its HTTP API.

    A bare socket connect can succeed before the HTTP server is actually ready
    (or when something unrelated holds the port), so we confirm with a real
    ``GET /api/version`` before declaring the daemon usable.

    Args:
        host: Ollama host (default 127.0.0.1)
        port: Ollama port (default 11434)
        timeout: Connection timeout in seconds

    Returns:
        True if Ollama's API responds, False otherwise
    """
    # Fast socket pre-check: if the port isn't even open, skip the HTTP attempt.
    try:
        with socket.create_connection((host, port), timeout):
            pass
    except OSError:
        return False
    url = f"http://{host}:{port}/api/version"
    try:
        with urllib.request.urlopen(url, timeout=max(timeout, 1.0)) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except (urllib.error.URLError, OSError):
        return False


def ensure_ollama_running(max_wait_seconds: float = 15.0) -> Optional[subprocess.Popen]:
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

    # Capture serve stderr to a temp file so a startup failure (e.g. port in use,
    # bad OLLAMA_HOST) can be surfaced in the timeout message instead of vanishing.
    serve_err = tempfile.TemporaryFile(mode="w+")
    proc = subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=serve_err,
        start_new_session=True,  # Detach from parent
    )

    # Poll until ready or timeout
    wait_interval = 0.25
    max_polls = max(1, int(max_wait_seconds / wait_interval))

    for _ in range(max_polls):
        if _ollama_ready():
            return proc
        time.sleep(wait_interval)

    # If we get here, daemon didn't become ready in time — include serve's stderr.
    proc.terminate()
    err_text = ""
    with contextlib.suppress(OSError, ValueError):
        serve_err.seek(0)
        err_text = serve_err.read().strip()
    detail = f"\nollama serve output:\n{err_text}" if err_text else ""
    raise RuntimeError(
        f"ollama serve did not become ready in {max_wait_seconds} seconds.{detail}"
    )


def _ollama_models_dir() -> str:
    """Directory Ollama stores models in (OLLAMA_MODELS or ~/.ollama/models)."""
    return os.environ.get(
        "OLLAMA_MODELS", os.path.join(os.path.expanduser("~"), ".ollama", "models")
    )


def _dir_size_bytes(path: str) -> int:
    """Best-effort total size of a file or directory tree, in bytes (0 if absent)."""
    if os.path.isfile(path):
        with contextlib.suppress(OSError):
            return os.path.getsize(path)
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            with contextlib.suppress(OSError):
                total += os.path.getsize(os.path.join(root, name))
    return total


def _source_model_path(modelfile_content: str) -> Optional[str]:
    """Extract the local FROM path from a Modelfile, if it points to a real path."""
    for line in modelfile_content.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("FROM "):
            candidate = stripped[5:].strip().strip('"')
            if os.path.exists(candidate):
                return candidate
            return None
    return None


def _check_ollama_disk(modelfile_content: str) -> None:
    """Fail fast if the Ollama models volume lacks room for the created model.

    Requires ~1.5x the source model size, with a 15GB floor when the size is
    unknown (e.g. FROM references a Hub id rather than a local path).
    """
    models_dir = _ollama_models_dir()
    # disk_usage needs an existing path; walk up to the nearest existing parent.
    probe = models_dir
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    if not probe or not os.path.exists(probe):
        return  # Can't determine the volume; skip rather than block.
    try:
        free = shutil.disk_usage(probe).free
    except OSError:
        return
    floor = 15 * 2 ** 30
    src = _source_model_path(modelfile_content)
    src_size = _dir_size_bytes(src) if src else 0
    required = max(floor, int(src_size * 1.5))
    if free < required:
        raise RuntimeError(
            f"Not enough disk for the Ollama model: {free / 2 ** 30:.1f} GB free on "
            f"'{models_dir}', need ~{required / 2 ** 30:.1f} GB. Point Ollama at a "
            f"bigger disk, e.g. `export OLLAMA_MODELS=/big/disk/ollama-models`."
        )


def _ollama_key_hint() -> str:
    """Message telling the user how to register their Ollama signing key to push."""
    pub_path = os.path.join(os.path.expanduser("~"), ".ollama", "id_ed25519.pub")
    key_line = ""
    with contextlib.suppress(OSError):
        with open(pub_path) as f:
            key_line = f"\nYour public key ({pub_path}):\n{f.read().strip()}"
    return (
        "Ollama rejected the push (unauthorized). Register your public key at "
        "https://ollama.com/settings/keys and make sure the model is namespaced as "
        "`<username>/<name>`." + key_line
    )


def create_and_push_ollama_model(
    ollama_model: str,
    model_parameters: str,
    modelfile_content: str,
    quantization: Optional[str] = None,
) -> None:
    """Create and push an Ollama model with proper daemon management.

    Args:
        ollama_model: Name of the Ollama model
        model_parameters: Model parameters/tag
        modelfile_content: Content for the Modelfile
        quantization: Optional quantization (e.g. "q4_k_m") passed to
            ``ollama create --quantize`` so the model isn't stored as huge f16.

    Raises:
        RuntimeError: If ollama operations fail (with actionable guidance)
        subprocess.CalledProcessError: If the create command fails
    """
    # Write Modelfile
    with open("Modelfile", "w") as f:
        f.write(modelfile_content)

    # Disk pre-check BEFORE we start the daemon / create, so we fail with clear
    # guidance instead of a cryptic "no space left on device" mid-create.
    _check_ollama_disk(modelfile_content)

    # Ensure daemon is running
    ensure_ollama_running()

    # Create and push model
    tag = f"{ollama_model}:{model_parameters}"

    create_cmd = ["ollama", "create", tag, "-f", "Modelfile"]
    if quantization:
        create_cmd += ["--quantize", quantization]
    subprocess.run(create_cmd, check=True)

    # Push with captured output so a 401/403 becomes an actionable message rather
    # than a raw non-zero exit.
    result = subprocess.run(["ollama", "push", tag], capture_output=True, text=True)
    if result.returncode != 0:
        combined = f"{result.stderr or ''}\n{result.stdout or ''}".lower()
        if any(t in combined for t in ("unauthorized", "401", "403", "forbidden", "invalid key")):
            raise RuntimeError(_ollama_key_hint())
        raise RuntimeError(
            f"`ollama push {tag}` failed:\n{(result.stderr or result.stdout or '').strip()}"
        )
