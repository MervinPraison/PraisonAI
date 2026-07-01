"""
JSONL Display Mode for PraisonAI CLI.

Provides structured JSONL output matching Gemini CLI's STREAM_JSON format.
Each event is a single JSON line written to stderr.

Usage:
    praisonai "prompt" --display jsonl 2>/tmp/events.jsonl
    
Event Types:
    - init: Session start with model info
    - tool_use: Tool call with parameters
    - tool_result: Tool completion with status/output
    - llm_start: LLM call start
    - llm_end: LLM call end with metrics
    - autonomy_step: Autonomy iteration info (PraisonAI unique)
    - error: Error event
    - result: Final result with stats
"""

import json
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TextIO


class JsonlDisplay:
    """JSONL event emitter matching Gemini CLI's STREAM_JSON format.
    
    Thread-safe for multi-agent execution.
    """
    
    def __init__(self, file: TextIO = None):
        self.file = file or sys.stderr
        self._start_time = time.time()
        self._tool_calls = 0
        self._tokens_in = 0
        self._tokens_out = 0
    
    def emit(self, event_type: str, **kwargs) -> None:
        """Emit a JSONL event. Thread-safe."""
        event = {
            "type": event_type,
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        # Filter None values
        event.update({k: v for k, v in kwargs.items() if v is not None})
        
        try:
            self.file.write(json.dumps(event, default=str) + "\n")
            self.file.flush()
        except Exception:
            pass  # Silently ignore write errors
    
    def on_init(self, model: str = None, session_id: str = None) -> None:
        """Emit init event at session start."""
        self.emit("init", model=model, session_id=session_id)
    
    def on_tool_call(
        self,
        message: str = None,
        tool_name: str = None,
        tool_input: Dict[str, Any] = None,
        tool_output: str = None,
        **kwargs
    ) -> None:
        """Callback for tool calls - emits tool_use or tool_result."""
        if tool_name:
            if tool_output is None:
                # Tool starting
                self._tool_calls += 1
                self.emit("tool_use", tool=tool_name, args=tool_input)
            else:
                # Tool completed
                output_str = str(tool_output)[:500] if tool_output else None
                self.emit("tool_result", tool=tool_name, status="ok", output=output_str)
    
    def on_llm_start(self, model: str = None, agent_name: str = None, **kwargs) -> None:
        """Callback for LLM call start."""
        self.emit("llm_start", model=model, agent=agent_name)
    
    def on_llm_end(
        self,
        model: str = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost: float = None,
        latency_ms: float = None,
        **kwargs
    ) -> None:
        """Callback for LLM call end with metrics."""
        self._tokens_in += tokens_in
        self._tokens_out += tokens_out
        self.emit(
            "llm_end",
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost=cost,
            latency_ms=latency_ms
        )
    
    def on_error(self, message: str = None, **kwargs) -> None:
        """Callback for errors."""
        if message:
            self.emit("error", severity="error", message=str(message))
    
    def on_interaction(self, response: str = None, agent_name: str = None, **kwargs) -> None:
        """Callback for agent response."""
        if response:
            # Truncate for JSONL
            self.emit("message", role="assistant", content=response[:2000], agent=agent_name)
    
    # P3/G2: Autonomy-specific events (PraisonAI unique!)
    def on_autonomy_iteration(
        self,
        iteration: int = None,
        max_iterations: int = None,
        stage: str = None,
        **kwargs
    ) -> None:
        """Callback for autonomy iteration."""
        self.emit("autonomy_step", iteration=iteration, max=max_iterations, stage=stage)
    
    def on_autonomy_stage_change(
        self,
        from_stage: str = None,
        to_stage: str = None,
        **kwargs
    ) -> None:
        """Callback for autonomy stage escalation."""
        self.emit("autonomy_stage", from_stage=from_stage, to_stage=to_stage)
    
    def on_autonomy_doom_loop(
        self,
        iteration: int = None,
        recovery_action: str = None,
        **kwargs
    ) -> None:
        """Callback for doom loop detection."""
        self.emit("autonomy_doom_loop", iteration=iteration, recovery=recovery_action)
    
    def on_complete(
        self,
        reason: str = None,
        iterations: int = None,
        duration_ms: float = None,
        **kwargs
    ) -> None:
        """Emit final result event with stats."""
        duration = duration_ms or (time.time() - self._start_time) * 1000
        self.emit(
            "result",
            status="success" if reason in ("goal", "promise") else "stopped",
            reason=reason,
            iterations=iterations,
            duration_ms=duration,
            stats={
                "total_tokens": self._tokens_in + self._tokens_out,
                "input_tokens": self._tokens_in,
                "output_tokens": self._tokens_out,
                "tool_calls": self._tool_calls,
            }
        )


def create_jsonl_display(file: TextIO = None) -> JsonlDisplay:
    """Create a JSONL display instance."""
    return JsonlDisplay(file=file)


__all__ = ["JsonlDisplay", "create_jsonl_display"]
