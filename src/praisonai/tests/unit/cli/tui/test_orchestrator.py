"""Tests for TUI Orchestrator."""

import pytest
import asyncio
from praisonai.cli.features.tui.orchestrator import (
    TuiOrchestrator,
    UIStateModel,
    SimulationRunner,
    OutputMode,
)
from praisonai.cli.features.tui.events import TUIEvent, TUIEventType
from praisonai.cli.features.queue import QueueConfig


class TestUIStateModel:
    """Tests for UIStateModel."""
    
    def test_default_state(self):
        """Test default state values."""
        state = UIStateModel()
        assert state.session_id == ""
        assert state.model == "gpt-4o-mini"
        assert state.messages == []
        assert state.is_processing is False
        assert state.current_screen == "main"
    
    def test_add_message(self):
        """Test adding messages."""
        state = UIStateModel()
        state.add_message("user", "Hello")
        state.add_message("assistant", "Hi there!")
        
        assert len(state.messages) == 2
        assert state.messages[0]["role"] == "user"
        assert state.messages[0]["content"] == "Hello"
        assert state.messages[1]["role"] == "assistant"
    
    def test_add_message_with_extras(self):
        """Test adding messages with extra fields."""
        state = UIStateModel()
        state.add_message("assistant", "Response", run_id="run123", agent_name="Agent1")
        
        assert state.messages[0]["run_id"] == "run123"
        assert state.messages[0]["agent_name"] == "Agent1"
    
    def test_message_limit(self):
        """Test message limit enforcement."""
        state = UIStateModel(max_messages=5)
        
        for i in range(10):
            state.add_message("user", f"Message {i}")
        
        assert len(state.messages) == 5
        assert state.messages[0]["content"] == "Message 5"
    
    def test_add_event(self):
        """Test adding events."""
        state = UIStateModel()
        event = TUIEvent(event_type=TUIEventType.MESSAGE_SUBMITTED)
        state.add_event(event)
        
        assert len(state.events) == 1
        assert state.events[0]["type"] == "message_submitted"
    
    def test_to_snapshot(self):
        """Test snapshot generation."""
        state = UIStateModel(session_id="test123", model="gpt-4")
        state.add_message("user", "Hello")
        state.is_processing = True
        
        snapshot = state.to_snapshot()
        
        assert snapshot["session_id"] == "test123"
        assert snapshot["model"] == "gpt-4"
        assert snapshot["message_count"] == 1
        assert snapshot["is_processing"] is True
    
    def test_render_snapshot_pretty(self):
        """Test pretty snapshot rendering."""
        state = UIStateModel(session_id="test123")
        state.add_message("user", "Hello")
        state.add_message("assistant", "Hi!")
        
        output = state.render_snapshot_pretty()
        
        assert "PraisonAI" in output
        assert "test123" in output
        assert "USER:" in output
        assert "ASSISTANT:" in output


class TestTuiOrchestrator:
    """Tests for TuiOrchestrator."""
    
    @pytest.fixture
    def config(self):
        """Create test config."""
        return QueueConfig(enable_persistence=False)
    
    @pytest.mark.asyncio
    async def test_start_stop(self, config):
        """Test starting and stopping orchestrator."""
        orchestrator = TuiOrchestrator(
            queue_config=config,
            output_mode=OutputMode.SILENT,
        )
        
        await orchestrator.start(session_id="test-session")
        
        assert orchestrator.state.session_id == "test-session"
        assert orchestrator._running is True
        
        await orchestrator.stop()
        
        assert orchestrator._running is False
    
    @pytest.mark.asyncio
    async def test_event_callbacks(self, config):
        """Test event callbacks are called."""
        orchestrator = TuiOrchestrator(
            queue_config=config,
            output_mode=OutputMode.SILENT,
        )
        
        events = []
        orchestrator.add_event_callback(lambda e: events.append(e))
        
        await orchestrator.start()
        
        # Should have session started event
        assert len(events) >= 1
        assert events[0].event_type == TUIEventType.SESSION_STARTED
        
        await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_set_model(self, config):
        """Test setting model."""
        orchestrator = TuiOrchestrator(
            queue_config=config,
            output_mode=OutputMode.SILENT,
        )
        
        await orchestrator.start()
        orchestrator.set_model("gpt-4")
        
        assert orchestrator.state.model == "gpt-4"
        
        await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_navigate_screen(self, config):
        """Test screen navigation."""
        orchestrator = TuiOrchestrator(
            queue_config=config,
            output_mode=OutputMode.SILENT,
        )
        
        await orchestrator.start()
        orchestrator.navigate_screen("queue")
        
        assert orchestrator.state.current_screen == "queue"
        
        await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_set_focus(self, config):
        """Test focus setting."""
        orchestrator = TuiOrchestrator(
            queue_config=config,
            output_mode=OutputMode.SILENT,
        )
        
        await orchestrator.start()
        orchestrator.set_focus("chat")
        
        assert orchestrator.state.focused_widget == "chat"
        
        await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_get_snapshot(self, config):
        """Test getting snapshot."""
        orchestrator = TuiOrchestrator(
            queue_config=config,
            output_mode=OutputMode.SILENT,
        )
        
        await orchestrator.start(session_id="snap-test")
        
        snapshot = orchestrator.get_snapshot()
        
        assert snapshot["session_id"] == "snap-test"
        assert "model" in snapshot
        assert "is_processing" in snapshot
        
        await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_render_snapshot(self, config):
        """Test rendering snapshot."""
        orchestrator = TuiOrchestrator(
            queue_config=config,
            output_mode=OutputMode.SILENT,
        )
        
        await orchestrator.start()
        
        output = orchestrator.render_snapshot()
        
        assert "PraisonAI" in output
        assert "Queue" in output
        
        await orchestrator.stop()


class TestSimulationRunner:
    """Tests for SimulationRunner."""
    
    @pytest.fixture
    def config(self):
        """Create test config."""
        return QueueConfig(enable_persistence=False)
    
    @pytest.mark.asyncio
    async def test_run_empty_script(self, config):
        """Test running empty script."""
        orchestrator = TuiOrchestrator(
            queue_config=config,
            output_mode=OutputMode.SILENT,
        )
        runner = SimulationRunner(orchestrator)
        
        script = {"steps": []}
        success = await runner.run_script(script)
        
        assert success is True
    
    @pytest.mark.asyncio
    async def test_run_navigate_step(self, config):
        """Test navigate step."""
        orchestrator = TuiOrchestrator(
            queue_config=config,
            output_mode=OutputMode.SILENT,
        )
        runner = SimulationRunner(orchestrator)
        
        script = {
            "steps": [
                {"action": "navigate", "args": {"screen": "queue"}},
                {"action": "navigate", "args": {"screen": "main"}},
            ]
        }
        
        success = await runner.run_script(script)
        
        assert success is True
        assert orchestrator.state.current_screen == "main"
    
    @pytest.mark.asyncio
    async def test_run_focus_step(self, config):
        """Test focus step."""
        orchestrator = TuiOrchestrator(
            queue_config=config,
            output_mode=OutputMode.SILENT,
        )
        runner = SimulationRunner(orchestrator)
        
        script = {
            "steps": [
                {"action": "focus", "args": {"widget": "chat"}},
            ]
        }
        
        success = await runner.run_script(script)
        
        assert success is True
        assert orchestrator.state.focused_widget == "chat"
    
    @pytest.mark.asyncio
    async def test_run_model_step(self, config):
        """Test model step."""
        orchestrator = TuiOrchestrator(
            queue_config=config,
            output_mode=OutputMode.SILENT,
        )
        runner = SimulationRunner(orchestrator)
        
        script = {
            "steps": [
                {"action": "model", "args": {"model": "gpt-4"}},
            ]
        }
        
        success = await runner.run_script(script)
        
        assert success is True
        assert orchestrator.state.model == "gpt-4"
    
    @pytest.mark.asyncio
    async def test_run_sleep_step(self, config):
        """Test sleep step."""
        orchestrator = TuiOrchestrator(
            queue_config=config,
            output_mode=OutputMode.SILENT,
        )
        runner = SimulationRunner(orchestrator)
        
        script = {
            "steps": [
                {"action": "sleep", "args": {"seconds": 0.1}},
            ]
        }
        
        import time
        start = time.time()
        success = await runner.run_script(script)
        elapsed = time.time() - start
        
        assert success is True
        assert elapsed >= 0.1
    
    @pytest.mark.asyncio
    async def test_assertion_mode_pass(self, config):
        """Test assertion mode with passing assertions."""
        orchestrator = TuiOrchestrator(
            queue_config=config,
            output_mode=OutputMode.SILENT,
        )
        runner = SimulationRunner(orchestrator, assert_mode=True)
        
        script = {
            "session_id": "assert-test",
            "steps": [
                {
                    "action": "model",
                    "args": {"model": "gpt-4"},
                    "expected": {"model": "gpt-4"}
                },
            ]
        }
        
        success = await runner.run_script(script)
        summary = runner.get_summary()
        
        assert success is True
        assert summary["assertions_passed"] == 1
        assert summary["assertions_failed"] == 0
    
    @pytest.mark.asyncio
    async def test_assertion_mode_fail(self, config):
        """Test assertion mode with failing assertions."""
        orchestrator = TuiOrchestrator(
            queue_config=config,
            output_mode=OutputMode.SILENT,
        )
        runner = SimulationRunner(orchestrator, assert_mode=True)
        
        script = {
            "steps": [
                {
                    "action": "model",
                    "args": {"model": "gpt-4"},
                    "expected": {"model": "gpt-3.5"}  # Wrong expectation
                },
            ]
        }
        
        success = await runner.run_script(script)
        summary = runner.get_summary()
        
        assert success is False
        assert summary["assertions_failed"] == 1
    
    @pytest.mark.asyncio
    async def test_unknown_action(self, config):
        """Test unknown action raises error."""
        orchestrator = TuiOrchestrator(
            queue_config=config,
            output_mode=OutputMode.SILENT,
        )
        runner = SimulationRunner(orchestrator)
        
        script = {
            "steps": [
                {"action": "unknown_action", "args": {}},
            ]
        }
        
        success = await runner.run_script(script)
        
        assert success is False
        assert len(runner.errors) > 0
    
    @pytest.mark.asyncio
    async def test_get_summary(self, config):
        """Test getting summary."""
        orchestrator = TuiOrchestrator(
            queue_config=config,
            output_mode=OutputMode.SILENT,
        )
        runner = SimulationRunner(orchestrator)
        
        script = {"steps": []}
        await runner.run_script(script)
        
        summary = runner.get_summary()
        
        assert "assertions_passed" in summary
        assert "assertions_failed" in summary
        assert "errors" in summary
        assert "success" in summary
