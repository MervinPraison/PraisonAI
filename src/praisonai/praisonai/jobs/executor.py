"""
Job Executor for PraisonAI Async Jobs API.

Handles background execution of agent jobs.
"""

import asyncio
import logging
import os
from typing import Optional, Callable, Any, Dict

from .models import Job, JobStatus
from .store import JobStore

logger = logging.getLogger(__name__)


class JobExecutor:
    """
    Executes jobs in the background using asyncio.
    
    Features:
    - Concurrent job execution with configurable limits
    - Timeout handling
    - Cancellation support
    - Progress callbacks
    - Webhook notifications
    """
    
    def __init__(
        self,
        store: JobStore,
        max_concurrent: int = 10,
        default_timeout: int = 3600,
        cleanup_interval: int = 300
    ):
        self.store = store
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout
        self.cleanup_interval = cleanup_interval
        
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown = False
        self._progress_callbacks: Dict[str, Callable] = {}
    
    def _get_semaphore(self) -> asyncio.Semaphore:
        """Lazily create semaphore to avoid event loop issues."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self._semaphore
    
    async def start(self):
        """Start the executor and cleanup loop."""
        self._shutdown = False
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"JobExecutor started (max_concurrent={self.max_concurrent})")
    
    async def stop(self):
        """Stop the executor and cancel all running jobs."""
        self._shutdown = True
        
        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Cancel all running jobs
        for job_id, task in list(self._running_tasks.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._running_tasks.clear()
        logger.info("JobExecutor stopped")
    
    async def _cleanup_loop(self):
        """Periodically clean up old completed jobs."""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self.store.cleanup_old_jobs(max_age_seconds=86400)  # 24 hours
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    
    async def submit(self, job: Job) -> Job:
        """
        Submit a job for execution.
        
        Args:
            job: Job to execute
            
        Returns:
            The submitted job
        """
        # Save job to store
        await self.store.save(job)
        
        # Start execution task
        task = asyncio.create_task(self._execute_job(job))
        self._running_tasks[job.id] = task
        
        # Clean up task reference when done
        task.add_done_callback(lambda t: self._running_tasks.pop(job.id, None))
        
        logger.info(f"Job submitted: {job.id}")
        return job
    
    async def cancel(self, job_id: str) -> bool:
        """
        Cancel a running job.
        
        Args:
            job_id: ID of job to cancel
            
        Returns:
            True if cancelled, False if not found or already complete
        """
        job = await self.store.get(job_id)
        if not job:
            return False
        
        if job.is_terminal:
            return False
        
        # Mark as cancelled
        job.cancel()
        await self.store.save(job)
        
        # Cancel the task if running
        task = self._running_tasks.get(job_id)
        if task and not task.done():
            task.cancel()
        
        logger.info(f"Job cancelled: {job_id}")
        return True
    
    def register_progress_callback(self, job_id: str, callback: Callable):
        """Register a callback for job progress updates."""
        self._progress_callbacks[job_id] = callback
    
    def unregister_progress_callback(self, job_id: str):
        """Unregister a progress callback."""
        self._progress_callbacks.pop(job_id, None)
    
    async def _execute_job(self, job: Job):
        """Execute a job."""
        async with self._get_semaphore():
            try:
                # Mark as running
                job.start()
                await self.store.save(job)
                await self._notify_progress(job)
                
                logger.info(f"Job started: {job.id}")
                
                # Execute with timeout
                timeout = job.timeout or self.default_timeout
                result = await asyncio.wait_for(
                    self._run_agent(job),
                    timeout=timeout
                )
                
                # Mark as succeeded
                job.succeed(result)
                await self.store.save(job)
                await self._notify_progress(job)
                
                logger.info(f"Job succeeded: {job.id}")
                
                # Send webhook if configured
                if job.webhook_url:
                    await self._send_webhook(job)
                
            except asyncio.TimeoutError:
                job.fail(f"Job timed out after {job.timeout}s")
                await self.store.save(job)
                await self._notify_progress(job)
                logger.warning(f"Job timed out: {job.id}")
                
            except asyncio.CancelledError:
                if job.status != JobStatus.CANCELLED:
                    job.cancel()
                    await self.store.save(job)
                await self._notify_progress(job)
                logger.info(f"Job cancelled: {job.id}")
                raise
                
            except Exception as e:
                job.fail(str(e))
                await self.store.save(job)
                await self._notify_progress(job)
                logger.error(f"Job failed: {job.id} - {e}")
                
                # Send webhook for failures too
                if job.webhook_url:
                    await self._send_webhook(job)
    
    async def _run_agent(self, job: Job) -> Any:
        """
        Run the agent for a job.
        
        This is the core execution logic that runs the PraisonAI agent.
        Supports both direct agent execution and recipe-based execution.
        """
        # Check if this is a recipe job
        if job.recipe_name:
            return await self._run_recipe(job)
        
        # Imports are done lazily in _run_praisonai_agents and _run_legacy_praisonai
        
        # Determine agent configuration
        agent_file = job.agent_file or "agents.yaml"
        framework = job.framework or "praisonai"
        
        # Check if we should use inline YAML
        if job.agent_yaml:
            # Write to temp file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(job.agent_yaml)
                agent_file = f.name
        
        # Update progress
        job.update_progress(percentage=10.0, step="Initializing agent")
        await self.store.save(job)
        await self._notify_progress(job)
        
        try:
            # Try praisonaiagents first (preferred)
            if framework == "praisonai":
                result = await self._run_praisonai_agents(job, agent_file)
            else:
                # Use legacy PraisonAI for crewai/autogen
                result = await self._run_legacy_praisonai(job, agent_file, framework)
            
            return result
            
        finally:
            # Clean up temp file if created
            if job.agent_yaml and agent_file != "agents.yaml":
                try:
                    os.unlink(agent_file)
                except Exception:
                    pass
    
    async def _run_recipe(self, job: Job) -> Any:
        """Run a recipe-based job."""
        try:
            from praisonai.recipe.bridge import resolve, execute_resolved_recipe
        except ImportError:
            raise RuntimeError("Recipe execution requires praisonai.recipe module")
        
        # Update progress
        job.update_progress(percentage=10.0, step=f"Resolving recipe: {job.recipe_name}")
        await self.store.save(job)
        await self._notify_progress(job)
        
        # Resolve the recipe
        resolved = resolve(
            job.recipe_name,
            input_data=job.prompt,
            config=job.recipe_config or {},
            session_id=job.session_id,
            options={'timeout_sec': job.timeout},
        )
        
        # Update job with recipe info
        job.agent_id = f"recipe:{resolved.name}"
        job.run_id = resolved.run_id
        
        # Update progress
        job.update_progress(percentage=20.0, step=f"Executing recipe: {resolved.name}")
        await self.store.save(job)
        await self._notify_progress(job)
        
        # Execute the recipe
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: execute_resolved_recipe(resolved)
        )
        
        # Update progress
        job.update_progress(percentage=90.0, step="Finalizing")
        await self.store.save(job)
        await self._notify_progress(job)
        
        return result
    
    async def _run_praisonai_agents(self, job: Job, agent_file: str) -> Any:
        """Run using praisonaiagents framework."""
        try:
            from praisonaiagents import Agent
        except ImportError:
            raise RuntimeError("praisonaiagents not installed")
        
        # Update progress
        job.update_progress(percentage=20.0, step="Creating agent")
        await self.store.save(job)
        await self._notify_progress(job)
        
        # Create agent
        agent = Agent(
            instructions="You are a helpful AI assistant.", output="minimal"
        )
        
        # Update job with agent info
        job.agent_id = getattr(agent, 'name', 'agent')
        job.run_id = getattr(agent, 'run_id', None)
        
        # Update progress
        job.update_progress(percentage=30.0, step="Running agent")
        await self.store.save(job)
        await self._notify_progress(job)
        
        # Run the agent
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: agent.start(job.prompt)
        )
        
        # Update progress
        job.update_progress(percentage=90.0, step="Finalizing")
        await self.store.save(job)
        await self._notify_progress(job)
        
        return result
    
    async def _run_legacy_praisonai(self, job: Job, agent_file: str, framework: str) -> Any:
        """Run using legacy PraisonAI (crewai/autogen)."""
        try:
            from praisonai import PraisonAI
        except ImportError:
            raise RuntimeError("praisonai not installed")
        
        # Update progress
        job.update_progress(percentage=20.0, step="Creating PraisonAI instance")
        await self.store.save(job)
        await self._notify_progress(job)
        
        # Create PraisonAI instance
        praisonai = PraisonAI(
            agent_file=agent_file,
            framework=framework
        )
        
        # Update progress
        job.update_progress(percentage=30.0, step="Running agents")
        await self.store.save(job)
        await self._notify_progress(job)
        
        # Run in executor (blocking call)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, praisonai.run)
        
        # Update progress
        job.update_progress(percentage=90.0, step="Finalizing")
        await self.store.save(job)
        await self._notify_progress(job)
        
        return result
    
    async def _notify_progress(self, job: Job):
        """Notify progress callback if registered."""
        callback = self._progress_callbacks.get(job.id)
        if callback:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(job)
                else:
                    callback(job)
            except Exception as e:
                logger.warning(f"Progress callback error for {job.id}: {e}")
    
    async def _send_webhook(self, job: Job):
        """Send webhook notification for job completion."""
        if not job.webhook_url:
            return
        
        try:
            import httpx
            
            payload = {
                "job_id": job.id,
                "status": job.status.value,
                "result": job.result if job.status == JobStatus.SUCCEEDED else None,
                "error": job.error if job.status == JobStatus.FAILED else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "duration_seconds": job.duration_seconds
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    job.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code >= 400:
                    logger.warning(f"Webhook failed for {job.id}: {response.status_code}")
                else:
                    logger.info(f"Webhook sent for {job.id}")
                    
        except Exception as e:
            logger.error(f"Webhook error for {job.id}: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get executor statistics."""
        return {
            "running_jobs": len(self._running_tasks),
            "max_concurrent": self.max_concurrent,
            "default_timeout": self.default_timeout,
            "shutdown": self._shutdown
        }
