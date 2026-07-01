"""
TUI Orchestrator for PraisonAI.

Provides unified event handling for both interactive TUI and headless simulation modes.
Inspired by gemini-cli's event-driven architecture and codex-cli's state management.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TextIO
import sys

from .events import TUIEvent, TUIEventType
from ..queue import QueueManager, QueueConfig, QueuedRun, RunState

logger = logging.getLogger(__name__)


class OutputMode(str, Enum):
    """Output mode for headless simulation."""
    PRETTY = "pretty"
    JSONL = "jsonl"
    SILENT = "silent"


@dataclass
class UIStateModel:
    """
    In-memory UI state model.
    
    Mirrors the state that would be displayed in the TUI,
    enabling headless simulation and snapshot generation.
    """
    # Session info
    session_id: str = ""
    workspace: str = ""
    
    # Model/config
    model: str = "gpt-4o-mini"
    
    # Chat history
    messages: List[Dict[str, Any]] = field(default_factory=list)
    max_messages: int = 1000
    
    # Current streaming state
    current_run_id: Optional[str] = None
    streaming_content: str = ""
    is_processing: bool = False
    
    # Queue state
    queued_runs: List[Dict[str, Any]] = field(default_factory=list)
    running_runs: List[Dict[str, Any]] = field(default_factory=list)
    
    # Tool calls
    pending_tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    recent_tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    
    # Metrics
    total_tokens: int = 0
    total_cost: float = 0.0
    
    # Focus/screen state (for simulation)
    current_screen: str = "main"
    focused_widget: str = "composer"
    
    # Events log (for trace/replay)
    events: List[Dict[str, Any]] = field(default_factory=list)
    max_events: int = 10000
    
    def add_message(self, role: str, content: str, **kwargs) -> None:
        """Add a message to history."""
        msg = {
            "role": role,
            "content": content,
            "timestamp": time.time(),
            **kwargs
        }
        self.messages.append(msg)
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
    
    def add_event(self, event: TUIEvent) -> None:
        """Add an event to the log."""
        evt = {
            "type": event.event_type.value,
            "timestamp": event.timestamp,
            "run_id": event.run_id,
            "session_id": event.session_id,
            "agent_name": event.agent_name,
            "data": event.data,
        }
        self.events.append(evt)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]
    
    def to_snapshot(self) -> Dict[str, Any]:
        """Generate a snapshot of current state."""
        return {
            "session_id": self.session_id,
            "model": self.model,
            "current_screen": self.current_screen,
            "focused_widget": self.focused_widget,
            "is_processing": self.is_processing,
            "current_run_id": self.current_run_id,
            "streaming_content_length": len(self.streaming_content),
            "message_count": len(self.messages),
            "last_messages": self.messages[-5:] if self.messages else [],
            "queued_count": len(self.queued_runs),
            "running_count": len(self.running_runs),
            "pending_tool_calls": len(self.pending_tool_calls),
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
        }
    
    def render_snapshot_pretty(self) -> str:
        """Render a pretty text snapshot like TUI would show."""
        lines = []
        
        # Status bar
        status = f"◉ PraisonAI │ Session: {self.session_id[:8] if self.session_id else 'new'}"
        status += f" │ Model: {self.model}"
        if self.total_tokens > 0:
            status += f" │ Tokens: {self.total_tokens:,}"
        if self.total_cost > 0:
            status += f" │ ${self.total_cost:.4f}"
        if self.is_processing:
            status += " │ ⟳ Processing..."
        lines.append("─" * 60)
        lines.append(status)
        lines.append("─" * 60)
        
        # Chat messages (last 5)
        lines.append("\n[Chat History]")
        for msg in self.messages[-5:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:100]
            if len(msg.get("content", "")) > 100:
                content += "..."
            lines.append(f"  {role.upper()}: {content}")
        
        # Streaming content
        if self.streaming_content:
            lines.append(f"\n[Streaming] ({len(self.streaming_content)} chars)")
            preview = self.streaming_content[-200:]
            if len(self.streaming_content) > 200:
                preview = "..." + preview
            lines.append(f"  {preview}")
        
        # Queue status
        lines.append(f"\n[Queue] Queued: {len(self.queued_runs)} │ Running: {len(self.running_runs)}")
        
        # Tool calls
        if self.pending_tool_calls:
            lines.append(f"\n[Pending Approvals] {len(self.pending_tool_calls)}")
            for tc in self.pending_tool_calls[:3]:
                lines.append(f"  ⚠ {tc.get('tool_name', 'unknown')}")
        
        # Screen/focus
        lines.append(f"\n[UI] Screen: {self.current_screen} │ Focus: {self.focused_widget}")
        lines.append("─" * 60)
        
        return "\n".join(lines)


class TuiOrchestrator:
    """
    Unified orchestrator for TUI and headless modes.
    
    Subscribes to the event bus and maintains an in-memory UI state model.
    Can drive Textual widgets (interactive) or output snapshots (headless).
    """
    
    def __init__(
        self,
        queue_manager: Optional[QueueManager] = None,
        queue_config: Optional[QueueConfig] = None,
        output_mode: OutputMode = OutputMode.PRETTY,
        output_stream: Optional[TextIO] = None,
        jsonl_path: Optional[str] = None,
        debug: bool = False,
    ):
        self.queue_config = queue_config or QueueConfig()
        self.queue_manager = queue_manager
        self.output_mode = output_mode
        self.output_stream = output_stream or sys.stdout
        self.jsonl_path = jsonl_path
        self.debug = debug
        
        # State
        self.state = UIStateModel()
        self._event_callbacks: List[Callable[[TUIEvent], None]] = []
        self._jsonl_file: Optional[TextIO] = None
        self._running = False
        
        # Trace ID for this orchestrator session
        self.trace_id = str(uuid.uuid4())[:8]
    
    async def start(self, session_id: Optional[str] = None, recover: bool = True) -> None:
        """Start the orchestrator."""
        self.state.session_id = session_id or str(uuid.uuid4())[:8]
        self._running = True
        
        # Open JSONL file if specified
        if self.jsonl_path:
            self._jsonl_file = open(self.jsonl_path, "a")
        
        # Initialize queue manager if not provided
        if not self.queue_manager:
            self.queue_manager = QueueManager(
                config=self.queue_config,
                on_output=self._handle_output,
                on_complete=self._handle_complete,
                on_error=self._handle_error,
            )
            await self.queue_manager.start(recover=recover)
            self.queue_manager.set_session(self.state.session_id)
        
        self._emit_event(TUIEvent(
            event_type=TUIEventType.SESSION_STARTED,
            session_id=self.state.session_id,
            data={"trace_id": self.trace_id}
        ))
        
        if self.debug:
            self._log_debug(f"Orchestrator started: session={self.state.session_id}, trace={self.trace_id}")
    
    async def stop(self) -> None:
        """Stop the orchestrator."""
        self._running = False
        
        if self.queue_manager:
            await self.queue_manager.stop()
        
        if self._jsonl_file:
            self._jsonl_file.close()
            self._jsonl_file = None
        
        if self.debug:
            self._log_debug("Orchestrator stopped")
    
    def add_event_callback(self, callback: Callable[[TUIEvent], None]) -> None:
        """Add an event callback."""
        self._event_callbacks.append(callback)
    
    def _emit_event(self, event: TUIEvent) -> None:
        """Emit an event to all listeners."""
        # Add to state log
        self.state.add_event(event)
        
        # Write to JSONL if enabled
        if self._jsonl_file:
            self._write_jsonl(event)
        
        # Call callbacks
        for callback in self._event_callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Event callback error: {e}")
        
        # Output based on mode
        if self.output_mode == OutputMode.JSONL:
            self._print_jsonl(event)
        elif self.output_mode == OutputMode.PRETTY and self.debug:
            self._print_event_pretty(event)
    
    def _write_jsonl(self, event: TUIEvent) -> None:
        """Write event to JSONL file."""
        if not self._jsonl_file:
            return
        
        record = {
            "timestamp": event.timestamp,
            "trace_id": self.trace_id,
            "session_id": event.session_id or self.state.session_id,
            "event_type": event.event_type.value,
            "run_id": event.run_id,
            "agent_name": event.agent_name,
            "data": event.data,
        }
        self._jsonl_file.write(json.dumps(record, default=str) + "\n")
        self._jsonl_file.flush()
    
    def _print_jsonl(self, event: TUIEvent) -> None:
        """Print event as JSONL to output stream."""
        record = {
            "timestamp": event.timestamp,
            "event_type": event.event_type.value,
            "run_id": event.run_id,
            "data": event.data,
        }
        print(json.dumps(record, default=str), file=self.output_stream)
    
    def _print_event_pretty(self, event: TUIEvent) -> None:
        """Print event in pretty format."""
        ts = time.strftime("%H:%M:%S", time.localtime(event.timestamp))
        print(f"[{ts}] {event.event_type.value}", end="", file=self.output_stream)
        if event.run_id:
            print(f" run={event.run_id[:8]}", end="", file=self.output_stream)
        if event.data:
            data_preview = str(event.data)[:50]
            print(f" {data_preview}", end="", file=self.output_stream)
        print(file=self.output_stream)
    
    def _log_debug(self, message: str) -> None:
        """Log debug message."""
        if self.debug:
            ts = time.strftime("%H:%M:%S")
            print(f"[DEBUG {ts}] {message}", file=self.output_stream)
    
    # Queue callbacks
    
    async def _handle_output(self, run_id: str, chunk: str) -> None:
        """Handle streaming output."""
        if run_id == self.state.current_run_id:
            self.state.streaming_content += chunk
        
        self._emit_event(TUIEvent.output_chunk(run_id, chunk))
    
    async def _handle_complete(self, run_id: str, run: QueuedRun) -> None:
        """Handle run completion."""
        if run_id == self.state.current_run_id:
            # Add assistant message
            self.state.add_message(
                "assistant",
                run.output_content or self.state.streaming_content,
                run_id=run_id,
                agent_name=run.agent_name,
            )
            
            # Update metrics
            if run.metrics:
                self.state.total_tokens += run.metrics.get("tokens", 0)
                self.state.total_cost += run.metrics.get("cost", 0.0)
            
            # Clear streaming state
            self.state.current_run_id = None
            self.state.streaming_content = ""
            self.state.is_processing = False
        
        # Update queue state
        self._update_queue_state()
        
        self._emit_event(TUIEvent.run_completed(
            run_id,
            run.output_content or "",
            agent_name=run.agent_name,
        ))
    
    async def _handle_error(self, run_id: str, error: Exception) -> None:
        """Handle run error."""
        if run_id == self.state.current_run_id:
            self.state.add_message(
                "system",
                f"Error: {error}",
                run_id=run_id,
            )
            self.state.current_run_id = None
            self.state.streaming_content = ""
            self.state.is_processing = False
        
        self._update_queue_state()
        
        self._emit_event(TUIEvent.error(str(error), run_id=run_id))
    
    def _update_queue_state(self) -> None:
        """Update queue state from manager."""
        if not self.queue_manager:
            return
        
        runs = self.queue_manager.list_runs(limit=100)
        self.state.queued_runs = [
            r.to_dict() for r in runs if r.state == RunState.QUEUED
        ]
        self.state.running_runs = [
            r.to_dict() for r in runs if r.state == RunState.RUNNING
        ]
    
    # Public API
    
    async def submit_message(self, content: str, agent_name: str = "Assistant") -> str:
        """Submit a message for processing."""
        # Add user message
        self.state.add_message("user", content)
        self.state.is_processing = True
        
        self._emit_event(TUIEvent.message_submitted(content))
        
        # Submit to queue
        run_id = await self.queue_manager.submit(
            input_content=content,
            agent_name=agent_name,
            config={"agent_config": {"name": agent_name, "model": self.state.model}}
        )
        
        self.state.current_run_id = run_id
        self.state.streaming_content = ""
        
        # Add placeholder for streaming
        self.state.add_message(
            "assistant",
            "",
            run_id=run_id,
            agent_name=agent_name,
            is_streaming=True,
        )
        
        self._update_queue_state()
        
        return run_id
    
    async def cancel_run(self, run_id: Optional[str] = None) -> bool:
        """Cancel a run."""
        target_id = run_id or self.state.current_run_id
        if not target_id:
            return False
        
        result = await self.queue_manager.cancel(target_id)
        
        if target_id == self.state.current_run_id:
            self.state.current_run_id = None
            self.state.streaming_content = ""
            self.state.is_processing = False
        
        self._update_queue_state()
        
        self._emit_event(TUIEvent(
            event_type=TUIEventType.RUN_CANCELLED,
            run_id=target_id,
        ))
        
        return result
    
    async def retry_run(self, run_id: str) -> Optional[str]:
        """Retry a failed run."""
        new_id = await self.queue_manager.retry(run_id)
        self._update_queue_state()
        return new_id
    
    def set_model(self, model: str) -> None:
        """Set the current model."""
        self.state.model = model
        self._emit_event(TUIEvent.status_update(f"Model set to {model}"))
    
    def navigate_screen(self, screen: str) -> None:
        """Navigate to a screen (for simulation)."""
        self.state.current_screen = screen
        self._emit_event(TUIEvent(
            event_type=TUIEventType.SCREEN_CHANGED,
            data={"screen": screen}
        ))
    
    def set_focus(self, widget: str) -> None:
        """Set focus to a widget (for simulation)."""
        self.state.focused_widget = widget
        self._emit_event(TUIEvent(
            event_type=TUIEventType.FOCUS_CHANGED,
            data={"widget": widget}
        ))
    
    def get_snapshot(self) -> Dict[str, Any]:
        """Get current state snapshot."""
        return self.state.to_snapshot()
    
    def render_snapshot(self) -> str:
        """Render pretty snapshot."""
        return self.state.render_snapshot_pretty()
    
    async def wait_for_idle(self, timeout: float = 60.0) -> bool:
        """Wait until no runs are processing."""
        start = time.time()
        while time.time() - start < timeout:
            if not self.state.is_processing and not self.state.running_runs:
                return True
            await asyncio.sleep(0.1)
        return False
    
    async def wait_for_run(self, run_id: str, timeout: float = 60.0) -> bool:
        """Wait for a specific run to complete."""
        start = time.time()
        while time.time() - start < timeout:
            run = self.queue_manager.get_run(run_id)
            if run and run.state.is_terminal():
                return True
            await asyncio.sleep(0.1)
        return False


@dataclass
class SimulationStep:
    """A step in a simulation script."""
    action: str  # "submit", "cancel", "retry", "navigate", "focus", "wait", "approve", "deny"
    args: Dict[str, Any] = field(default_factory=dict)
    expected: Optional[Dict[str, Any]] = None  # For assertion mode


class SimulationRunner:
    """
    Runs simulation scripts for headless TUI testing.
    
    Script format (YAML):
    ```yaml
    session_id: test-session
    model: gpt-4o-mini
    steps:
      - action: submit
        args:
          content: "Hello, world!"
      - action: wait
        args:
          condition: idle
          timeout: 30
      - action: navigate
        args:
          screen: queue
      - action: cancel
        args:
          run_id: current
    ```
    """
    
    def __init__(
        self,
        orchestrator: TuiOrchestrator,
        assert_mode: bool = False,
    ):
        self.orchestrator = orchestrator
        self.assert_mode = assert_mode
        self.assertions_passed = 0
        self.assertions_failed = 0
        self.errors: List[str] = []
    
    async def run_script(self, script: Dict[str, Any]) -> bool:
        """Run a simulation script."""
        # Initialize session
        session_id = script.get("session_id")
        await self.orchestrator.start(session_id=session_id)
        
        if "model" in script:
            self.orchestrator.set_model(script["model"])
        
        # Run steps
        steps = script.get("steps", [])
        for i, step_data in enumerate(steps):
            step = SimulationStep(
                action=step_data.get("action", ""),
                args=step_data.get("args", {}),
                expected=step_data.get("expected"),
            )
            
            try:
                await self._run_step(step, i)
            except Exception as e:
                self.errors.append(f"Step {i} ({step.action}): {e}")
                if self.assert_mode:
                    break
        
        await self.orchestrator.stop()
        
        return len(self.errors) == 0
    
    async def _run_step(self, step: SimulationStep, index: int) -> None:
        """Run a single simulation step."""
        action = step.action.lower()
        args = step.args
        
        if action == "submit":
            content = args.get("content", "")
            agent = args.get("agent", "Assistant")
            await self.orchestrator.submit_message(content, agent)
        
        elif action == "cancel":
            run_id = args.get("run_id")
            if run_id == "current":
                run_id = None
            await self.orchestrator.cancel_run(run_id)
        
        elif action == "retry":
            run_id = args.get("run_id", "")
            await self.orchestrator.retry_run(run_id)
        
        elif action == "navigate":
            screen = args.get("screen", "main")
            self.orchestrator.navigate_screen(screen)
        
        elif action == "focus":
            widget = args.get("widget", "composer")
            self.orchestrator.set_focus(widget)
        
        elif action == "wait":
            condition = args.get("condition", "idle")
            timeout = args.get("timeout", 30.0)
            
            if condition == "idle":
                success = await self.orchestrator.wait_for_idle(timeout)
            elif condition == "run":
                run_id = args.get("run_id", "")
                success = await self.orchestrator.wait_for_run(run_id, timeout)
            else:
                await asyncio.sleep(timeout)
                success = True
            
            if not success and self.assert_mode:
                raise TimeoutError(f"Wait condition '{condition}' timed out")
        
        elif action == "model":
            model = args.get("model", "gpt-4o-mini")
            self.orchestrator.set_model(model)
        
        elif action == "snapshot":
            snapshot = self.orchestrator.render_snapshot()
            print(snapshot)
        
        elif action == "sleep":
            duration = args.get("seconds", 1.0)
            await asyncio.sleep(duration)
        
        else:
            raise ValueError(f"Unknown action: {action}")
        
        # Check assertions
        if self.assert_mode and step.expected:
            self._check_assertions(step.expected, index)
    
    def _check_assertions(self, expected: Dict[str, Any], step_index: int) -> None:
        """Check assertions against current state."""
        snapshot = self.orchestrator.get_snapshot()
        
        for key, expected_value in expected.items():
            actual_value = snapshot.get(key)
            
            if actual_value != expected_value:
                self.assertions_failed += 1
                self.errors.append(
                    f"Step {step_index}: Expected {key}={expected_value}, got {actual_value}"
                )
            else:
                self.assertions_passed += 1
    
    def get_summary(self) -> Dict[str, Any]:
        """Get simulation summary."""
        return {
            "assertions_passed": self.assertions_passed,
            "assertions_failed": self.assertions_failed,
            "errors": self.errors,
            "success": len(self.errors) == 0,
        }
