"""
Docker Sandbox implementation for PraisonAI.

Uses the unified compute provider via adapter to eliminate duplication.
"""

from __future__ import annotations

import logging
from typing import Optional

from praisonaiagents.sandbox import SandboxConfig
from ._compat import SandboxToComputeAdapter

logger = logging.getLogger(__name__)


class DockerSandbox(SandboxToComputeAdapter):
    """Docker-based sandbox for safe code execution.
    
    Executes code in isolated Docker containers using the unified compute provider.
    Eliminates duplication between sandbox/ and integrations/compute/ hierarchies.
    
    Example:
        from praisonai.sandbox import DockerSandbox
        
        sandbox = DockerSandbox(image="python:3.11-slim")
        result = await sandbox.execute("print('Hello, World!')")
        print(result.stdout)  # Hello, World!
    
    Requires: Docker installed and running
    """
    
    def __init__(
        self,
        image: str = "python:3.11-slim",
        config: Optional[SandboxConfig] = None,
    ):
        """Initialize the Docker sandbox.
        
        Args:
            image: Docker image to use
            config: Optional sandbox configuration
        """
        # Use the compute provider from integrations/compute/
        from praisonai.integrations.compute.docker import DockerCompute
        
        # Initialize the adapter with the compute provider
        super().__init__(DockerCompute(), image=image)
        self.config = config or SandboxConfig.docker(image)
    
    @property
    def sandbox_type(self) -> str:
        return "docker"