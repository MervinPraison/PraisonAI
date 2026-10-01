"""
Adapter to wrap recipe execution behind the standard Agent duck-typing for Gateway and BotOS.

Streaming source lives in the wrapper (``praisonai.recipe`` — ``run``/``run_stream``);
this core adapter is only a thin bridge that forwards incremental recipe events into
the already-present :class:`StreamEventEmitter` so recipe/YAML-backed gateway agents
reach parity with Python ``Agent``-backed ones (token drafts, status phrases, SSE).
"""

import asyncio
import logging
from typing import Any, Optional
from praisonaiagents.streaming import StreamEventEmitter

logger = logging.getLogger(__name__)

class RecipeBotAdapter:
    """Wraps recipe execution to act like an Agent for gateway/bot compatibility."""

    def __init__(self, recipe_name: str, **kwargs):
        self.recipe_name = recipe_name
        self.config = kwargs
        self.stream_emitter = StreamEventEmitter()

    @property
    def name(self) -> str:
        return f"recipe-{self.recipe_name}"

    def _recipe_module(self):
        """Lazy import of the wrapper recipe API (heavy implementation stays in praisonai)."""
        try:
            from praisonai import recipe
            return recipe
        except ImportError as e:
            raise ImportError(
                f"Failed to load PraisonAI recipe components: {e}. "
                "Make sure you have praisonai installed."
            ) from e

    @staticmethod
    def _extract_text(output: Any) -> str:
        """Best-effort render of a recipe output payload to a single string."""
        if output is None:
            return ""
        if isinstance(output, str):
            return output
        if hasattr(output, "final_output"):
            return str(output.final_output)
        if isinstance(output, dict):
            for key in ("reply", "output", "message", "text", "result"):
                if key in output:
                    return str(output[key])
        return str(output)

    def chat(self, message: str) -> str:
        """Process the message via the recipe runtime (blocking, string-only)."""
        try:
            recipe = self._recipe_module()
            result = recipe.run(self.recipe_name, input={"user_input": message}, config=self.config or None)
            if getattr(result, "ok", False):
                return self._extract_text(result.output)
            error = getattr(result, "error", None) or "Recipe execution failed"
            raise RuntimeError(error)
        except Exception as e:
            logger.error(f"Recipe execution failed: {e}")
            from ...bots.failure import render_failure_reply

            return render_failure_reply(e).text

    async def astart(self, message: str, stream: bool = False, **kwargs) -> str:
        """Async surface used by the gateway/bot streaming hot path.

        Forwards the recipe's incremental events into ``self.stream_emitter`` so the
        bot DraftStreamer / OpenAI-compatible SSE surface receive progressive output,
        then returns the final text. Degrades safely to a single final send when the
        recipe runtime cannot produce incremental output.
        """
        return await self.achat(message)

    async def achat(self, message: str) -> str:
        """Stream recipe execution into ``self.stream_emitter`` and return final text."""
        from praisonaiagents.streaming import StreamEvent, StreamEventType

        try:
            recipe = self._recipe_module()
        except Exception as e:  # pragma: no cover - import guard
            logger.error(f"Recipe execution failed: {e}")
            from ...bots.failure import render_failure_reply

            return render_failure_reply(e).text

        loop = asyncio.get_running_loop()
        has_listeners = self.stream_emitter.has_callbacks

        def _emit(event: StreamEvent) -> None:
            try:
                self.stream_emitter.emit(event)
            except Exception as emit_exc:  # never break the run on an emit failure
                logger.debug("Recipe stream emit failed: %s", emit_exc)

        def _run_blocking() -> str:
            final_text = ""
            emitted_first = False
            try:
                stream = recipe.run_stream(
                    self.recipe_name,
                    input={"user_input": message},
                    config=self.config or None,
                )
                for rec_event in stream:
                    etype = getattr(rec_event, "event_type", "")
                    data = getattr(rec_event, "data", {}) or {}
                    if etype == "progress" and has_listeners:
                        text = data.get("message")
                        if text:
                            _emit(StreamEvent(
                                type=StreamEventType.TOOL_PROGRESS,
                                content=str(text),
                                metadata={"step": data.get("step")},
                            ))
                    elif etype == "output":
                        final_text = self._extract_text(data.get("output"))
                        if final_text and has_listeners:
                            if not emitted_first:
                                _emit(StreamEvent(type=StreamEventType.FIRST_TOKEN))
                                emitted_first = True
                            _emit(StreamEvent(
                                type=StreamEventType.DELTA_TEXT,
                                content=final_text,
                            ))
                    elif etype == "error":
                        raise RuntimeError(data.get("message") or "Recipe execution failed")
                if has_listeners:
                    _emit(StreamEvent(type=StreamEventType.STREAM_END))
                return final_text
            except Exception:
                if has_listeners:
                    _emit(StreamEvent(type=StreamEventType.STREAM_END))
                raise

        try:
            return await loop.run_in_executor(None, _run_blocking)
        except Exception as e:
            logger.error(f"Recipe execution failed: {e}")
            from ...bots.failure import render_failure_reply

            return render_failure_reply(e).text
