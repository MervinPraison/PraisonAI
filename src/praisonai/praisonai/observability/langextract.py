"""
Langextract TraceSinkProtocol Implementation for PraisonAI.

Provides LangextractSink adapter that implements TraceSinkProtocol from the core SDK,
producing self-contained interactive HTML visualizations of agent runs grounded in
the original input text.

Architecture:
- Core SDK (praisonaiagents): Defines TraceSinkProtocol (unchanged)
- Wrapper (praisonai): Implements LangextractSink adapter (this file)
- Pattern: Protocol-driven design per AGENTS.md §4.1 — mirrors LangfuseSink
"""

from __future__ import annotations
import os
import threading
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from praisonaiagents.trace.protocol import (
    ActionEvent,
    ActionEventType,
    TraceSinkProtocol,
)


@dataclass
class LangextractSinkConfig:
    """Configuration for the langextract trace sink."""
    output_path: str = "praisonai-trace.html"
    jsonl_path: Optional[str] = None           # derived from output_path if None
    document_id: str = "praisonai-run"
    auto_open: bool = False                     # open HTML in browser on close()
    include_llm_content: bool = True            # include response text in attributes
    include_tool_args: bool = True
    enabled: bool = True


class LangextractSink:
    """
    Implements `TraceSinkProtocol` by accumulating ActionEvents and, on `close()`,
    rendering them as a langextract AnnotatedDocument + interactive HTML.

    Grounding strategy:
      - We record the first AGENT_START's `metadata["input"]` as the source text.
      - OUTPUT events produce extractions grounded against the agent's output.
      - TOOL_* events produce ungrounded extractions (char_interval=None) whose
        `attributes` carry the tool name, args summary, duration, status.
      - AGENT_START/END bracket a run; we emit a single parent "agent" extraction
        spanning the whole document for overview.
    """

    __slots__ = ("_config", "_lock", "_events", "_source_text", "_closed")

    def __init__(self, config: Optional[LangextractSinkConfig] = None) -> None:
        self._config = config or LangextractSinkConfig()
        self._lock = threading.Lock()
        self._events: List[ActionEvent] = []
        self._source_text: Optional[str] = None
        self._closed = False

    # ---- TraceSinkProtocol -------------------------------------------------

    def emit(self, event: ActionEvent) -> None:
        if not self._config.enabled or self._closed:
            return
        with self._lock:
            # Capture source text from first AGENT_START
            if (
                self._source_text is None
                and event.event_type == ActionEventType.AGENT_START.value
                and event.metadata
            ):
                self._source_text = event.metadata.get("input") or ""
            self._events.append(event)

    def flush(self) -> None:
        pass  # no-op; HTML is built on close()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        try:
            self._render()
        except Exception as e:
            # Observability must never break the agent
            import logging
            logging.getLogger(__name__).warning("LangextractSink render failed: %s", e)

    # ---- Rendering ---------------------------------------------------------

    def _render(self) -> None:
        # Lazy import — langextract is optional
        try:
            import langextract as lx  # type: ignore
        except ImportError:
            raise ImportError(
                "langextract is not installed. Install with: pip install 'praisonai[langextract]'"
            )

        # Capture snapshot of events under lock to ensure thread safety
        with self._lock:
            events = self._events[:]
            source = self._source_text or ""
        
        # Skip rendering if no events were recorded
        if not events:
            return

        extractions = list(self._events_to_extractions(lx, source, events))
        doc = lx.data.AnnotatedDocument(
            document_id=self._config.document_id,
            text=source,
            extractions=extractions,
        )

        jsonl = self._config.jsonl_path or (Path(self._config.output_path).with_suffix(".jsonl").as_posix())
        Path(jsonl).parent.mkdir(parents=True, exist_ok=True)
        lx.io.save_annotated_documents([doc], output_name=os.path.basename(jsonl), output_dir=os.path.dirname(jsonl) or ".")

        html = lx.visualize(jsonl)
        html_text = html.data if hasattr(html, "data") else html
        
        # Create parent directory for output path if it doesn't exist
        output_path = Path(self._config.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html_text, encoding="utf-8")

        if self._config.auto_open:
            webbrowser.open(f"file://{output_path.resolve()}")

    def _events_to_extractions(self, lx, source: str, events: List[ActionEvent]):
        """Pure mapper: ActionEvent list -> lx.data.Extraction generator."""
        for ev in events:
            et = ev.event_type
            attrs: Dict[str, Any] = {
                "agent_name": ev.agent_name,
                "duration_ms": ev.duration_ms,
                "status": ev.status,
            }
            if et == ActionEventType.AGENT_START.value:
                yield lx.data.Extraction(
                    extraction_class="agent_run",
                    extraction_text=(source[:200] if source else ev.agent_name or "agent"),
                    attributes={**attrs, "kind": "start"},
                )
            elif et == ActionEventType.TOOL_START.value:
                yield lx.data.Extraction(
                    extraction_class="tool_call",
                    extraction_text=ev.tool_name or "tool",
                    attributes={
                        **attrs,
                        "tool_name": ev.tool_name,
                        "tool_args": ev.tool_args if self._config.include_tool_args else None,
                    },
                )
            elif et == ActionEventType.TOOL_END.value:
                yield lx.data.Extraction(
                    extraction_class="tool_result",
                    extraction_text=ev.tool_result_summary or "(empty)",
                    attributes={**attrs, "tool_name": ev.tool_name},
                )
            elif et == ActionEventType.OUTPUT.value:
                # Fix: OUTPUT events store text in tool_result_summary, not metadata['content']
                output_text = (
                    ev.tool_result_summary
                    or (ev.metadata or {}).get("output")
                    or (ev.metadata or {}).get("content", "")
                )
                yield lx.data.Extraction(
                    extraction_class="final_output",
                    extraction_text=output_text[:1000],
                    attributes=attrs,
                )
            elif et == ActionEventType.ERROR.value:
                yield lx.data.Extraction(
                    extraction_class="error",
                    extraction_text=ev.error_message or "error",
                    attributes=attrs,
                )
            # AGENT_END is summary-only — skip for now; could produce run stats extraction