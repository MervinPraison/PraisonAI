"""Run the whole agent on any compute place, not just the ones with a backend.

``run_on=`` used to accept two names while ``tools_run_on=`` accepted twelve.
That asymmetry was an implementation detail leaking into the vocabulary: every
compute place can already run an arbitrary command, and running the agent loop
is just running one more command. Nothing about ``e2b`` or ``modal`` makes them
unable to host a loop -- there simply was no backend written for them.

So instead of one bespoke backend per vendor, this wraps *any*
``ComputeProviderProtocol`` and gets the whole set at once. The specialised
``DockerManagedAgent`` remains because it can talk to the daemon directly and
skip a provisioning layer; everything else routes through here.

The limitations are the same ones every hosted runtime has, and worth stating
plainly rather than discovering later:

* **Python callables in ``tools=`` do not cross.** A function defined in your
  process cannot be rebuilt remotely, so the agent is reconstructed from its
  serialisable configuration.
* **The model API key must reach the remote environment.** That is what moving
  the loop means.
* **The package is installed on first use** unless the place's image already
  carries it.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MARKER = "__PRAISON_RESULT__"

_KEY_VARS = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "GROQ_API_KEY", "MISTRAL_API_KEY", "COHERE_API_KEY", "OPENROUTER_API_KEY",
    "DEEPSEEK_API_KEY", "XAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE",
)

_RUNNER = r'''
import json, sys

payload = json.load(open("/tmp/praison_agent.json"))
try:
    from praisonaiagents import Agent

    kwargs = {k: v for k, v in payload["agent"].items() if v is not None}
    result = Agent(**kwargs).start(payload["prompt"])
    out = {"ok": True, "result": result if isinstance(result, str) else str(result)}
except Exception as exc:                     # noqa: BLE001 - reported, not raised
    out = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

sys.stdout.write("\n__PRAISON_RESULT__" + json.dumps(out) + "\n")
'''


class ComputeManagedAgent:
    """A whole agent running on any compute place. ManagedBackendProtocol."""

    def __init__(
        self,
        place: str,
        config: Optional[Any] = None,
        *,
        provider: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        keep_alive: bool = True,
        pip_packages: Optional[List[str]] = None,
        **_ignored: Any,
    ):
        del provider                      # implied by `place`
        self._place = place
        self._config = _as_dict(config)
        self._extra_env = dict(env or {})
        self._keep_alive = keep_alive
        self._pip_packages = list(pip_packages or ["praisonaiagents"])
        self._provider = None
        self._instance: Optional[str] = None
        self._prepared = False

    @property
    def provider_name(self) -> str:
        return self._place

    @property
    def is_available(self) -> bool:
        try:
            return bool(getattr(self._resolve(), "is_available", True))
        except Exception:
            return False

    # ── ManagedBackendProtocol ───────────────────────────────────────────────
    async def execute(self, prompt: str, **kwargs) -> str:
        await self._ensure()

        payload = json.dumps({"agent": self._config, "prompt": prompt})
        await self._write("/tmp/praison_agent.json", payload)
        await self._write("/tmp/praison_runner.py", _RUNNER)

        result = await self._provider.execute(
            self._instance, "python /tmp/praison_runner.py",
            kwargs.get("timeout", 900),
        )
        answer = _parse(result.get("stdout", ""))
        if answer is None:
            detail = (result.get("stderr") or result.get("stdout") or "").strip()[-600:]
            raise RuntimeError(
                f"The agent produced no result on {self._place}.\n{detail}"
            )
        if not answer.get("ok"):
            raise RuntimeError(f"Agent failed on {self._place}: {answer['error']}")

        if not self._keep_alive:
            await self.ashutdown()
        return answer["result"]

    async def stream(self, prompt: str, **kwargs):
        """Yield the finished answer once.

        The loop runs to completion remotely, so there is no token stream to
        forward. Yielding the result keeps iterator callers working instead of
        pretending to stream.
        """
        yield await self.execute(prompt, **kwargs)

    def reset_session(self) -> None:
        from praisonaiagents.approval.utils import run_coroutine_safely

        run_coroutine_safely(self.ashutdown())

    def reset_all(self) -> None:
        self.reset_session()

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def ashutdown(self) -> None:
        if self._provider is not None and self._instance:
            try:
                await self._provider.shutdown(self._instance)
            except Exception as exc:  # pragma: no cover - teardown stays quiet
                logger.debug("[compute_managed] shutdown failed: %s", exc)
        self._instance = None
        self._prepared = False

    def _resolve(self):
        if self._provider is None:
            from praisonaiagents.managed._compute_bridge import resolve_compute

            self._provider = resolve_compute(self._place)
        return self._provider

    async def _ensure(self) -> None:
        if self._instance and self._prepared:
            return

        from praisonaiagents.managed.protocols import ComputeConfig

        provider = self._resolve()
        env = {k: os.environ[k] for k in _KEY_VARS if os.environ.get(k)}
        env.update(self._extra_env)

        info = await provider.provision(ComputeConfig(env=env))
        self._instance = getattr(info, "instance_id", info)
        logger.info("[compute_managed] provisioned %s on %s", self._instance, self._place)

        probe = await provider.execute(self._instance, "python -c 'import praisonaiagents'", 180)
        if probe.get("exit_code"):
            logger.info("[compute_managed] installing %s on %s", self._pip_packages, self._place)
            install = await provider.execute(
                self._instance,
                "pip install --no-cache-dir -q " + " ".join(map(shlex.quote, self._pip_packages)),
                900,
            )
            if install.get("exit_code"):
                await self.ashutdown()
                raise RuntimeError(
                    f"Could not install praisonaiagents on {self._place}:\n"
                    + (install.get("stderr") or "")[-600:]
                )
        self._prepared = True

    async def _write(self, path: str, content: str) -> None:
        """Write a file remotely using only the one primitive every place has.

        A compute provider exposes ``execute`` and nothing else, so the file
        goes in through a quoted heredoc. The delimiter is random and uppercase
        -- uppercase because the security policy substring-matches blocked
        commands, and a lowercase hex delimiter contains "dd" about a tenth of
        the time.
        """
        delimiter = f"__PRAISON_EOF_{uuid.uuid4().hex.upper()}__"
        while delimiter in content:
            delimiter = f"__PRAISON_EOF_{uuid.uuid4().hex.upper()}__"
        heredoc = f"cat > {shlex.quote(path)} <<'{delimiter}'\n{content}\n{delimiter}"
        result = await self._provider.execute(self._instance, heredoc, 300)
        if result.get("exit_code"):
            raise RuntimeError(
                f"Could not write {path} on {self._place}: {result.get('stderr', '')[:300]}"
            )


def _as_dict(config: Any) -> Dict[str, Any]:
    """Constructor kwargs for the remote Agent, JSON-safe values only."""
    if config is None:
        return {"instructions": "You are a helpful assistant."}
    raw = dict(config) if isinstance(config, dict) else (
        {k: v for k, v in vars(config).items() if not k.startswith("_")}
        if hasattr(config, "__dict__") else {}
    )
    allowed = ("name", "role", "goal", "backstory", "instructions", "llm",
               "system", "model", "verbose", "markdown", "self_reflect")
    out = {k: raw[k] for k in allowed if k in raw and isinstance(raw[k], (str, bool, int, float))}
    if "system" in out:
        out.setdefault("instructions", out.pop("system"))
    if "model" in out:
        out.setdefault("llm", out.pop("model"))
    out.pop("system", None)
    out.pop("model", None)
    if not any(out.get(k) for k in ("name", "role", "goal", "backstory", "instructions")):
        out["instructions"] = "You are a helpful assistant."
    return out


def _parse(stdout: str) -> Optional[Dict[str, Any]]:
    for line in reversed((stdout or "").splitlines()):
        if _MARKER in line:
            try:
                return json.loads(line.split(_MARKER, 1)[1])
            except json.JSONDecodeError:
                return None
    return None


def make_loader(place: str):
    """A registry loader binding this generic backend to one place.

    Returns a real subclass rather than a factory function: HostedAgent's
    factory path calls issubclass() on whatever the registry hands back, which
    a plain function fails with "arg 1 must be a class".
    """

    def _loader():
        def __init__(self, config=None, **kwargs):
            kwargs.pop("place", None)
            ComputeManagedAgent.__init__(self, place, config, **kwargs)

        return type(
            f"{place.capitalize()}ManagedAgent",
            (ComputeManagedAgent,),
            {"__init__": __init__, "__doc__": f"The whole agent, running on {place}."},
        )

    return _loader
