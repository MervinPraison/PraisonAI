"""
Real deployment scheduler that integrates with the actual deployment system.

This module provides the actual deployment scheduler implementation that was
previously shadowed by the mock in __init__.py.
"""

import logging
import threading
import asyncio
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class DeployerInterface(ABC):
    """Abstract interface for deployers to ensure provider compatibility."""
    
    @abstractmethod
    def deploy(self) -> bool:
        """Execute deployment. Returns True on success, False on failure."""
        pass


class DeployHandlerAdapter(DeployerInterface):
    """Adapter for the real DeployHandler to match the scheduler interface."""
    
    def __init__(self, provider: str = "gcp", config: Optional[Dict[str, Any]] = None):
        self.provider = provider
        self.config = config or {}
    
    def deploy(self) -> bool:
        """Execute deployment using the real DeployHandler."""
        try:
            from types import SimpleNamespace
            from praisonai_deploy.cli.features.deploy import DeployHandler

            handler = DeployHandler()

            # Build a namespace carrying every attribute ``handle_deploy`` reads.
            deploy_args = SimpleNamespace(
                file=self.config.get("file", "agents.yaml"),
                type=self.config.get("type", "cloud"),
                provider=self.provider,
                json=False,
                background=False,
                verbose=False,
                yes=True,
                force=False,
            )

            # ``handle_deploy`` signals failure via ``sys.exit`` (SystemExit).
            handler.handle_deploy(deploy_args)
            return True

        except SystemExit as exc:
            code = exc.code
            success = code in (None, 0)
            if not success:
                logger.error(f"Deployment failed with exit code {code}")
            return success
        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            return False


class DeploymentScheduler:
    """
    Real deployment scheduler with provider-agnostic design.
    
    Features:
    - Simple interval-based scheduling
    - Thread-safe operation
    - Integrates with actual DeployHandler
    - Provider dispatch support
    """
    
    def __init__(self, provider: str = "gcp", config: Optional[Dict[str, Any]] = None):
        self.provider = provider
        self.config = config or {}
        self.is_running = False
        self._stop_event = threading.Event()
        self._thread = None
        self._deployer = None
        
    def set_deployer(self, deployer: DeployerInterface):
        """Set custom deployer implementation."""
        self._deployer = deployer
        
    def _get_deployer(self) -> DeployerInterface:
        """Get deployer instance using factory pattern."""
        if self._deployer:
            return self._deployer
        
        # Use real DeployHandler via adapter
        return DeployHandlerAdapter(self.provider, self.config)
    
    def start(self, schedule_expr: str, max_retries: int = 3) -> bool:
        """
        Start scheduled deployment.
        
        Args:
            schedule_expr: Schedule expression (e.g., "daily", "*/6h", "3600")
            max_retries: Maximum retry attempts on failure
            
        Returns:
            True if scheduler started successfully
        """
        if self.is_running:
            logger.warning("Scheduler is already running")
            return False
            
        try:
            from praisonai_deploy._wrapper_bridge import import_wrapper_module

            ScheduleParser = import_wrapper_module("praisonai.scheduler.shared").ScheduleParser
            interval = ScheduleParser.parse(schedule_expr)
            self.is_running = True
            self._stop_event.clear()
            
            self._thread = threading.Thread(
                target=self._run_schedule,
                args=(interval, max_retries),
                daemon=True
            )
            self._thread.start()
            
            logger.info(f"Deployment scheduler started with {interval}s interval")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            self.is_running = False
            return False
    
    def stop(self) -> bool:
        """Stop the scheduler."""
        if not self.is_running:
            return True
            
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            
        self.is_running = False
        logger.info("Deployment scheduler stopped")
        return True
    
    def _run_schedule(self, interval: int, max_retries: int):
        """Internal method to run scheduled deployments."""
        deployer = self._get_deployer()
        
        while not self._stop_event.is_set():
            logger.info("Starting scheduled deployment")
            
            success = False
            for attempt in range(max_retries):
                try:
                    if deployer.deploy():
                        logger.info(f"Deployment successful on attempt {attempt + 1}")
                        success = True
                        break
                    else:
                        logger.warning(f"Deployment failed on attempt {attempt + 1}")
                except Exception as e:
                    logger.error(f"Deployment error on attempt {attempt + 1}: {e}")
                
                if attempt < max_retries - 1:
                    # Interruptible wait so stop() can break the retry loop.
                    if self._stop_event.wait(30):
                        return
            
            if not success:
                logger.error(f"Deployment failed after {max_retries} attempts")
            
            # Wait for next scheduled time
            self._stop_event.wait(interval)
    
    def deploy_once(self) -> bool:
        """Execute a single deployment immediately."""
        deployer = self._get_deployer()
        try:
            return deployer.deploy()
        except Exception as e:
            logger.error(f"One-time deployment failed: {e}")
            return False

    async def adeploy_with_retry(self, max_retries: int = 3) -> bool:
        """
        Async variant of deployment retry logic — never blocks the event loop.
        
        Args:
            max_retries: Maximum number of retry attempts
            
        Returns:
            True if deployment succeeded, False otherwise
        """
        deployer = self._get_deployer()
        
        for attempt in range(max_retries):
            try:
                # Run blocking deploy() call in thread pool to avoid blocking event loop
                if await asyncio.to_thread(deployer.deploy):
                    logger.info(f"Deployment successful on attempt {attempt + 1}")
                    return True
                else:
                    logger.warning(f"Deployment failed on attempt {attempt + 1}")
            except (OSError, RuntimeError, ConnectionError) as e:
                logger.exception(f"Deployment error on attempt {attempt + 1}: {e}")
            except Exception as e:
                logger.exception(f"Unexpected deployment error on attempt {attempt + 1}: {e}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(30)  # Wait before retry (cooperative)
        
        logger.error(f"Deployment failed after {max_retries} attempts")
        return False


def create_deployment_scheduler(provider: str = "gcp", config: Optional[Dict[str, Any]] = None) -> DeploymentScheduler:
    """
    Factory function to create a real deployment scheduler for different providers.
    
    Args:
        provider: Deployment provider ("gcp", "aws", "azure", etc.)
        config: Optional configuration dict
        
    Returns:
        Configured DeploymentScheduler instance that uses real deployment logic
    """
    return DeploymentScheduler(provider, config)
