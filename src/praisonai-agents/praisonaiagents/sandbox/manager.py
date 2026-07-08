"""
SandboxManager for PraisonAI Agents.

Factory and context manager for sandbox backends.
Core SDK component that routes to appropriate sandbox implementations
in the praisonai wrapper package.
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional, TYPE_CHECKING

from .config import SandboxConfig
from .protocols import SandboxProtocol, SandboxResult

if TYPE_CHECKING:
    from typing import AsyncContextManager

logger = logging.getLogger(__name__)


class SandboxManager:
    """Factory and context manager for all sandbox backends.
    
    Routes to appropriate sandbox implementations based on configuration.
    Lightweight manager in core SDK - heavy implementations in wrapper.
    
    Example:
        from praisonaiagents.sandbox import SandboxManager, SandboxConfig
        
        # Simple usage
        config = SandboxConfig.docker("python:3.11-slim")
        manager = SandboxManager(config)
        result = await manager.run_code("print('Hello, World!')")
        
        # Context manager usage  
        async with SandboxManager(config) as sandbox:
            result = await sandbox.execute("print('Hello, World!')")
    """
    
    def __init__(self, config: Optional[SandboxConfig] = None):
        """Initialize the sandbox manager.
        
        Args:
            config: Sandbox configuration. Defaults to subprocess sandbox.
        """
        self.config = config or SandboxConfig.subprocess()
        self._sandbox: Optional[SandboxProtocol] = None
        
    async def __aenter__(self) -> SandboxProtocol:
        """Async context manager entry."""
        self._sandbox = await self._create_sandbox()
        return self._sandbox
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup."""
        if self._sandbox:
            try:
                await self._sandbox.stop()
                await self._sandbox.cleanup()
            except Exception as e:
                logger.warning(f"Error during sandbox cleanup: {e}")
            finally:
                self._sandbox = None
    
    async def run_code(
        self, 
        code: str,
        language: str = "python",
        **kwargs
    ) -> SandboxResult:
        """Convenience method: create sandbox, run code, cleanup.
        
        Args:
            code: Code to execute
            language: Programming language
            **kwargs: Additional arguments passed to execute()
            
        Returns:
            SandboxResult with execution details
        """
        async with self as sandbox:
            return await sandbox.execute(code, language=language, **kwargs)
    
    async def _create_sandbox(self) -> SandboxProtocol:
        """Create appropriate sandbox backend based on config.
        
        Routes to implementations in praisonai wrapper package.
        
        Returns:
            Configured sandbox instance
            
        Raises:
            ValueError: For unknown sandbox types
            ImportError: If required dependencies not available
        """
        sandbox_type = self.config.sandbox_type.lower()
        
        if sandbox_type == "docker":
            return await self._create_docker_sandbox()
        elif sandbox_type in ("subprocess", "local"):
            return await self._create_subprocess_sandbox()  
        elif sandbox_type == "e2b":
            return await self._create_e2b_sandbox()
        elif sandbox_type == "sandlock":
            return await self._create_sandlock_sandbox()
        elif sandbox_type == "ssh":
            return await self._create_ssh_sandbox()
        elif sandbox_type == "modal":
            return await self._create_modal_sandbox()
        elif sandbox_type == "daytona":
            return await self._create_daytona_sandbox()
        elif sandbox_type == "capsule":
            return await self._create_capsule_sandbox()
        else:
            raise ValueError(
                f"Unknown sandbox type: {sandbox_type!r}. "
                f"Supported: 'docker', 'subprocess', 'e2b', 'sandlock', 'ssh', 'modal', 'daytona', 'capsule'"
            )
    
    async def _create_docker_sandbox(self) -> SandboxProtocol:
        """Create Docker sandbox."""
        try:
            # Lazy import from wrapper package
            from praisonai.sandbox import DockerSandbox
        except ImportError as e:
            raise ImportError(
                "Docker sandbox not available. Install with: "
                "pip install praisonaiagents[sandbox-docker]"
            ) from e
        
        sandbox = DockerSandbox(
            image=self.config.image,
            config=self.config,
        )
        
        if not sandbox.is_available:
            raise RuntimeError(
                "Docker is not available. Please install Docker and ensure it's running."
            )
        
        await sandbox.start()
        return sandbox
    
    async def _create_subprocess_sandbox(self) -> SandboxProtocol:
        """Create subprocess sandbox."""
        try:
            from praisonai.sandbox import SubprocessSandbox
        except ImportError as e:
            raise ImportError(
                "Subprocess sandbox not available. This should not happen - "
                "please check your installation."
            ) from e
        
        sandbox = SubprocessSandbox(config=self.config)
        await sandbox.start()
        return sandbox
    
    async def _create_e2b_sandbox(self) -> SandboxProtocol:
        """Create E2B sandbox."""
        try:
            from praisonai.sandbox import E2BSandbox
        except ImportError as e:
            raise ImportError(
                "E2B sandbox not available. Install with: "
                "pip install praisonaiagents[sandbox] e2b-code-interpreter"
            ) from e
        
        sandbox = E2BSandbox(config=self.config)
        
        if not sandbox.is_available:
            raise RuntimeError(
                "E2B is not available. Please set E2B_API_KEY environment variable."
            )
        
        await sandbox.start()
        return sandbox
    
    async def _create_sandlock_sandbox(self) -> SandboxProtocol:
        """Create Sandlock sandbox.""" 
        try:
            from praisonai.sandbox import SandlockSandbox
        except ImportError as e:
            raise ImportError(
                "Sandlock sandbox not available. Install sandlock."
            ) from e
        
        sandbox = SandlockSandbox(config=self.config)
        await sandbox.start()
        return sandbox
        
    async def _create_ssh_sandbox(self) -> SandboxProtocol:
        """Create SSH sandbox."""
        try:
            from praisonai.sandbox import SSHSandbox
        except ImportError as e:
            raise ImportError(
                "SSH sandbox not available. Install with: "
                "pip install paramiko"
            ) from e
        
        sandbox = SSHSandbox(config=self.config)
        await sandbox.start()
        return sandbox
        
    async def _create_modal_sandbox(self) -> SandboxProtocol:
        """Create Modal sandbox."""
        try:
            from praisonai.sandbox import ModalSandbox
        except ImportError as e:
            raise ImportError(
                "Modal sandbox not available. Install with: "
                "pip install modal"
            ) from e
        
        sandbox = ModalSandbox(config=self.config)
        await sandbox.start()
        return sandbox
        
    async def _create_daytona_sandbox(self) -> SandboxProtocol:
        """Create Daytona sandbox."""
        try:
            from praisonai.sandbox import DaytonaSandbox
        except ImportError as e:
            raise ImportError(
                "Daytona sandbox not available. Install daytona client."
            ) from e
        
        sandbox = DaytonaSandbox(config=self.config)
        await sandbox.start()
        return sandbox

    async def _create_capsule_sandbox(self) -> SandboxProtocol:
        """Create Capsule sandbox."""
        try:
            from praisonai.sandbox import CapsuleSandbox
        except ImportError as e:
            raise ImportError(
                "Capsule sandbox not available. Install with: "
                "pip install praisonai[capsule]"
            ) from e

        sandbox = CapsuleSandbox(config=self.config)

        if not sandbox.is_available:
            raise RuntimeError(
                "Capsule is not available. Install with: pip install praisonai[capsule]"
            )

        await sandbox.start()
        return sandbox

    def get_available_types(self) -> Dict[str, Dict[str, Any]]:
        """Get available sandbox types and their status.
        
        Returns:
            Dictionary mapping sandbox types to availability info
        """
        types = {}
        
        # Check Docker
        try:
            from praisonai.sandbox import DockerSandbox
            docker = DockerSandbox()
            types["docker"] = {
                "available": docker.is_available,
                "description": "Isolated Docker containers",
                "requires": ["docker"],
            }
        except ImportError:
            types["docker"] = {
                "available": False,
                "description": "Isolated Docker containers", 
                "requires": ["docker", "praisonaiagents[sandbox-docker]"],
            }
        
        # Check subprocess (always available)
        types["subprocess"] = {
            "available": True,
            "description": "Local subprocess (limited isolation)",
            "requires": [],
        }
        
        # Check E2B
        try:
            from praisonai.sandbox import E2BSandbox
            e2b = E2BSandbox()
            types["e2b"] = {
                "available": e2b.is_available,
                "description": "E2B cloud sandboxes",
                "requires": ["e2b-code-interpreter", "E2B_API_KEY"],
            }
        except ImportError:
            types["e2b"] = {
                "available": False,
                "description": "E2B cloud sandboxes",
                "requires": ["e2b-code-interpreter", "E2B_API_KEY"],
            }
        
        # Add other types with try/except blocks
        for sandbox_type, module_name, description, requirements in [
            ("sandlock", "SandlockSandbox", "OS-native sandboxing", ["sandlock"]),
            ("ssh", "SSHSandbox", "Remote SSH execution", ["paramiko"]),
            ("modal", "ModalSandbox", "Modal cloud compute", ["modal"]),
            ("daytona", "DaytonaSandbox", "Daytona workspaces", ["daytona"]),
            ("capsule", "CapsuleSandbox", "Lightweight WebAssembly isolation", ["capsule"]),
        ]:
            try:
                from praisonai import sandbox
                sandbox_class = getattr(sandbox, module_name)
                # Check if class exists without instantiating (some need required args)
                types[sandbox_type] = {
                    "available": False,  # Can't easily check without required args
                    "description": description,
                    "requires": requirements,
                }
            except (ImportError, AttributeError):
                types[sandbox_type] = {
                    "available": False,
                    "description": description,
                    "requires": requirements,
                }
        
        return types