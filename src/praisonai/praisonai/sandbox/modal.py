"""
Modal Sandbox implementation for PraisonAI.

Uses the unified compute provider via adapter to eliminate duplication.
"""

from __future__ import annotations

import logging
from typing import Optional

from praisonaiagents.sandbox import SandboxConfig
from ._compat import SandboxToComputeAdapter

logger = logging.getLogger(__name__)


class ModalSandbox(SandboxToComputeAdapter):
    """Modal-based sandbox for serverless code execution.
    
    Executes code on Modal's serverless platform using the unified compute provider.
    Eliminates duplication between sandbox/ and integrations/compute/ hierarchies.
    
    Example:
        from praisonai.sandbox import ModalSandbox
        
        sandbox = ModalSandbox()
        result = await sandbox.execute("print('Hello, World!')")
        print(result.stdout)  # Hello, World!
    
    Requires: Modal token and account setup
    """
    
    def __init__(
        self,
        image: str = "python:3.11-slim",
        config: Optional[SandboxConfig] = None,
    ):
        """Initialize the Modal sandbox.
        
        Args:
            image: Container image to use on Modal
            config: Optional sandbox configuration
        """
        # Use the compute provider from integrations/compute/
        from praisonai.integrations.compute.modal_compute import ModalCompute
        
        # Initialize the adapter with the compute provider
        super().__init__(ModalCompute(), image=image)
        self.config = config or SandboxConfig.modal(image)
    
    @property
    def sandbox_type(self) -> str:
        return "modal"