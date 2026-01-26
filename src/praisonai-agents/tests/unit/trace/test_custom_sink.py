"""
Tests for custom sink protocol and trace_context helper.

TDD tests to verify:
1. Custom sinks can implement ContextTraceSinkProtocol protocol (duck typing)
2. trace_context() context manager properly sets/resets emitter
3. Exception in sink doesn't crash agent execution
4. Protocol compliance validation

Note: ContextTraceSink is a backward-compat alias for ContextTraceSinkProtocol
per AGENTS.md naming convention (XProtocol for interfaces).
"""


class TestCustomSinkProtocol:
    """Tests for custom sink implementing ContextTraceSinkProtocol protocol."""
    
    def test_custom_sink_duck_typing_works(self):
        """Test that a custom class implementing emit/flush/close works as sink."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextTraceSinkProtocol
        )
        
        # Custom sink - NO inheritance required
        class MyCustomSink:
            def __init__(self):
                self.events = []
            
            def emit(self, event):
                self.events.append(event)
            
            def flush(self):
                pass
            
            def close(self):
                pass
        
        sink = MyCustomSink()
        
        # Should pass isinstance check (runtime_checkable)
        assert isinstance(sink, ContextTraceSinkProtocol)
        
        # Should work with emitter
        emitter = ContextTraceEmitter(sink=sink, session_id="test", enabled=True)
        emitter.session_start({"test": True})
        
        assert len(sink.events) == 1
        assert sink.events[0].event_type.value == "session_start"
    
    def test_custom_sink_without_inheritance(self):
        """Test that custom sink works without inheriting from any base class."""
        from praisonaiagents.trace.context_events import ContextTraceEmitter
        
        received_events = []
        
        # Completely standalone class
        class HTTPSink:
            def emit(self, event):
                received_events.append(event.to_dict())
            
            def flush(self):
                pass
            
            def close(self):
                pass
        
        sink = HTTPSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="http-test", enabled=True)
        
        emitter.agent_start("test_agent", {"role": "tester"})
        emitter.agent_end("test_agent")
        
        assert len(received_events) == 2
        assert received_events[0]["event_type"] == "agent_start"
        assert received_events[1]["event_type"] == "agent_end"


class TestTraceContextManager:
    """Tests for trace_context() context manager."""
    
    def test_trace_context_sets_emitter(self):
        """Test that trace_context sets the emitter for the context."""
        from praisonaiagents.trace.context_events import (
            trace_context, get_context_emitter,
            ContextTraceEmitter, ContextListSink
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="ctx-test", enabled=True)
        
        with trace_context(emitter):
            current = get_context_emitter()
            assert current is emitter
            assert current.enabled
    
    def test_trace_context_resets_after_exit(self):
        """Test that trace_context resets emitter after exiting."""
        from praisonaiagents.trace.context_events import (
            trace_context, get_context_emitter,
            ContextTraceEmitter, ContextListSink
        )
        
        # Get default (disabled)
        default = get_context_emitter()
        assert not default.enabled
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="reset-test", enabled=True)
        
        with trace_context(emitter):
            pass  # Do nothing
        
        # Should be back to default
        after = get_context_emitter()
        assert not after.enabled
    
    def test_trace_context_resets_on_exception(self):
        """Test that trace_context resets emitter even when exception occurs."""
        from praisonaiagents.trace.context_events import (
            trace_context, get_context_emitter,
            ContextTraceEmitter, ContextListSink
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="exc-test", enabled=True)
        
        try:
            with trace_context(emitter):
                raise ValueError("Test exception")
        except ValueError:
            pass
        
        # Should still be reset
        after = get_context_emitter()
        assert not after.enabled
    
    def test_trace_context_yields_emitter(self):
        """Test that trace_context yields the emitter."""
        from praisonaiagents.trace.context_events import (
            trace_context, ContextTraceEmitter, ContextListSink
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="yield-test", enabled=True)
        
        with trace_context(emitter) as ctx_emitter:
            assert ctx_emitter is emitter
            ctx_emitter.session_start({})
        
        assert len(sink.get_events()) == 1


class TestSinkExceptionSafety:
    """Tests for exception safety in sink operations."""
    
    def test_sink_exception_does_not_crash_emitter(self):
        """Test that exception in sink.emit() doesn't crash the emitter."""
        from praisonaiagents.trace.context_events import ContextTraceEmitter
        
        class FailingSink:
            def emit(self, event):
                raise RuntimeError("Sink failed!")
            
            def flush(self):
                pass
            
            def close(self):
                pass
        
        sink = FailingSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="fail-test", enabled=True)
        
        # Should NOT raise - exception should be silently caught
        emitter.session_start({})
        emitter.agent_start("test", {})
        emitter.agent_end("test")
        emitter.session_end()
        
        # If we get here, test passes
        assert True
    
    def test_sink_exception_allows_agent_to_continue(self):
        """Test that failing sink doesn't prevent agent operations."""
        from praisonaiagents.trace.context_events import (
            trace_context, ContextTraceEmitter
        )
        
        call_count = 0
        
        class CountingFailingSink:
            def emit(self, event):
                nonlocal call_count
                call_count += 1
                raise Exception("Always fails")
            
            def flush(self):
                pass
            
            def close(self):
                pass
        
        sink = CountingFailingSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="count-test", enabled=True)
        
        with trace_context(emitter):
            emitter.session_start({})
            emitter.agent_start("agent1", {})
            emitter.agent_end("agent1")
        
        # All emit calls should have been attempted
        assert call_count == 3


class TestProtocolCompliance:
    """Tests for protocol compliance checking."""
    
    def test_runtime_checkable_protocol(self):
        """Test that ContextTraceSink is runtime_checkable."""
        from praisonaiagents.trace.context_events import ContextTraceSink
        from typing import Protocol
        
        # Should be a Protocol
        assert issubclass(ContextTraceSink, Protocol)
    
    def test_builtin_sinks_implement_protocol(self):
        """Test that all built-in sinks implement the protocol."""
        from praisonaiagents.trace.context_events import (
            ContextTraceSink, ContextNoOpSink, ContextListSink
        )
        
        noop = ContextNoOpSink()
        list_sink = ContextListSink()
        
        assert isinstance(noop, ContextTraceSink)
        assert isinstance(list_sink, ContextTraceSink)
    
    def test_incomplete_sink_fails_isinstance(self):
        """Test that incomplete implementation fails isinstance check."""
        from praisonaiagents.trace.context_events import ContextTraceSink
        
        # Missing close() method
        class IncompleteSink:
            def emit(self, event):
                pass
            
            def flush(self):
                pass
            # No close() method
        
        sink = IncompleteSink()
        assert not isinstance(sink, ContextTraceSink)


class TestMainPackageExports:
    """Tests for exports from main praisonaiagents package."""
    
    def test_context_trace_sink_exported(self):
        """Test ContextTraceSink is exported from main package."""
        from praisonaiagents import ContextTraceSink
        from typing import Protocol
        assert issubclass(ContextTraceSink, Protocol)
    
    def test_context_trace_emitter_exported(self):
        """Test ContextTraceEmitter is exported from main package."""
        from praisonaiagents import ContextTraceEmitter
        assert ContextTraceEmitter is not None
    
    def test_trace_context_exported(self):
        """Test trace_context is exported from main package."""
        from praisonaiagents import trace_context
        assert callable(trace_context)
    
    def test_context_event_exported(self):
        """Test ContextEvent is exported from main package."""
        from praisonaiagents import ContextEvent
        assert ContextEvent is not None
    
    def test_context_event_type_exported(self):
        """Test ContextEventType is exported from main package."""
        from praisonaiagents import ContextEventType
        assert hasattr(ContextEventType, 'SESSION_START')
