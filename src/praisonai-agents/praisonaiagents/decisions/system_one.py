"""Call Ollama / TypeSafe System One decision endpoint (``POST /v1/systemone``).

See: https://ollama.com/blog/ollama-now-supports-jev-style-decision-models
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping, MutableMapping, Optional

KNOWN_DECISION_MODELS = frozenset({"nimble", "tev1", "tev1:0.8b"})


def is_decision_model(model: str) -> bool:
    """Return True if *model* looks like a known Ollama decision model id."""
    name = (model or "").strip().split("/")[-1]
    if name in KNOWN_DECISION_MODELS:
        return True
    return name.startswith("tev1")


def resolve_system_one_base_url(api_base: Optional[str] = None) -> str:
    """Resolve base URL for ``/v1/systemone`` (Ollama 0.35+ or TypeSafe cloud)."""
    if api_base:
        return api_base.rstrip("/")
    for key in ("TYPESAFE_BASE_URL", "OLLAMA_HOST"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            from praisonaiagents.local.target import parse_ollama_host

            parsed = parse_ollama_host(raw) if not raw.startswith("http") else raw.rstrip("/")
            if parsed:
                return parsed.rstrip("/")
            return raw.rstrip("/")
    return "http://127.0.0.1:11434"


def choice_question(instructions: str, criteria: Mapping[str, str]) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": dict(criteria)}


def noul_question(instructions: str) -> dict[str, Any]:
    return {"type": "noul", "instructions": instructions}


def score_question(instructions: str, criteria: list[str]) -> dict[str, Any]:
    return {"type": "score", "instructions": instructions, "criteria": list(criteria)}


@dataclass
class SystemOneResult:
    """Parsed ``/v1/systemone`` response."""

    model: str
    answers: dict[str, Any]
    usage: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def choice(self, name: str) -> Optional[str]:
        entry = self.answers.get(name) or {}
        if entry.get("type") == "choice":
            return entry.get("choice")
        return None

    def noul(self, name: str) -> Optional[float]:
        entry = self.answers.get(name) or {}
        if entry.get("type") == "noul":
            val = entry.get("noul")
            return float(val) if val is not None else None
        return None

    def score(self, name: str) -> Optional[float]:
        entry = self.answers.get(name) or {}
        if entry.get("type") == "score":
            val = entry.get("score")
            return float(val) if val is not None else None
        return None

    def confidence(self, name: str) -> Optional[float]:
        entry = self.answers.get(name) or {}
        val = entry.get("confidence")
        return float(val) if val is not None else None


def _default_timeout(explicit: float) -> float:
    if explicit != 120.0:
        return explicit
    raw = (os.environ.get("SYSTEM_ONE_TIMEOUT") or os.environ.get("OLLAMA_SYSTEM_ONE_TIMEOUT") or "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return 600.0


def _default_api_key(api_key: Optional[str]) -> Optional[str]:
    if api_key is not None:
        return api_key
    return os.environ.get("TYPESAFE_API_KEY") or os.environ.get("OLLAMA_API_KEY") or "ollama"


def _build_payload(
    *,
    model: str,
    state: Mapping[str, Any],
    questions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "model": model,
        "state": dict(state),
        "questions": {k: dict(v) for k, v in questions.items()},
    }


def _parse_response(data: dict[str, Any]) -> SystemOneResult:
    return SystemOneResult(
        model=str(data.get("model") or ""),
        answers=dict(data.get("answers") or {}),
        usage=dict(data.get("usage") or {}),
        raw=data,
    )


def system_one(
    *,
    state: Mapping[str, Any],
    questions: Mapping[str, Mapping[str, Any]],
    model: Optional[str] = None,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: float = 120.0,
) -> SystemOneResult:
    """
    Run a System One decision request against Ollama or TypeSafe.

    Example::

        from praisonaiagents.decisions import system_one, choice_question, noul_question

        result = system_one(
            state={"ticket": "Please refund my duplicate charge."},
            questions={
                "team": choice_question(
                    "Which team?",
                    {"billing": "Payments", "technical": "Bugs", "other": "Other"},
                ),
                "refund": noul_question("Does the user ask for a refund?"),
            },
            model="nimble",
        )
        assert result.choice("team") == "billing"
    """
    resolved_model = (
        model
        or os.environ.get("TYPESAFE_DEFAULT_MODEL")
        or os.environ.get("OLLAMA_DECISION_MODEL")
        or "nimble"
    )
    base = resolve_system_one_base_url(api_base)
    url = f"{base}/v1/systemone"
    body = json.dumps(_build_payload(model=resolved_model, state=state, questions=questions)).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    key = _default_api_key(api_key)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    timeout = _default_timeout(timeout)
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"system_one HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"system_one failed to reach {url!r}. Is Ollama 0.35+ running with a decision model pulled?"
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"system_one expected JSON object, got {type(data).__name__}")
    return _parse_response(data)


async def asystem_one(
    *,
    state: Mapping[str, Any],
    questions: Mapping[str, Mapping[str, Any]],
    model: Optional[str] = None,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: float = 120.0,
) -> SystemOneResult:
    """Async ``system_one`` using aiohttp (already a core dependency)."""
    import aiohttp

    resolved_model = (
        model
        or os.environ.get("TYPESAFE_DEFAULT_MODEL")
        or os.environ.get("OLLAMA_DECISION_MODEL")
        or "nimble"
    )
    base = resolve_system_one_base_url(api_base)
    url = f"{base}/v1/systemone"
    payload = _build_payload(model=resolved_model, state=state, questions=questions)
    headers: MutableMapping[str, str] = {"Content-Type": "application/json", "Accept": "application/json"}
    key = _default_api_key(api_key)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    timeout_obj = aiohttp.ClientTimeout(total=_default_timeout(timeout))
    async with aiohttp.ClientSession(timeout=timeout_obj) as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"system_one HTTP {resp.status}: {text[:2000]}")
            data = json.loads(text)
    if not isinstance(data, dict):
        raise RuntimeError(f"system_one expected JSON object, got {type(data).__name__}")
    return _parse_response(data)


def system_one_via_typesafe_sdk(
    *,
    state: Mapping[str, Any],
    questions: Mapping[str, Any],
    model: Optional[str] = None,
    timeout: float = 120.0,
) -> SystemOneResult:
    """Optional path through the official ``typesafe-sdk`` (``pip install typesafe-sdk``)."""
    try:
        from typesafe_sdk import TypeSafeClient
    except ImportError as exc:
        raise ImportError(
            "typesafe-sdk is not installed. Use: pip install typesafe-sdk "
            "or call system_one() which uses HTTP directly."
        ) from exc

    with TypeSafeClient(timeout=timeout) as client:
        result = client.system_one(state=dict(state), questions=dict(questions), model=model)
    answers: dict[str, Any] = {}
    for key, val in getattr(result, "answers", {}).items():
        answers[key] = val if isinstance(val, dict) else getattr(val, "__dict__", {"value": val})
    return SystemOneResult(
        model=str(getattr(result, "model", model or "")),
        answers=answers,
        usage=dict(getattr(result, "usage", {}) or {}),
        raw={"via": "typesafe-sdk"},
    )
