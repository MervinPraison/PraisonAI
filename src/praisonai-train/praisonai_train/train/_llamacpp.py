"""llama.cpp launch / benchmark helpers for MTP fast inference.

Modelled on ``_ollama.py``: guard on the binary with a clean install message,
run subprocesses with captured output translated into friendly errors, and spawn
long-running servers detached with a health-poll instead of blocking.

MTP (Multi-Token Prediction) speculative decoding is enabled by passing a stock
drafter via ``--model-draft <drafter.gguf> --spec-type draft-mtp
--spec-draft-n-max N`` to mainline llama.cpp.
"""
from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional

_INSTALL_HINT = (
    "llama.cpp binary not found. Build it (https://github.com/ggml-org/llama.cpp — "
    "`cmake -B build && cmake --build build`) or download a release, then either add "
    "it to your PATH or set LLAMA_CPP_BIN to the binary (or the directory containing it)."
)


def find_llama_binary(name: str = "llama-server") -> str:
    """Locate a llama.cpp binary (``llama-server`` / ``llama-cli``).

    Resolution order:
      1. ``LLAMA_CPP_BIN`` env — may point at the binary itself or a directory
         containing it.
      2. ``shutil.which(name)`` on PATH.

    Raises:
        RuntimeError: with install guidance if the binary can't be found.
    """
    env = os.environ.get("LLAMA_CPP_BIN")
    if env:
        p = Path(env)
        if p.is_dir():
            candidate = p / name
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate)
        elif p.exists() and os.access(p, os.X_OK):
            # A file was given. Honour it only when it *is* the requested binary,
            # otherwise prefer the correctly-named sibling in the same directory.
            # Never return a differently-named executable — launching e.g.
            # llama-cli with server flags (or vice-versa) fails cryptically.
            if p.name == name:
                return str(p)
            sibling = p.parent / name
            if sibling.exists() and os.access(sibling, os.X_OK):
                return str(sibling)

    found = shutil.which(name)
    if found:
        return found

    raise RuntimeError(_INSTALL_HINT)


def build_mtp_cmd(
    binary: str,
    model_gguf: str | Path,
    draft_gguf: Optional[str | Path] = None,
    spec_draft_n_max: int = 2,
    extra: Optional[List[str]] = None,
    server: bool = True,
    port: int = 8080,
    ngl: int = 99,
) -> List[str]:
    """Assemble a llama.cpp argument list (pure — no side effects).

    When ``draft_gguf`` is provided the MTP speculative-decoding flags
    (``--model-draft``, ``--spec-type draft-mtp``, ``--spec-draft-n-max``) are
    included. Always includes ``--model`` and ``-ngl``; for a server the
    ``--port`` is added too.
    """
    cmd: List[str] = [str(binary), "--model", str(model_gguf), "-ngl", str(ngl)]
    if draft_gguf:
        cmd += [
            "--model-draft", str(draft_gguf),
            "--spec-type", "draft-mtp",
            "--spec-draft-n-max", str(spec_draft_n_max),
        ]
    if server:
        cmd += ["--port", str(port)]
    if extra:
        cmd += list(extra)
    return cmd


def _server_ready(port: int, timeout: float = 1.0) -> bool:
    """True once llama-server answers its health endpoint on ``port``."""
    for path in ("/health", "/v1/models"):
        url = f"http://127.0.0.1:{port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                if 200 <= getattr(resp, "status", 200) < 300:
                    return True
        except urllib.error.HTTPError as exc:
            # /v1/models may 401/400 without a key but still proves it's up.
            if exc.code in (400, 401, 403):
                return True
        except (urllib.error.URLError, OSError):
            continue
    return False


def serve(
    model_gguf: str | Path,
    draft_gguf: Optional[str | Path] = None,
    spec_draft_n_max: int = 2,
    port: int = 8080,
    ngl: int = 99,
    wait: bool = True,
    max_wait_seconds: float = 60.0,
) -> subprocess.Popen:
    """Launch ``llama-server`` (optionally with an MTP drafter) detached.

    Health-polls ``http://127.0.0.1:<port>/health`` for up to ``max_wait_seconds``,
    prints the OpenAI-compatible endpoint, and returns the Popen handle.

    Raises:
        RuntimeError: with captured server output if it doesn't come up.
    """
    binary = find_llama_binary("llama-server")
    cmd = build_mtp_cmd(
        binary, model_gguf, draft_gguf=draft_gguf,
        spec_draft_n_max=spec_draft_n_max, server=True, port=port, ngl=ngl,
    )

    serve_err = tempfile.TemporaryFile(mode="w+")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=serve_err,
        start_new_session=True,
    )

    if not wait:
        return proc

    wait_interval = 0.5
    max_polls = max(1, int(max_wait_seconds / wait_interval))
    for _ in range(max_polls):
        if proc.poll() is not None:
            break  # process exited early — surface its output below
        if _server_ready(port):
            mtp = " (MTP speculative decoding ON)" if draft_gguf else ""
            print(
                f"llama-server ready{mtp} — OpenAI-compatible endpoint: "
                f"http://127.0.0.1:{port}/v1"
            )
            return proc
        time.sleep(wait_interval)

    # Failed to become ready — terminate and surface stderr.
    with contextlib.suppress(OSError, ValueError):
        proc.terminate()
    err_text = ""
    with contextlib.suppress(OSError, ValueError):
        serve_err.seek(0)
        err_text = serve_err.read().strip()
    detail = f"\nllama-server output:\n{err_text}" if err_text else ""
    raise RuntimeError(
        f"llama-server did not become ready on port {port} in "
        f"{max_wait_seconds:.0f}s.{detail}"
    )


def parse_llama_timings(text: str) -> dict:
    """Parse tokens/sec and draft acceptance from llama.cpp stderr/stdout.

    llama.cpp prints lines like::

        llama_perf_context_print:  eval time =  1234.56 ms /   256 runs   (  4.82 ms per token,   207.45 tokens per second)

    and, with speculative decoding, draft acceptance stats such as
    ``n_accept = 812`` / ``accept = 78.4%``.

    Returns a dict with ``tokens_per_sec`` (float | None), ``n_predict``
    (int | None) and ``accept_rate`` (float | None, as a 0..1 fraction).
    """
    result: dict = {"tokens_per_sec": None, "n_predict": None, "accept_rate": None}

    # tokens/sec — take the LAST "eval" match (generation, not prompt eval).
    tps_matches = re.findall(r"([\d.]+)\s*tokens per second", text)
    if tps_matches:
        try:
            result["tokens_per_sec"] = float(tps_matches[-1])
        except ValueError:
            pass

    # n_predict / number of generated tokens — "/  256 runs" on the eval line.
    runs = re.findall(r"/\s*(\d+)\s*runs", text)
    if runs:
        try:
            result["n_predict"] = int(runs[-1])
        except ValueError:
            pass

    # draft acceptance rate — either an explicit percentage or n_accept/n_drafted.
    pct = re.search(r"accept(?:ance)?\s*(?:rate)?\s*[=:]\s*([\d.]+)\s*%", text, re.I)
    if pct:
        try:
            result["accept_rate"] = float(pct.group(1)) / 100.0
        except ValueError:
            pass
    else:
        n_accept = re.search(r"n_accept\s*[=:]\s*(\d+)", text, re.I)
        n_drafted = re.search(r"n_draft(?:ed)?\s*[=:]\s*(\d+)", text, re.I)
        if n_accept and n_drafted:
            try:
                acc = int(n_accept.group(1))
                drafted = int(n_drafted.group(1))
                if drafted > 0:
                    result["accept_rate"] = acc / drafted
            except ValueError:
                pass

    return result


def benchmark(
    model_gguf: str | Path,
    draft_gguf: Optional[str | Path] = None,
    spec_draft_n_max: int = 2,
    prompt: Optional[str] = None,
    n_predict: int = 256,
    ngl: int = 99,
) -> dict:
    """Run ``llama-cli`` once and report throughput (and MTP acceptance).

    Returns ``{"tokens_per_sec": float, "n_predict": int, "accept_rate":
    float|None, "mtp": bool}``.

    Raises:
        RuntimeError: with captured output if llama-cli fails.
    """
    binary = find_llama_binary("llama-cli")
    prompt = prompt or "Explain multi-token prediction in one paragraph."
    cmd = build_mtp_cmd(
        binary, model_gguf, draft_gguf=draft_gguf,
        spec_draft_n_max=spec_draft_n_max, server=False, ngl=ngl,
        extra=["--prompt", prompt, "-n", str(n_predict), "--no-conversation"],
    )

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"llama-cli benchmark failed:\n{detail}")

    # llama.cpp writes timings to stderr; parse both streams to be safe.
    parsed = parse_llama_timings(f"{proc.stderr}\n{proc.stdout}")
    return {
        "tokens_per_sec": parsed["tokens_per_sec"],
        "n_predict": parsed["n_predict"] if parsed["n_predict"] is not None else n_predict,
        "accept_rate": parsed["accept_rate"],
        "mtp": bool(draft_gguf),
    }
