"""
Core Execution Module.

Provides the unified execution primitives:
- _execute_core(): Single implementation shared by all paths
- execute_sync(): Synchronous wrapper for CLI
- execute_async(): Asynchronous wrapper for TUI workers
"""

import asyncio
import time
import uuid
from typing import Optional, AsyncGenerator

from .request import ExecutionRequest
from .result import ExecutionResult


def _generate_run_id() -> str:
    """Generate a unique run ID."""
    return str(uuid.uuid4())[:8]


def _execute_core(
    request: ExecutionRequest,
    timing: Optional[dict] = None,
) -> ExecutionResult:
    """
    THE SINGLE EXECUTION IMPLEMENTATION.
    
    All execution modes call this function.
    Profiler wraps this function, never injects into it.
    
    Args:
        request: The execution request
        timing: Optional dict to record timing phases (for profiling)
    
    Returns:
        ExecutionResult with output and metadata
    """
    run_id = _generate_run_id()
    start_time = time.perf_counter()
    
    if timing is not None:
        timing["core_start"] = start_time
    
    try:
        # Phase 1: Import (measured inline)
        import_start = time.perf_counter()
        from praisonaiagents import Agent
        import_end = time.perf_counter()
        
        if timing is not None:
            timing["imports_ms"] = (import_end - import_start) * 1000
        
        # Phase 2: Agent Construction
        agent_start = time.perf_counter()
        
        agent_config = {
            "name": request.agent_name,
            "verbose": False,
        }
        
        if request.agent_instructions:
            agent_config["instructions"] = request.agent_instructions
        
        if request.model:
            agent_config["llm"] = request.model
        
        if request.tools:
            agent_config["tools"] = list(request.tools)
        
        agent = Agent(**agent_config)
        agent_end = time.perf_counter()
        
        if timing is not None:
            timing["agent_init_ms"] = (agent_end - agent_start) * 1000
        
        # Phase 3: Execution
        exec_start = time.perf_counter()
        
        if request.stream:
            # For streaming, collect all chunks
            chunks = []
            if hasattr(agent, '_start_stream'):
                for chunk in agent._start_stream(request.prompt):
                    chunks.append(chunk)
            else:
                # Fallback to non-streaming
                result = agent.start(request.prompt)
                chunks = [result] if result else []
            output = "".join(chunks)
        else:
            output = agent.start(request.prompt)
        
        exec_end = time.perf_counter()
        
        if timing is not None:
            timing["execution_ms"] = (exec_end - exec_start) * 1000
        
        end_time = time.perf_counter()
        
        if timing is not None:
            timing["total_ms"] = (end_time - start_time) * 1000
        
        return ExecutionResult(
            output=output or "",
            run_id=run_id,
            success=True,
            start_time=start_time,
            end_time=end_time,
            metadata={
                "model": request.model,
                "stream": request.stream,
            },
        )
        
    except Exception as e:
        end_time = time.perf_counter()
        
        if timing is not None:
            timing["total_ms"] = (end_time - start_time) * 1000
            timing["error"] = str(e)
        
        return ExecutionResult.from_error(
            error=str(e),
            run_id=run_id,
        )


def execute_sync(request: ExecutionRequest) -> ExecutionResult:
    """
    Synchronous execution wrapper.
    
    Used by:
    - CLI direct prompt
    - Profile command
    
    Args:
        request: The execution request
    
    Returns:
        ExecutionResult with output and metadata
    """
    return _execute_core(request)


async def execute_async(request: ExecutionRequest) -> ExecutionResult:
    """
    Asynchronous execution wrapper.
    
    Used by:
    - TUI workers
    - Queue system
    
    Args:
        request: The execution request
    
    Returns:
        ExecutionResult with output and metadata
    """
    # Run the synchronous core in a thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _execute_core, request, None)


async def execute_async_stream(
    request: ExecutionRequest,
) -> AsyncGenerator[str, None]:
    """
    Asynchronous streaming execution.
    
    Yields chunks as they arrive.
    
    Args:
        request: The execution request (stream=True recommended)
    
    Yields:
        String chunks of the response
    """
    try:
        from praisonaiagents import Agent
        
        agent_config = {
            "name": request.agent_name,
            "verbose": False,
        }
        
        if request.agent_instructions:
            agent_config["instructions"] = request.agent_instructions
        
        if request.model:
            agent_config["llm"] = request.model
        
        if request.tools:
            agent_config["tools"] = list(request.tools)
        
        agent = Agent(**agent_config)
        
        if hasattr(agent, '_start_stream'):
            for chunk in agent._start_stream(request.prompt):
                yield chunk
                await asyncio.sleep(0)  # Yield control
        else:
            result = agent.start(request.prompt)
            if result:
                yield result
                
    except Exception as e:
        yield f"Error: {e}"
