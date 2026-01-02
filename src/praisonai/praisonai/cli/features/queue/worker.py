"""
Worker Pool for PraisonAI Queue System.

Manages async workers that execute queued runs.
"""

import asyncio
import logging
import time
from collections import deque
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

from .models import QueuedRun, RunState, StreamChunk, QueueEvent
from .scheduler import QueueScheduler

logger = logging.getLogger(__name__)


class StreamBuffer:
    """Bounded buffer with backpressure for streaming output."""
    
    def __init__(self, max_size: int = 1000, drop_strategy: str = "oldest"):
        """
        Initialize stream buffer.
        
        Args:
            max_size: Maximum number of chunks to buffer.
            drop_strategy: "oldest" to drop oldest, "newest" to reject new.
        """
        self._buffer: deque = deque(maxlen=max_size)
        self._lock = asyncio.Lock()
        self._drop_strategy = drop_strategy
        self._dropped_count = 0
        self._max_size = max_size
    
    async def push(self, chunk: StreamChunk) -> bool:
        """
        Push a chunk to the buffer.
        
        Returns:
            True if added, False if dropped.
        """
        async with self._lock:
            if len(self._buffer) >= self._max_size:
                if self._drop_strategy == "oldest":
                    self._buffer.popleft()
                    self._dropped_count += 1
                elif self._drop_strategy == "newest":
                    self._dropped_count += 1
                    return False
            self._buffer.append(chunk)
            return True
    
    async def drain(self, batch_size: int = 50) -> List[StreamChunk]:
        """Drain up to batch_size chunks."""
        async with self._lock:
            result = []
            for _ in range(min(batch_size, len(self._buffer))):
                result.append(self._buffer.popleft())
            return result
    
    async def drain_all(self) -> List[StreamChunk]:
        """Drain all chunks."""
        async with self._lock:
            result = list(self._buffer)
            self._buffer.clear()
            return result
    
    @property
    def size(self) -> int:
        """Current buffer size."""
        return len(self._buffer)
    
    @property
    def dropped_count(self) -> int:
        """Number of dropped chunks."""
        return self._dropped_count


class WorkerPool:
    """
    Manages worker tasks for executing queued runs.
    
    Workers poll the scheduler for runs and execute them with streaming output.
    """
    
    def __init__(
        self,
        scheduler: QueueScheduler,
        on_output: Optional[Callable[[str, str], Coroutine[Any, Any, None]]] = None,
        on_complete: Optional[Callable[[str, QueuedRun], Coroutine[Any, Any, None]]] = None,
        on_error: Optional[Callable[[str, Exception], Coroutine[Any, Any, None]]] = None,
        on_event: Optional[Callable[[QueueEvent], Coroutine[Any, Any, None]]] = None,
        max_workers: int = 4,
        poll_interval: float = 0.1,
        stream_buffer_size: int = 1000,
    ):
        """
        Initialize worker pool.
        
        Args:
            scheduler: The queue scheduler.
            on_output: Callback for streaming output (run_id, chunk).
            on_complete: Callback when run completes (run_id, run).
            on_error: Callback when run fails (run_id, exception).
            on_event: Callback for queue events.
            max_workers: Maximum number of concurrent workers.
            poll_interval: Seconds between scheduler polls.
            stream_buffer_size: Size of stream buffer per run.
        """
        self.scheduler = scheduler
        self.on_output = on_output
        self.on_complete = on_complete
        self.on_error = on_error
        self.on_event = on_event
        self.max_workers = max_workers
        self.poll_interval = poll_interval
        self.stream_buffer_size = stream_buffer_size
        
        self._workers: List[asyncio.Task] = []
        self._running = False
        self._stream_buffers: Dict[str, StreamBuffer] = {}
        self._active_runs: Set[str] = set()
    
    async def start(self) -> None:
        """Start the worker pool."""
        if self._running:
            return
        
        self._running = True
        
        for i in range(self.max_workers):
            task = asyncio.create_task(
                self._worker_loop(i),
                name=f"queue-worker-{i}"
            )
            self._workers.append(task)
        
        logger.info(f"Started {self.max_workers} queue workers")
    
    async def stop(self, timeout: float = 5.0) -> None:
        """
        Stop all workers gracefully.
        
        Args:
            timeout: Seconds to wait for workers to finish.
        """
        self._running = False
        
        if not self._workers:
            return
        
        # Wait for workers to finish current work
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._workers, return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            # Cancel remaining workers
            for task in self._workers:
                if not task.done():
                    task.cancel()
            
            await asyncio.gather(*self._workers, return_exceptions=True)
        
        self._workers.clear()
        logger.info("Stopped queue workers")
    
    async def _worker_loop(self, worker_id: int) -> None:
        """Main worker loop."""
        logger.debug(f"Worker {worker_id} started")
        
        while self._running:
            try:
                # Get next run from scheduler
                run = await self.scheduler.next()
                
                if run is None:
                    # No work available, wait and retry
                    await asyncio.sleep(self.poll_interval)
                    continue
                
                # Execute the run
                self._active_runs.add(run.run_id)
                try:
                    await self._execute_run(run, worker_id)
                finally:
                    self._active_runs.discard(run.run_id)
                    
            except asyncio.CancelledError:
                logger.debug(f"Worker {worker_id} cancelled")
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)
        
        logger.debug(f"Worker {worker_id} stopped")
    
    async def _execute_run(self, run: QueuedRun, worker_id: int) -> None:
        """Execute a single run with streaming output."""
        logger.debug(f"Worker {worker_id} executing run {run.run_id}")
        
        # Create stream buffer for this run
        buffer = StreamBuffer(max_size=self.stream_buffer_size)
        self._stream_buffers[run.run_id] = buffer
        
        output_chunks: List[str] = []
        
        try:
            # Import agent lazily to avoid circular imports
            from praisonaiagents import Agent
            from .manager import QueueManager
            
            # Get agent configuration
            agent_config = run.config.get("agent_config", {})
            agent_name = run.agent_name or agent_config.get("name", "Assistant")
            
            # Get tools from runtime registry (not from config, as functions can't be serialized)
            tools = QueueManager.get_tools_for_run(run.run_id)
            
            # Create agent with session_id for history persistence
            # Agent automatically restores history from JSON store when session_id is provided
            # Note: Agent uses 'llm' parameter, not 'model'
            agent = Agent(
                name=agent_name,
                instructions=agent_config.get("instructions", "You are a helpful assistant."),
                llm=agent_config.get("model"),
                tools=tools,
                verbose=agent_config.get("verbose", False),
                session_id=agent_config.get("session_id") or run.session_id,  # Use session for history
            )
            
            # Legacy: Inject chat history if provided (for backward compatibility)
            # This is no longer needed as Agent now has built-in JSON persistence
            # but we keep it for cases where chat_history is explicitly passed
            if run.chat_history and not agent.chat_history:
                agent.chat_history = list(run.chat_history)
                logger.debug(f"Injected {len(run.chat_history)} messages from run.chat_history (legacy)")
            
            # Check for cancellation before starting
            if self.scheduler.is_cancelled(run.run_id):
                logger.debug(f"Run {run.run_id} was cancelled before execution")
                return
            
            # Execute with streaming if available
            chunk_index = 0
            
            # Try streaming first
            try:
                async for chunk in self._stream_agent(agent, run.input_content):
                    # Check for cancellation
                    if self.scheduler.is_cancelled(run.run_id):
                        logger.debug(f"Run {run.run_id} cancelled during execution")
                        self.scheduler.clear_cancel_token(run.run_id)
                        return
                    
                    # Check for pause
                    while run.state == RunState.PAUSED:
                        await asyncio.sleep(0.1)
                        if self.scheduler.is_cancelled(run.run_id):
                            return
                    
                    output_chunks.append(chunk)
                    
                    # Buffer the chunk
                    stream_chunk = StreamChunk(
                        run_id=run.run_id,
                        content=chunk,
                        chunk_index=chunk_index,
                    )
                    await buffer.push(stream_chunk)
                    chunk_index += 1
                    
                    # Emit output callback
                    if self.on_output:
                        try:
                            await self.on_output(run.run_id, chunk)
                        except Exception as e:
                            logger.error(f"Error in output callback: {e}")
                            
            except Exception as stream_error:
                # Fallback to non-streaming
                logger.debug(f"Streaming failed, falling back to sync: {stream_error}")
                result = agent.chat(run.input_content)
                output_chunks = [result]
                
                if self.on_output:
                    try:
                        await self.on_output(run.run_id, result)
                    except Exception as e:
                        logger.error(f"Error in output callback: {e}")
            
            # Combine output
            full_output = "".join(output_chunks)
            
            # Mark final chunk
            final_chunk = StreamChunk(
                run_id=run.run_id,
                content="",
                chunk_index=chunk_index,
                is_final=True,
            )
            await buffer.push(final_chunk)
            
            # Complete the run
            completed_run = await self.scheduler.complete(
                run.run_id,
                output=full_output,
                metrics={
                    "chunks": chunk_index,
                    "output_length": len(full_output),
                }
            )
            
            if completed_run and self.on_complete:
                try:
                    await self.on_complete(run.run_id, completed_run)
                except Exception as e:
                    logger.error(f"Error in complete callback: {e}")
                    
        except asyncio.CancelledError:
            # Worker was cancelled
            await self.scheduler.cancel(run.run_id)
            raise
            
        except Exception as e:
            logger.error(f"Run {run.run_id} failed: {e}", exc_info=True)
            
            # Mark as failed
            failed_run = await self.scheduler.fail(run.run_id, str(e))
            
            if self.on_error:
                try:
                    await self.on_error(run.run_id, e)
                except Exception as callback_error:
                    logger.error(f"Error in error callback: {callback_error}")
                    
        finally:
            # Cleanup buffer
            self._stream_buffers.pop(run.run_id, None)
    
    async def _stream_agent(self, agent, input_content: str):
        """
        Stream output from agent.
        
        Yields chunks of output text.
        """
        # Try to use agent's async streaming if available
        if hasattr(agent, 'astream'):
            async for chunk in agent.astream(input_content):
                yield chunk
        elif hasattr(agent, 'stream'):
            # Wrap sync stream in async
            for chunk in agent.stream(input_content):
                yield chunk
                await asyncio.sleep(0)  # Yield control
        else:
            # Fallback: get full response and yield in chunks
            result = agent.chat(input_content)
            
            # Simulate streaming by yielding words
            words = result.split()
            chunk_size = 3  # Words per chunk
            
            for i in range(0, len(words), chunk_size):
                chunk_words = words[i:i + chunk_size]
                chunk = " ".join(chunk_words)
                if i + chunk_size < len(words):
                    chunk += " "
                yield chunk
                await asyncio.sleep(0.05)  # Small delay for streaming effect
    
    def get_stream_buffer(self, run_id: str) -> Optional[StreamBuffer]:
        """Get the stream buffer for a run."""
        return self._stream_buffers.get(run_id)
    
    @property
    def active_run_count(self) -> int:
        """Number of currently executing runs."""
        return len(self._active_runs)
    
    @property
    def is_running(self) -> bool:
        """Whether the worker pool is running."""
        return self._running
