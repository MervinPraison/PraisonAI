"""Run the whole agent inside a container you own.

``run_on="anthropic"`` hands the entire agent -- model calls, loop and tools --
to someone else's managed runtime. This is the same shape, self-hosted: the
loop runs in a local container instead of a vendor's cloud.

The distinction from ``tools_run_on="docker"`` is what crosses the boundary:

* ``tools_run_on="docker"`` -- your Python process runs the loop and calls the
  model. Only shell and file tools are executed in the container. Your
  environment, your files and your API keys are all still in play locally.
* ``run_on="docker"`` -- the loop itself runs in the container. The model call
  is made from inside it, so the container needs the API key and nothing on
  your filesystem is reachable unless you mounted it.

Both are legitimate; they answer different questions, which is exactly why the
two parameters exist. The same word naming the same place under both is not an
ambiguity -- the parameter carries the scope.

Deliberate limitations, stated rather than hidden:

* **Python callables in ``tools=`` do not cross.** A function defined in your
  process cannot be reconstructed in the container, so it is not sent. This is
  the same limitation the hosted runtimes have; the agent is rebuilt inside
  from its serialisable configuration.
* **The container needs the model API key.** It is passed through from your
  environment. That is the point of moving the loop, and it is worth knowing.
* **First run installs the package** unless you supply an image that already
  has it, which costs roughly a minute. Pass ``image=`` to skip it.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Model API keys worth forwarding. Only ones actually set are passed, and they
# are written to a file inside the container rather than into the command line,
# so they never appear in `docker inspect` or a process listing.
_KEY_VARS = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "GROQ_API_KEY", "MISTRAL_API_KEY", "COHERE_API_KEY", "OPENROUTER_API_KEY",
    "DEEPSEEK_API_KEY", "XAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE",
)

_DEFAULT_IMAGE = "python:3.12-slim"

# The runner is written into the container and executed there. It rebuilds the
# agent from JSON and prints exactly one line of JSON back, so stdout noise
# (pip warnings, telemetry) cannot be mistaken for the answer.
_RUNNER = r'''
import json, sys, os

payload = json.load(open("/tmp/praison_agent.json"))
try:
    from praisonaiagents import Agent

    kwargs = {k: v for k, v in payload["agent"].items() if v is not None}
    agent = Agent(**kwargs)
    result = agent.start(payload["prompt"])
    out = {"ok": True, "result": result if isinstance(result, str) else str(result)}
except Exception as exc:                     # noqa: BLE001 - reported, not raised
    out = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

sys.stdout.write("\n__PRAISON_RESULT__" + json.dumps(out) + "\n")
'''

_MARKER = "__PRAISON_RESULT__"


class DockerManagedAgent:
    """A whole agent running in a container. Implements ManagedBackendProtocol.

    Args:
        config: agent configuration (instructions, llm, name, ...). Accepts a
            ``ManagedConfig``/``HostedAgentConfig``, a plain dict, or None.
        image: container image. Defaults to ``python:3.12-slim``, onto which
            praisonaiagents is installed on first use. Supply your own image
            with the package baked in to skip that.
        env: extra environment variables for the container.
        keep_alive: reuse one container across calls (default) so a follow-up
            turn does not pay start-up again.
    """

    def __init__(
        self,
        config: Optional[Any] = None,
        *,
        provider: Optional[str] = None,
        image: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        keep_alive: bool = True,
        pip_packages: Optional[List[str]] = None,
        **_ignored: Any,
    ):
        # `provider` arrives because HostedAgent(provider="docker") acts as a
        # factory and forwards it. It is already implied by this class, so it
        # is accepted and dropped rather than rejected.
        del provider
        self._config = _as_dict(config)
        self.image = image or _DEFAULT_IMAGE
        self._extra_env = dict(env or {})
        self._keep_alive = keep_alive
        self._pip_packages = list(pip_packages or ["praisonaiagents"])
        self._container: Optional[str] = None
        self._prepared = False

    # ── identity ─────────────────────────────────────────────────────────────
    @property
    def provider_name(self) -> str:
        return "docker"

    @property
    def is_available(self) -> bool:
        return _docker_ok()

    # ── ManagedBackendProtocol ───────────────────────────────────────────────
    async def execute(self, prompt: str, **kwargs) -> str:
        # Docker start-up, package install and the container turn are blocking
        # subprocess work. Run them off the event-loop thread so concurrent
        # async callers are not stalled behind one agent's container.
        import asyncio

        return await asyncio.to_thread(self._execute_sync, prompt, **kwargs)

    async def stream(self, prompt: str, **kwargs):
        """Yield the result once.

        The loop runs to completion inside the container, so there is no token
        stream to forward. Yielding the finished answer keeps callers that
        expect an iterator working, rather than pretending to stream.
        """
        import asyncio

        yield await asyncio.to_thread(self._execute_sync, prompt, **kwargs)

    def reset_session(self) -> None:
        """Drop the container; the next call starts a clean one."""
        self.shutdown()

    def reset_all(self) -> None:
        self.reset_session()

    # ── lifecycle ────────────────────────────────────────────────────────────
    def shutdown(self) -> None:
        if self._container:
            _run(["docker", "rm", "-f", self._container], check=False, timeout=120)
            logger.info("[docker_managed] removed container %s", self._container)
        self._container = None
        self._prepared = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.shutdown()

    # ── the work ─────────────────────────────────────────────────────────────
    def _execute_sync(self, prompt: str, **kwargs) -> str:
        self._ensure_container()
        # An ephemeral container must not outlive the call that made it, even
        # when the turn raises. Tear it down in `finally` so a failure after
        # start-up cannot leak a `praisonai-agent-*` container.
        try:
            payload = json.dumps({"agent": self._config, "prompt": prompt})

            _write_file(self._container, "/tmp/praison_agent.json", payload)
            _write_file(self._container, "/tmp/praison_runner.py", _RUNNER)

            result = _run(
                ["docker", "exec", self._container, "python", "/tmp/praison_runner.py"],
                timeout=kwargs.get("timeout", 900),
            )
            answer = _parse(result.stdout)
            if answer is None:
                detail = (result.stderr or result.stdout or "").strip()[-600:]
                raise RuntimeError(
                    f"The agent produced no result inside the container.\n{detail}"
                )
            if not answer.get("ok"):
                raise RuntimeError(
                    f"Agent failed inside the container: {answer['error']}"
                )
            return answer["result"]
        finally:
            if not self._keep_alive:
                self.shutdown()

    def _ensure_container(self) -> None:
        if self._container and self._prepared:
            return
        if not _docker_ok():
            raise RuntimeError(
                "run_on='docker' needs a running Docker daemon.\n"
                "  Start Docker Desktop, or check `docker info`.\n"
                "  To keep the loop on this machine and move only the tools, "
                "use tools_run_on='docker' instead."
            )

        name = f"praisonai-agent-{uuid.uuid4().hex[:12]}"
        env_args: List[str] = []
        for key in _KEY_VARS:
            if os.environ.get(key):
                env_args += ["-e", key]          # value comes from our env, not argv
        for key, value in self._extra_env.items():
            env_args += ["-e", f"{key}={value}"]

        _run([
            "docker", "run", "-d", "--name", name,
            "--label", "praisonai=managed",
            "--label", "praisonai.scope=whole-agent",
            *env_args, self.image, "sleep", "infinity",
        ], timeout=300)
        self._container = name
        logger.info("[docker_managed] started %s from %s", name, self.image)

        # Install only if the package is not already in the image.
        probe = _run(
            ["docker", "exec", name, "python", "-c", "import praisonaiagents"],
            check=False, timeout=120,
        )
        if probe.returncode != 0:
            logger.info("[docker_managed] installing %s (first run)", self._pip_packages)
            install = _run(
                ["docker", "exec", name, "pip", "install", "--no-cache-dir",
                 "-q", *self._pip_packages],
                check=False, timeout=900,
            )
            if install.returncode != 0:
                self.shutdown()
                raise RuntimeError(
                    "Could not install praisonaiagents in the container:\n"
                    + (install.stderr or "")[-600:]
                    + "\nSupply an image that already has it with image=..."
                )
        self._prepared = True


# ── helpers ──────────────────────────────────────────────────────────────────
def _as_dict(config: Any) -> Dict[str, Any]:
    """Normalise a config object into constructor kwargs for the remote Agent."""
    if config is None:
        return {"instructions": "You are a helpful assistant."}
    if isinstance(config, dict):
        raw = dict(config)
    else:
        raw = {
            k: v for k, v in vars(config).items()
            if not k.startswith("_")
        } if hasattr(config, "__dict__") else {}

    # Only fields an Agent can be rebuilt from, and only JSON-safe values.
    allowed = ("name", "role", "goal", "backstory", "instructions", "llm",
               "system", "model", "verbose", "markdown", "self_reflect")
    out: Dict[str, Any] = {}
    for key in allowed:
        if key in raw and isinstance(raw[key], (str, bool, int, float)):
            out[key] = raw[key]
    # `system`/`model` are the hosted-config spellings of instructions/llm.
    if "system" in out and "instructions" not in out:
        out["instructions"] = out.pop("system")
    if "model" in out and "llm" not in out:
        out["llm"] = out.pop("model")
    out.pop("system", None)
    out.pop("model", None)
    if not any(out.get(k) for k in ("name", "role", "goal", "backstory", "instructions")):
        out["instructions"] = "You are a helpful assistant."
    return out


def _parse(stdout: str) -> Optional[Dict[str, Any]]:
    """Pull the one marked JSON line out of whatever else got printed."""
    for line in reversed((stdout or "").splitlines()):
        if _MARKER in line:
            try:
                return json.loads(line.split(_MARKER, 1)[1])
            except json.JSONDecodeError:
                return None
    return None


def _write_file(container: str, path: str, content: str) -> None:
    """Write a file into the container without going through the shell.

    Piping to `docker exec -i ... tee` keeps the content off the argument list,
    so a long instruction or an API key never lands in a process listing.
    """
    import subprocess

    proc = subprocess.run(
        ["docker", "exec", "-i", container, "tee", path],
        input=content, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Could not write {path} into the container: {proc.stderr}")


def _run(cmd: List[str], *, check: bool = True, timeout: int = 300):
    import subprocess

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"`{shlex.join(cmd[:3])} ...` failed ({proc.returncode}): "
            f"{(proc.stderr or proc.stdout or '').strip()[:400]}"
        )
    return proc


def _docker_ok() -> bool:
    try:
        return _run(["docker", "version", "--format", "{{.Server.Version}}"],
                    check=False, timeout=30).returncode == 0
    except Exception:
        return False
