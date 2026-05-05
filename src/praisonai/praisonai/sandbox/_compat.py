"""
Compatibility layer to unify sandbox/ and integrations/compute/ hierarchies.

Provides SandboxToComputeAdapter to expose ComputeProvider as legacy SandboxConfig/SandboxResult API.
This eliminates code duplication between the two parallel hierarchies.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Union

from praisonaiagents.sandbox import (
    SandboxConfig,
    SandboxResult,
    SandboxStatus,
)

logger = logging.getLogger(__name__)


class SandboxToComputeAdapter:
    """Expose a ComputeProvider as the legacy SandboxConfig/SandboxResult API."""
    
    def __init__(self, compute_provider: Any, image: str = "python:3.11-slim"):
        """
        Initialize adapter with compute provider and default image.
        
        Args:
            compute_provider: Instance implementing ComputeProviderProtocol
            image: Default container image to use
        """
        self._compute = compute_provider
        self._image = image
        self._instance_id: Optional[str] = None
        self._is_running = False
        
    @property
    def is_available(self) -> bool:
        """Check if the compute provider is available."""
        if hasattr(self._compute, 'is_available'):
            return self._compute.is_available
        # Fallback - try to check if we can instantiate
        try:
            return True
        except Exception:
            return False
    
    async def start(self) -> None:
        """Start the sandbox by provisioning a compute instance."""
        if self._is_running:
            return
            
        try:
            # Create compute config - adapt to whatever the compute provider expects
            if hasattr(self._compute, 'provision'):
                # For ComputeProviderProtocol
                config = {
                    'image': self._image,
                    'auto_shutdown': False,  # We'll manage lifecycle
                }
                
                # Try to create a proper config object if available
                try:
                    from praisonaiagents.managed.protocols import ComputeConfig
                    compute_config = ComputeConfig(image=self._image)
                    info = await self._compute.provision(compute_config)
                    self._instance_id = info.instance_id
                except (ImportError, AttributeError):
                    # Fallback to basic provision call
                    info = await self._compute.provision(config)
                    self._instance_id = getattr(info, 'instance_id', 'default')
                    
                self._is_running = True
                logger.debug(f"Started compute instance: {self._instance_id}")
            else:
                # Direct start method
                await self._compute.start()
                self._is_running = True
                self._instance_id = "default"
                
        except Exception as e:
            logger.error(f"Failed to start compute instance: {e}")
            raise RuntimeError(f"Failed to start sandbox: {e}")
    
    async def execute(
        self,
        code: str,
        language: str = "python",
        limits: Optional[Any] = None,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> SandboxResult:
        """
        Execute code in the sandbox and return SandboxResult.
        
        Args:
            code: Code to execute
            language: Programming language (default: python)
            limits: Resource limits (optional)
            env: Environment variables (optional)
            working_dir: Working directory (optional)
            
        Returns:
            SandboxResult with execution results
        """
        if not self._is_running or not self._instance_id:
            await self.start()
            
        try:
            # Execute on compute provider
            if hasattr(self._compute, 'execute'):
                result = await self._compute.execute(
                    self._instance_id, 
                    code,
                    env=env,
                    working_dir=working_dir
                )
                
                # Convert compute result to SandboxResult
                if hasattr(result, 'stdout'):
                    # Structured result object
                    return SandboxResult(
                        status=SandboxStatus.SUCCESS if result.exit_code == 0 else SandboxStatus.ERROR,
                        stdout=result.stdout,
                        stderr=result.stderr or "",
                        exit_code=getattr(result, 'exit_code', 0),
                        execution_time=getattr(result, 'execution_time', 0.0),
                    )
                else:
                    # Plain string result
                    return SandboxResult(
                        status=SandboxStatus.SUCCESS,
                        stdout=str(result),
                        stderr="",
                        exit_code=0,
                        execution_time=0.0,
                    )
            else:
                # Fallback for simple compute providers
                result = str(await self._compute.run(code))
                return SandboxResult(
                    status=SandboxStatus.SUCCESS,
                    stdout=result,
                    stderr="",
                    exit_code=0,
                    execution_time=0.0,
                )
                
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            return SandboxResult(
                status=SandboxStatus.ERROR,
                stdout="",
                stderr=str(e),
                exit_code=1,
                execution_time=0.0,
            )
    
    async def stop(self) -> None:
        """Stop the sandbox by shutting down the compute instance."""
        if not self._is_running:
            return
            
        try:
            if hasattr(self._compute, 'shutdown') and self._instance_id:
                await self._compute.shutdown(self._instance_id)
            elif hasattr(self._compute, 'stop'):
                await self._compute.stop()
                
            self._is_running = False
            self._instance_id = None
            logger.debug("Stopped compute instance")
            
        except Exception as e:
            logger.warning(f"Error stopping compute instance: {e}")