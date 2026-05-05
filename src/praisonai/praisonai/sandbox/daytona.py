"""
Daytona Sandbox implementation for PraisonAI.

Uses the unified compute provider via adapter to eliminate duplication.
"""

from __future__ import annotations

import logging
from typing import Optional

from praisonaiagents.sandbox import SandboxConfig
from ._compat import SandboxToComputeAdapter

logger = logging.getLogger(__name__)


class DaytonaSandbox(SandboxToComputeAdapter):
    """Daytona-based sandbox for safe code execution.
    
    Executes code in isolated Daytona workspaces using the unified compute provider.
    Eliminates duplication between sandbox/ and integrations/compute/ hierarchies.
    
    Example:
        from praisonai.sandbox import DaytonaSandbox
        
        sandbox = DaytonaSandbox()
        result = await sandbox.execute("print('Hello, World!')")
        print(result.stdout)  # Hello, World!
    
    Requires: Daytona CLI and workspace access
    """
    
    def __init__(
        self,
        workspace_name: str = None,
        config: Optional[SandboxConfig] = None,
    ):
        """Initialize the Daytona sandbox.
        
        Args:
            workspace_name: Daytona workspace name
            config: Optional sandbox configuration
        """
        # Use the compute provider from integrations/compute/
        from praisonai.integrations.compute.daytona import DaytonaCompute
        
        # Initialize the adapter with the compute provider
        super().__init__(DaytonaCompute(), image="daytona-workspace")
        self.config = config or SandboxConfig.daytona(workspace_name)
        self.workspace_name = workspace_name
    
    @property
    def sandbox_type(self) -> str:
        return "daytona"