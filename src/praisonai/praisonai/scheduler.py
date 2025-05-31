import re
import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Union, Optional, Callable, Dict, Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class DeployerInterface(ABC):
    """Abstract interface for deployers to ensure provider compatibility."""
    
    @abstractmethod
    def deploy(self) -> bool:
        """Execute deployment. Returns True on success, False on failure."""
        pass

class CloudDeployerAdapter(DeployerInterface):
    """Adapter for existing CloudDeployer to match interface."""
    
    def __init__(self):
        from .deploy import CloudDeployer
        self._deployer = CloudDeployer()
    
    def deploy(self) -> bool:
        """Execute deployment using CloudDeployer."""
        try:
            self._deployer.run_commands()
            return True
        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            return False

class ScheduleParser:
    """Parse schedule expressions into intervals."""
    
    @staticmethod
    def parse(schedule_expr: str) -> int:
        """
        Parse schedule expression and return interval in seconds.
        
        Supported formats:
        - "daily" -> 86400 seconds
        - "hourly" -> 3600 seconds
        - "*/30m" -> 1800 seconds (every 30 minutes)
        - "*/6h" -> 21600 seconds (every 6 hours)
        - "60" -> 60 seconds (plain number)
        """
        schedule_expr = schedule_expr.strip().lower()
        
        if schedule_expr == "daily":
            return 86400
        elif schedule_expr == "hourly":
            return 3600
        elif schedule_expr.isdigit():
            return int(schedule_expr)
        elif schedule_expr.startswith("*/"):
            # Handle */30m, */6h patterns
            interval_part = schedule_expr[2:]
            if interval_part.endswith("m"):
                minutes = int(interval_part[:-1])
                return minutes * 60
            elif interval_part.endswith("h"):
                hours = int(interval_part[:-1])
                return hours * 3600
            elif interval_part.endswith("s"):
                return int(interval_part[:-1])
            else:
                return int(interval_part)
        else:
            raise ValueError(f"Unsupported schedule format: {schedule_expr}")

class DeploymentScheduler:
    """
    Minimal deployment scheduler with provider-agnostic design.
    
    Features:
    - Simple interval-based scheduling
    - Thread-safe operation
    - Extensible deployer factory pattern
    - Minimal dependencies
    """
    
    def __init__(self, schedule_config: Optional[Dict[str, Any]] = None):
        self.config = schedule_config or {}
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
        
        # Default to CloudDeployer for backward compatibility
        return CloudDeployerAdapter()
    
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
                    time.sleep(30)  # Wait before retry
            
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

def create_scheduler(provider: str = "gcp", config: Optional[Dict[str, Any]] = None) -> DeploymentScheduler:
    """
    Factory function to create scheduler for different providers.
    
    Args:
        provider: Deployment provider ("gcp", "aws", "azure", etc.)
        config: Optional configuration dict
        
    Returns:
        Configured DeploymentScheduler instance
    """
    scheduler = DeploymentScheduler(config)
    
    # Provider-specific deployer setup can be added here
    if provider == "gcp":
        # Default CloudDeployer for GCP
        pass
    elif provider == "aws":
        # Future: AWS deployer implementation
        logger.warning("AWS provider not yet implemented, using default")
    elif provider == "azure":
        # Future: Azure deployer implementation  
        logger.warning("Azure provider not yet implemented, using default")
    else:
        logger.warning(f"Unknown provider {provider}, using default")
    
    return scheduler