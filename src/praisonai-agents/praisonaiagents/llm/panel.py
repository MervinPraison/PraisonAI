"""
Panel (Mixture-of-Agents) LLM provider.

A ``PanelLLM`` is a *model selection*, not an orchestration primitive. One or
more advisory **reference** models run first (no tools, trimmed conversation
view); their outputs are folded into private context that is appended to the
**tail of the latest user turn** — below any stable cached prefix, so Anthropic
prompt caching on the system message is preserved. A single **aggregator** model
is the real acting model: it inherits the full normal agent loop (tool calls,
hooks, session) from :class:`~praisonaiagents.llm.llm.LLM`.

Selectable exactly like any other model::

    Agent(llm="panel:deep")
    Agent(llm={"provider": "panel", "references": [...], "aggregator": "..."})

YAML / CLI / bot ``/model`` paths flow the ``panel:<name>`` string through
unchanged because resolution happens in core model resolution.
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional, Union

from .llm import LLM

logger = logging.getLogger(__name__)


# =============================================================================
# Panel preset registry
# =============================================================================
# Named presets keyed by name. Resolved when a ``panel:<name>`` descriptor is
# selected. Wrapper/CLI/YAML can register additional presets at import time via
# ``register_panel_preset``.

PANEL_PRESETS: Dict[str, Dict[str, Any]] = {}


def register_panel_preset(name: str, config: Dict[str, Any]) -> None:
    """Register (or override) a named panel preset.

    Args:
        name: Preset name (used as ``panel:<name>``).
        config: Dict with ``references`` (list[str]), ``aggregator`` (str),
            and optional ``enabled`` (bool, default True).
    """
    PANEL_PRESETS[name] = dict(config)


def is_panel_descriptor(llm: Any) -> bool:
    """Return True if ``llm`` selects a panel provider.

    Accepts ``"panel:<name>"`` strings and ``{"provider": "panel", ...}`` dicts.
    """
    if isinstance(llm, str):
        return llm.startswith("panel:")
    if isinstance(llm, dict):
        return llm.get("provider") == "panel"
    return False


def resolve_panel_config(llm: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Resolve a panel descriptor into a normalized config dict.

    Returns a dict with keys ``references`` (list[str]), ``aggregator`` (str),
    and ``enabled`` (bool).

    Raises:
        ValueError: if the preset is unknown, the config is incomplete, or a
            recursion guard is violated (a reference/aggregator is itself a
            panel descriptor).
    """
    if isinstance(llm, str):
        name = llm.split(":", 1)[1] if ":" in llm else llm
        if name not in PANEL_PRESETS:
            raise ValueError(
                f"Unknown panel preset 'panel:{name}'. "
                f"Known presets: {sorted(PANEL_PRESETS) or '(none registered)'}. "
                "Use a dict descriptor or register_panel_preset(...) first."
            )
        config = dict(PANEL_PRESETS[name])
    elif isinstance(llm, dict):
        config = {k: v for k, v in llm.items() if k != "provider"}
    else:
        raise ValueError(f"Invalid panel descriptor: {llm!r}")

    references = config.get("references") or []
    aggregator = config.get("aggregator")
    enabled = config.get("enabled", True)

    if not aggregator:
        raise ValueError("Panel config requires an 'aggregator' model.")
    if not isinstance(references, (list, tuple)):
        raise ValueError("Panel 'references' must be a list of model strings.")

    # Recursion guard: a panel preset cannot reference another panel preset.
    if is_panel_descriptor(aggregator):
        raise ValueError("Panel 'aggregator' cannot itself be a panel descriptor.")
    for ref in references:
        if is_panel_descriptor(ref):
            raise ValueError("Panel 'references' cannot contain a panel descriptor.")

    return {
        "references": list(references),
        "aggregator": aggregator,
        "enabled": bool(enabled),
    }


# Guidance wrapper for injected reference context. Appended to the tail of the
# latest user turn so the cached system/history prefix is never modified.
_REFERENCE_HEADER = (
    "\n\n[Panel reference perspectives — advisory only, from other models. "
    "Use them to inform your answer; you remain the acting model.]\n"
)


class PanelLLM(LLM):
    """Aggregator-acting panel model.

    Subclasses :class:`LLM` so the aggregator inherits the full tool loop,
    hooks, session handling, and prompt-cache discipline unchanged. Reference
    calls are advisory (tool-free, trimmed view) and cached per user turn.
    """

    def __init__(
        self,
        aggregator: str,
        references: Optional[List[str]] = None,
        enabled: bool = True,
        reference_temperature: float = 0.0,
        **kwargs: Any,
    ):
        super().__init__(model=aggregator, **kwargs)
        self._panel_references = list(references or [])
        self._panel_enabled = bool(enabled)
        self._panel_reference_temperature = reference_temperature
        # Per-turn cache: signature(trimmed view) -> joined reference guidance.
        self._panel_ref_cache: Dict[str, str] = {}
        # Lazily-created reference LLM instances, keyed by model string.
        self._panel_ref_llms: Dict[str, LLM] = {}

    # -- helpers ------------------------------------------------------------

    def _panel_view_signature(
        self, prompt: Any, system_prompt: Optional[str], chat_history: Optional[List[Dict]]
    ) -> str:
        """Deterministic signature of the trimmed view used for caching."""
        text = repr(self._panel_trimmed_messages(prompt, system_prompt, chat_history))
        return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()

    @staticmethod
    def _panel_trimmed_messages(
        prompt: Any, system_prompt: Optional[str], chat_history: Optional[List[Dict]]
    ) -> List[Dict[str, str]]:
        """Build a strict-provider-safe, tool-free view for reference calls.

        Drops the system prompt, ``tool``-role messages and any ``tool_calls``
        payloads so strict providers do not 400 on orphan tool messages.
        Only user/assistant text content is kept.
        """
        view: List[Dict[str, str]] = []
        for m in chat_history or []:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            if role not in ("user", "assistant"):
                continue
            if m.get("tool_calls"):
                continue
            content = m.get("content")
            if isinstance(content, str) and content:
                view.append({"role": role, "content": content})
        if isinstance(prompt, str) and prompt:
            view.append({"role": "user", "content": prompt})
        elif isinstance(prompt, list):
            for part in prompt:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    view.append({"role": "user", "content": part["text"]})
        return view

    def _get_reference_llm(self, model: str) -> LLM:
        if model not in self._panel_ref_llms:
            self._panel_ref_llms[model] = LLM(model=model)
        return self._panel_ref_llms[model]

    def _format_reference_guidance(self, results: List[tuple]) -> str:
        parts = [_REFERENCE_HEADER]
        for label, text in results:
            parts.append(f"--- {label} ---\n{text}\n")
        return "".join(parts)

    @staticmethod
    def _inject_into_prompt(prompt: Any, guidance: str) -> Any:
        """Append guidance to the tail of the latest user prompt (cache-safe)."""
        if isinstance(prompt, str):
            return prompt + guidance
        if isinstance(prompt, list):
            new_prompt = [dict(p) if isinstance(p, dict) else p for p in prompt]
            for part in reversed(new_prompt):
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    part["text"] = part["text"] + guidance
                    return new_prompt
            new_prompt.append({"type": "text", "text": guidance})
            return new_prompt
        return prompt

    # -- reference execution ------------------------------------------------

    def _run_references_sync(self, view: List[Dict[str, str]]) -> str:
        results: List[tuple] = []
        for model in self._panel_references:
            label = f"Reference: {model}"
            try:
                ref_llm = self._get_reference_llm(model)
                text = ref_llm.get_response(
                    prompt=view[-1]["content"] if view else "",
                    chat_history=view[:-1] if len(view) > 1 else None,
                    temperature=self._panel_reference_temperature,
                    tools=None,
                    verbose=False,
                    stream=False,
                    markdown=False,
                )
                results.append((label, text if isinstance(text, str) else str(text)))
            except Exception as e:  # partial-failure tolerance
                logger.warning(f"Panel reference '{model}' failed: {e}")
                results.append((label, f"(unavailable: {e})"))
        return self._format_reference_guidance(results)

    async def _run_references_async(self, view: List[Dict[str, str]]) -> str:
        import asyncio

        async def _one(model: str):
            label = f"Reference: {model}"
            try:
                ref_llm = self._get_reference_llm(model)
                text = await ref_llm.get_response_async(
                    prompt=view[-1]["content"] if view else "",
                    chat_history=view[:-1] if len(view) > 1 else None,
                    temperature=self._panel_reference_temperature,
                    tools=None,
                    verbose=False,
                    stream=False,
                    markdown=False,
                )
                return (label, text if isinstance(text, str) else str(text))
            except Exception as e:  # partial-failure tolerance
                logger.warning(f"Panel reference '{model}' failed: {e}")
                return (label, f"(unavailable: {e})")

        results = await asyncio.gather(*[_one(m) for m in self._panel_references])
        return self._format_reference_guidance(list(results))

    # -- overridden entry points -------------------------------------------

    def get_response(self, prompt, system_prompt=None, chat_history=None, **kwargs):
        if self._panel_enabled and self._panel_references:
            view = self._panel_trimmed_messages(prompt, system_prompt, chat_history)
            sig = self._panel_view_signature(prompt, system_prompt, chat_history)
            guidance = self._panel_ref_cache.get(sig)
            if guidance is None:
                guidance = self._run_references_sync(view)
                self._panel_ref_cache[sig] = guidance
            prompt = self._inject_into_prompt(prompt, guidance)
        return super().get_response(
            prompt=prompt, system_prompt=system_prompt, chat_history=chat_history, **kwargs
        )

    async def get_response_async(self, prompt, system_prompt=None, chat_history=None, **kwargs):
        if self._panel_enabled and self._panel_references:
            view = self._panel_trimmed_messages(prompt, system_prompt, chat_history)
            sig = self._panel_view_signature(prompt, system_prompt, chat_history)
            guidance = self._panel_ref_cache.get(sig)
            if guidance is None:
                guidance = await self._run_references_async(view)
                self._panel_ref_cache[sig] = guidance
            prompt = self._inject_into_prompt(prompt, guidance)
        return await super().get_response_async(
            prompt=prompt, system_prompt=system_prompt, chat_history=chat_history, **kwargs
        )


def create_panel_llm(descriptor: Union[str, Dict[str, Any]], **llm_kwargs: Any) -> PanelLLM:
    """Build a :class:`PanelLLM` from a panel descriptor.

    Strips panel-only keys before forwarding remaining kwargs to ``LLM``.
    """
    config = resolve_panel_config(descriptor)
    for key in ("references", "aggregator", "enabled", "provider", "model"):
        llm_kwargs.pop(key, None)
    return PanelLLM(
        aggregator=config["aggregator"],
        references=config["references"],
        enabled=config["enabled"],
        **llm_kwargs,
    )
