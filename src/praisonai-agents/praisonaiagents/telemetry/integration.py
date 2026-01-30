"""
Performance-optimized integration module for adding telemetry to core PraisonAI components.
Uses thread pools and async patterns to minimize performance overhead.
"""

from typing import Any, Optional, TYPE_CHECKING
from functools import wraps
import time
import threading
import concurrent.futures
import queue
import asyncio
from contextlib import contextmanager

if TYPE_CHECKING:
    from .telemetry import MinimalTelemetry
    from ..agent.agent import Agent
    from ..task.task import Task
    from ..agents.agents import AgentManager

# Performance mode flag for auto-instrumentation (define early to avoid NameError)
_performance_mode_enabled = False

# Shared thread pool for telemetry operations to avoid creating threads per call
_telemetry_executor = None
_telemetry_queue = None
_queue_processor_running = False
_queue_lock = threading.Lock()
_atexit_registered = False

def _atexit_cleanup():
    """Cleanup handler registered with atexit to prevent hanging on exit."""
    global _queue_processor_running, _telemetry_executor, _telemetry_queue
    
    # Signal queue processor to stop
    _queue_processor_running = False
    
    # Shutdown executor without waiting (to prevent hang)
    if _telemetry_executor is not None:
        try:
            _telemetry_executor.shutdown(wait=False)
        except:
            pass
        _telemetry_executor = None
    
    _telemetry_queue = None

def _get_telemetry_executor():
    """Get or create the shared telemetry thread pool executor."""
    global _telemetry_executor, _atexit_registered
    if _telemetry_executor is None:
        # Use a small thread pool to avoid resource overhead
        _telemetry_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=2, 
            thread_name_prefix="telemetry"
        )
        
        # Register atexit cleanup to prevent hanging on exit
        if not _atexit_registered:
            import atexit
            atexit.register(_atexit_cleanup)
            _atexit_registered = True
            
    return _telemetry_executor

def _get_telemetry_queue():
    """Get or create the shared telemetry event queue."""
    global _telemetry_queue, _queue_processor_running
    if _telemetry_queue is None:
        _telemetry_queue = queue.Queue(maxsize=1000)  # Limit queue size to prevent memory issues
        
    # Start queue processor if not running (with proper thread safety)
    with _queue_lock:
        if not _queue_processor_running:
            _queue_processor_running = True
            # Use a daemon thread directly instead of executor to prevent hang
            processor_thread = threading.Thread(
                target=_process_telemetry_queue,
                name="telemetry-queue-processor",
                daemon=True  # Daemon thread will be killed on exit
            )
            processor_thread.start()
    
    return _telemetry_queue

def _process_telemetry_queue():
    """Background processor for telemetry events to batch operations."""
    global _telemetry_queue, _queue_processor_running
    batch_size = 10
    batch_timeout = 1.0  # Process batch every second
    
    try:
        while _queue_processor_running:
            # Check if interpreter is shutting down
            try:
                import sys
                if hasattr(sys, 'is_finalizing') and sys.is_finalizing():
                    break
            except:
                break
                
            events = []
            deadline = time.time() + batch_timeout
            
            # Collect events until batch size or timeout
            while len(events) < batch_size and time.time() < deadline:
                try:
                    if _telemetry_queue is None:
                        break
                    event = _telemetry_queue.get(timeout=0.1)
                    events.append(event)
                    _telemetry_queue.task_done()
                except queue.Empty:
                    continue
                except:
                    break
            
            # Process batch if we have events
            if events:
                _process_event_batch(events)
                
    except Exception as e:
        # Log error for debugging while maintaining non-disruptive behavior
        import logging
        logging.debug(f"Telemetry queue processing error: {e}")
        pass
    finally:
        _queue_processor_running = False

def _process_event_batch(events):
    """Process a batch of telemetry events efficiently."""
    try:
        from .telemetry import get_telemetry
        telemetry = get_telemetry()
        
        if not telemetry or not telemetry.enabled:
            return
            
        # Process events by type for efficiency
        for event in events:
            event_type = event.get('type')
            if event_type == 'agent_execution':
                telemetry.track_agent_execution(
                    event.get('agent_name'),
                    success=event.get('success', True),
                    async_mode=True  # Use async mode to prevent blocking
                )
            elif event_type == 'task_completion':
                telemetry.track_task_completion(
                    event.get('task_name'),
                    success=event.get('success', True)
                )
            elif event_type == 'tool_usage':
                telemetry.track_tool_usage(
                    event.get('tool_name'),
                    success=event.get('success', True),
                    execution_time=event.get('execution_time')
                )
            elif event_type == 'error':
                telemetry.track_error(event.get('error_type'))
            elif event_type == 'feature_usage':
                telemetry.track_feature_usage(event.get('feature_name'))
    except Exception as e:
        # Log error for debugging while maintaining non-disruptive behavior
        import logging
        logging.debug(f"Telemetry batch processing error: {e}")
        pass

@contextmanager
def _performance_mode_context():
    """Context manager for performance-critical operations that minimizes telemetry overhead."""
    # Store current performance mode state
    global _performance_mode_enabled
    original_state = _performance_mode_enabled
    
    try:
        # Temporarily enable performance mode for minimal overhead
        _performance_mode_enabled = True
        yield
    finally:
        # Restore original state
        _performance_mode_enabled = original_state


def _queue_telemetry_event(event_data):
    """Queue a telemetry event for batch processing."""
    try:
        telemetry_queue = _get_telemetry_queue()
        # Non-blocking put to avoid performance impact
        telemetry_queue.put_nowait(event_data)
    except queue.Full:
        # Queue is full, drop the event to maintain performance
        pass
    except Exception:
        # Silently handle any queue errors
        pass

def instrument_agent(agent: 'Agent', telemetry: Optional['MinimalTelemetry'] = None, performance_mode: bool = False):
    """
    Instrument an Agent instance with performance-optimized telemetry.
    
    Args:
        agent: The Agent instance to instrument
        telemetry: Optional telemetry instance (uses global if not provided)
        performance_mode: If True, uses minimal overhead tracking
    """
    # Early exit if telemetry is disabled by environment variables
    from .telemetry import _is_monitoring_disabled
    telemetry_disabled = _is_monitoring_disabled()
    
    if telemetry_disabled:
        return agent
    
    if not telemetry:
        from .telemetry import get_telemetry
        telemetry = get_telemetry()
    
    if not telemetry.enabled:
        return agent
    
    # Check if agent is already instrumented to avoid double-counting
    if hasattr(agent, '_telemetry_instrumented'):
        return agent
    
    # Store original methods
    original_chat = agent.chat if hasattr(agent, 'chat') else None
    original_start = agent.start if hasattr(agent, 'start') else None
    original_run = agent.run if hasattr(agent, 'run') else None
    original_execute_tool = agent.execute_tool if hasattr(agent, 'execute_tool') else None
    
    # Wrap chat method if it exists (this is the main method called by workflow)
    if original_chat:
        @wraps(original_chat)
        def instrumented_chat(*args, **kwargs):
            try:
                result = original_chat(*args, **kwargs)
                # Queue telemetry event for batch processing instead of creating threads
                if not performance_mode:
                    _queue_telemetry_event({
                        'type': 'agent_execution',
                        'agent_name': getattr(agent, 'name', 'unknown'),
                        'success': True
                    })
                return result
            except Exception as e:
                # Queue error event
                if not performance_mode:
                    _queue_telemetry_event({
                        'type': 'agent_execution',
                        'agent_name': getattr(agent, 'name', 'unknown'),
                        'success': False
                    })
                    _queue_telemetry_event({
                        'type': 'error',
                        'error_type': type(e).__name__
                    })
                raise
        
        agent.chat = instrumented_chat
    
    # Wrap start method if it exists
    if original_start:
        @wraps(original_start)
        def instrumented_start(*args, **kwargs):
            import types
            
            try:
                result = original_start(*args, **kwargs)
                
                # Check if result is a generator (streaming mode)
                if isinstance(result, types.GeneratorType):
                    # For streaming, defer telemetry tracking to avoid blocking
                    def streaming_wrapper():
                        try:
                            for chunk in result:
                                yield chunk
                            # Track success only after streaming completes
                            if not performance_mode:
                                _queue_telemetry_event({
                                    'type': 'agent_execution',
                                    'agent_name': getattr(agent, 'name', 'unknown'),
                                    'success': True
                                })
                        except Exception as e:
                            # Track error immediately
                            if not performance_mode:
                                _queue_telemetry_event({
                                    'type': 'agent_execution',
                                    'agent_name': getattr(agent, 'name', 'unknown'),
                                    'success': False
                                })
                                _queue_telemetry_event({
                                    'type': 'error',
                                    'error_type': type(e).__name__
                                })
                            raise
                    
                    return streaming_wrapper()
                else:
                    # For non-streaming, track immediately via queue
                    if not performance_mode:
                        _queue_telemetry_event({
                            'type': 'agent_execution',
                            'agent_name': getattr(agent, 'name', 'unknown'),
                            'success': True
                        })
                    return result
                    
            except Exception as e:
                # Track error via queue
                if not performance_mode:
                    _queue_telemetry_event({
                        'type': 'agent_execution',
                        'agent_name': getattr(agent, 'name', 'unknown'),
                        'success': False
                    })
                    _queue_telemetry_event({
                        'type': 'error',
                        'error_type': type(e).__name__
                    })
                raise
        
        agent.start = instrumented_start
    
    # Wrap run method if it exists
    if original_run:
        @wraps(original_run)
        def instrumented_run(*args, **kwargs):
            try:
                result = original_run(*args, **kwargs)
                # Track success via queue
                if not performance_mode:
                    _queue_telemetry_event({
                        'type': 'agent_execution',
                        'agent_name': getattr(agent, 'name', 'unknown'),
                        'success': True
                    })
                return result
            except Exception as e:
                # Track error via queue
                if not performance_mode:
                    _queue_telemetry_event({
                        'type': 'agent_execution',
                        'agent_name': getattr(agent, 'name', 'unknown'),
                        'success': False
                    })
                    _queue_telemetry_event({
                        'type': 'error',
                        'error_type': type(e).__name__
                    })
                raise
        
        agent.run = instrumented_run
    
    # Wrap execute_tool method
    if original_execute_tool:
        @wraps(original_execute_tool)
        def instrumented_execute_tool(tool_name: str, *args, **kwargs):
            start_time = time.time() if not performance_mode else None
            try:
                result = original_execute_tool(tool_name, *args, **kwargs)
                if not performance_mode:
                    execution_time = time.time() - start_time if start_time else None
                    _queue_telemetry_event({
                        'type': 'tool_usage',
                        'tool_name': tool_name,
                        'success': True,
                        'execution_time': execution_time
                    })
                return result
            except Exception as e:
                if not performance_mode:
                    execution_time = time.time() - start_time if start_time else None
                    _queue_telemetry_event({
                        'type': 'tool_usage',
                        'tool_name': tool_name,
                        'success': False,
                        'execution_time': execution_time
                    })
                    _queue_telemetry_event({
                        'type': 'error',
                        'error_type': type(e).__name__
                    })
                raise
        
        agent.execute_tool = instrumented_execute_tool
    
    # Mark agent as instrumented to avoid double instrumentation
    agent._telemetry_instrumented = True
    
    return agent


def instrument_workflow(workflow: 'Agents', telemetry: Optional['MinimalTelemetry'] = None, performance_mode: bool = False):
    """
    Instrument a Agents workflow with performance-optimized telemetry.
    
    Args:
        workflow: The Agents instance to instrument
        telemetry: Optional telemetry instance (uses global if not provided)
        performance_mode: If True, uses minimal overhead tracking
    """
    # Early exit if telemetry is disabled by environment variables
    from .telemetry import _is_monitoring_disabled
    telemetry_disabled = _is_monitoring_disabled()
    
    if telemetry_disabled:
        return workflow
    
    if not telemetry:
        from .telemetry import get_telemetry
        telemetry = get_telemetry()
    
    if not telemetry.enabled:
        return workflow
    
    # Check if workflow is already instrumented to avoid double-counting
    if hasattr(workflow, '_telemetry_instrumented'):
        return workflow
    
    # Track feature usage via queue
    if not performance_mode:
        _queue_telemetry_event({
            'type': 'feature_usage',
            'feature_name': f"workflow_{workflow.process}" if hasattr(workflow, 'process') else "workflow"
        })
    
    # Instrument all agents in the workflow
    if hasattr(workflow, 'agents') and workflow.agents:
        for agent in workflow.agents:
            instrument_agent(agent, telemetry, performance_mode)
    
    # Wrap the execute_task method to track task completions
    if hasattr(workflow, 'execute_task'):
        original_execute_task = workflow.execute_task
        
        @wraps(original_execute_task)
        def instrumented_execute_task(task_id, *args, **kwargs):
            task = None
            try:
                # Get task info
                if hasattr(workflow, 'tasks') and isinstance(task_id, int) and task_id < len(workflow.tasks):
                    task = workflow.tasks[task_id]
                
                result = original_execute_task(task_id, *args, **kwargs)
                
                # Track task completion via queue
                if not performance_mode:
                    task_name = task.name if task and hasattr(task, 'name') else f"task_{task_id}"
                    _queue_telemetry_event({
                        'type': 'task_completion',
                        'task_name': task_name,
                        'success': True
                    })
                
                return result
            except Exception as e:
                if not performance_mode:
                    _queue_telemetry_event({
                        'type': 'error',
                        'error_type': type(e).__name__
                    })
                    if task:
                        task_name = task.name if hasattr(task, 'name') else f"task_{task_id}"
                        _queue_telemetry_event({
                            'type': 'task_completion',
                            'task_name': task_name,
                            'success': False
                        })
                raise
        
        workflow.execute_task = instrumented_execute_task
    
    # Wrap the start method
    original_start = workflow.start
    
    @wraps(original_start)
    def instrumented_start(*args, **kwargs):
        try:
            result = original_start(*args, **kwargs)
            # Don't double-track here since agent.chat already tracks execution
            return result
        except Exception as e:
            if not performance_mode:
                _queue_telemetry_event({
                    'type': 'error',
                    'error_type': type(e).__name__
                })
            raise
    
    workflow.start = instrumented_start
    
    # Also wrap astart if it exists (async version)
    if hasattr(workflow, 'astart'):
        original_astart = workflow.astart
        
        @wraps(original_astart)
        async def instrumented_astart(*args, **kwargs):
            try:
                result = await original_astart(*args, **kwargs)
                # Don't double-track here since agent.chat already tracks execution
                return result
            except Exception as e:
                if not performance_mode:
                    _queue_telemetry_event({
                        'type': 'error',
                        'error_type': type(e).__name__
                    })
                raise
        
        workflow.astart = instrumented_astart
    
    # Mark workflow as instrumented to avoid double instrumentation
    workflow._telemetry_instrumented = True
    
    return workflow


# Auto-instrumentation helper
def auto_instrument_all(telemetry: Optional['MinimalTelemetry'] = None, performance_mode: bool = False):
    """
    Automatically instrument all new instances of Agent and Agents with optimized telemetry.
    This should be called after enabling telemetry.
    
    Args:
        telemetry: Optional telemetry instance (uses global if not provided)
        performance_mode: If True, uses minimal overhead tracking
    """
    # Early exit if telemetry is disabled by environment variables to avoid 
    # expensive class wrapping overhead
    try:
        from .telemetry import _is_monitoring_disabled
        telemetry_disabled = _is_monitoring_disabled()
    except ImportError:
        # Fallback if import fails - use same logic as _is_monitoring_disabled
        import os
        
        # Check if explicitly disabled via legacy flags
        explicitly_disabled = any([
            os.environ.get('PRAISONAI_TELEMETRY_DISABLED', '').lower() in ('true', '1', 'yes'),
            os.environ.get('PRAISONAI_DISABLE_TELEMETRY', '').lower() in ('true', '1', 'yes'),
            os.environ.get('DO_NOT_TRACK', '').lower() in ('true', '1', 'yes'),
        ])
        
        if explicitly_disabled:
            telemetry_disabled = True
        else:
            # NEW: Check if explicitly enabled (required for monitoring to be active)
            explicitly_enabled = any([
                os.environ.get('PRAISONAI_PERFORMANCE_ENABLED', '').lower() in ('true', '1', 'yes'),
                os.environ.get('PRAISONAI_TELEMETRY_ENABLED', '').lower() in ('true', '1', 'yes'),
            ])
            
            # Disabled by default unless explicitly enabled
            telemetry_disabled = not explicitly_enabled
    
    if telemetry_disabled:
        return
    
    if not telemetry:
        from .telemetry import get_telemetry
        telemetry = get_telemetry()
    
    if not telemetry.enabled:
        return
    
    try:
        # Import the classes
        from ..agent.agent import Agent
        from ..agents.agents import AgentManager
        
        # Store original __init__ methods
        original_agent_init = Agent.__init__
        original_workflow_init = Agents.__init__
        
        # Wrap Agent.__init__
        @wraps(original_agent_init)
        def agent_init_wrapper(self, *args, **kwargs):
            original_agent_init(self, *args, **kwargs)
            instrument_agent(self, telemetry, performance_mode)
        
        # Wrap Agents.__init__
        @wraps(original_workflow_init)
        def workflow_init_wrapper(self, *args, **kwargs):
            original_workflow_init(self, *args, **kwargs)
            instrument_workflow(self, telemetry, performance_mode)
        
        # Apply wrapped constructors
        Agent.__init__ = agent_init_wrapper
        Agents.__init__ = workflow_init_wrapper
        
    except ImportError:
        # Classes not available, skip auto-instrumentation
        pass


def enable_performance_mode():
    """Enable performance mode for all new telemetry instrumentation."""
    global _performance_mode_enabled
    _performance_mode_enabled = True


def disable_performance_mode():
    """Disable performance mode for all new telemetry instrumentation."""
    global _performance_mode_enabled
    _performance_mode_enabled = False


def cleanup_telemetry_resources():
    """
    Clean up telemetry resources including thread pools and queues.
    Should be called during application shutdown.
    """
    global _telemetry_executor, _telemetry_queue, _queue_processor_running
    
    # Stop queue processing
    _queue_processor_running = False
    
    # Wait for any remaining events to be processed
    if _telemetry_queue:
        try:
            # Give queue processor time to finish current batch
            import time
            time.sleep(1.1)  # Slightly longer than batch timeout
            
            # Clear any remaining events
            while not _telemetry_queue.empty():
                try:
                    _telemetry_queue.get_nowait()
                    _telemetry_queue.task_done()
                except queue.Empty:
                    break
        except Exception:
            pass
    
    # Shutdown thread pool with configurable timeout
    if _telemetry_executor:
        try:
            import os
            shutdown_timeout = float(os.environ.get('PRAISONAI_TELEMETRY_SHUTDOWN_TIMEOUT', '5.0'))
            _telemetry_executor.shutdown(wait=True, timeout=shutdown_timeout)
        except Exception as e:
            import logging
            logging.debug(f"Telemetry executor shutdown error: {e}")
            pass
        _telemetry_executor = None
    
    _telemetry_queue = None


# Performance mode flag moved to top of file to avoid NameError