"""
Dependency Checker for Templates.

Checks availability of tools, packages, and environment variables
required by templates. Supports strict mode for fail-fast behavior.
"""

import importlib.util
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .loader import TemplateConfig


class StrictModeError(Exception):
    """Raised when strict mode detects missing dependencies."""
    
    def __init__(self, message: str, missing_items: Dict[str, List[str]]):
        super().__init__(message)
        self.missing_items = missing_items


@dataclass
class DependencyStatus:
    """Status of a single dependency."""
    name: str
    available: bool
    source: Optional[str] = None
    install_hint: Optional[str] = None
    masked_value: Optional[str] = None


class DependencyChecker:
    """
    Checks availability of template dependencies.
    
    Supports checking:
    - Tools (from built-in registry, praisonai-tools, custom dirs)
    - Packages (via importlib.util.find_spec)
    - Environment variables (via os.environ)
    """
    
    # Known tool sources for install hints
    TOOL_INSTALL_HINTS = {
        "youtube_tool": "pip install praisonai-tools[video]",
        "whisper_tool": "pip install praisonai-tools[audio]",
        "vision_tool": "pip install praisonai-tools[vision]",
        "tavily_search": "pip install tavily-python",
    }
    
    def __init__(self, custom_tool_dirs: Optional[List[str]] = None):
        """
        Initialize dependency checker.
        
        Args:
            custom_tool_dirs: Additional directories to search for tools
        """
        self._custom_tool_dirs = custom_tool_dirs or []
        self._tool_cache: Dict[str, DependencyStatus] = {}
    
    def check_tool(self, tool_name: str) -> Dict[str, Any]:
        """
        Check if a tool is available.
        
        Args:
            tool_name: Name of the tool to check
            
        Returns:
            Dict with 'available', 'source', and 'install_hint' keys
        """
        # Check cache first
        if tool_name in self._tool_cache:
            status = self._tool_cache[tool_name]
            return {
                "available": status.available,
                "source": status.source,
                "install_hint": status.install_hint
            }
        
        # Check built-in tools
        source = self._check_builtin_tool(tool_name)
        if source:
            status = DependencyStatus(
                name=tool_name,
                available=True,
                source=source
            )
            self._tool_cache[tool_name] = status
            return {"available": True, "source": source, "install_hint": None}
        
        # Check praisonai-tools
        source = self._check_praisonai_tools(tool_name)
        if source:
            status = DependencyStatus(
                name=tool_name,
                available=True,
                source=source
            )
            self._tool_cache[tool_name] = status
            return {"available": True, "source": source, "install_hint": None}
        
        # Check custom directories
        source = self._check_custom_dirs(tool_name)
        if source:
            status = DependencyStatus(
                name=tool_name,
                available=True,
                source=source
            )
            self._tool_cache[tool_name] = status
            return {"available": True, "source": source, "install_hint": None}
        
        # Tool not found
        install_hint = self.TOOL_INSTALL_HINTS.get(tool_name)
        if not install_hint:
            install_hint = "Check praisonai-tools or define custom tool"
        
        status = DependencyStatus(
            name=tool_name,
            available=False,
            source=None,
            install_hint=install_hint
        )
        self._tool_cache[tool_name] = status
        return {"available": False, "source": None, "install_hint": install_hint}
    
    def _check_builtin_tool(self, tool_name: str) -> Optional[str]:
        """Check if tool exists in built-in registry."""
        try:
            from praisonaiagents.tools import TOOL_MAPPINGS
            if tool_name in TOOL_MAPPINGS:
                return "builtin"
        except ImportError:
            pass
        return None
    
    def _check_praisonai_tools(self, tool_name: str) -> Optional[str]:
        """Check if tool exists in praisonai-tools package."""
        try:
            import praisonai_tools
            if hasattr(praisonai_tools, tool_name):
                return "praisonai-tools"
            # Check for get_tool function
            if hasattr(praisonai_tools, 'get_tool'):
                try:
                    tool = praisonai_tools.get_tool(tool_name)
                    if tool:
                        return "praisonai-tools"
                except Exception:
                    pass
        except ImportError:
            pass
        return None
    
    def _check_custom_dirs(self, tool_name: str) -> Optional[str]:
        """Check if tool exists in custom directories."""
        for dir_path in self._custom_tool_dirs:
            path = Path(dir_path).expanduser()
            if not path.exists():
                continue
            
            # Check for tool file
            tool_file = path / f"{tool_name}.py"
            if tool_file.exists():
                return f"custom:{dir_path}"
            
            # Check for tool in any Python file (by function name)
            for py_file in path.glob("*.py"):
                try:
                    content = py_file.read_text()
                    if f"def {tool_name}" in content:
                        return f"custom:{dir_path}"
                except Exception:
                    pass
        
        return None
    
    def check_package(self, package_name: str) -> Dict[str, Any]:
        """
        Check if a Python package is available.
        
        Args:
            package_name: Name of the package to check
            
        Returns:
            Dict with 'available' and 'install_hint' keys
        """
        spec = importlib.util.find_spec(package_name)
        if spec is not None:
            return {"available": True, "install_hint": None}
        
        return {
            "available": False,
            "install_hint": f"pip install {package_name}"
        }
    
    def check_env_var(self, var_name: str) -> Dict[str, Any]:
        """
        Check if an environment variable is set.
        
        Args:
            var_name: Name of the environment variable
            
        Returns:
            Dict with 'available' and 'masked_value' keys
        """
        value = os.environ.get(var_name)
        if value:
            # Mask the value for security
            if len(value) > 8:
                masked = value[:4] + "*" * (len(value) - 8) + value[-4:]
            else:
                masked = "*" * len(value)
            return {"available": True, "masked_value": masked}
        
        return {"available": False, "masked_value": None}
    
    def check_template_dependencies(
        self,
        template: "TemplateConfig"
    ) -> Dict[str, Any]:
        """
        Check all dependencies for a template.
        
        Args:
            template: Template configuration to check
            
        Returns:
            Dict with 'tools', 'packages', 'env', and 'all_satisfied' keys
        """
        result = {
            "tools": [],
            "packages": [],
            "env": [],
            "all_satisfied": True
        }
        
        # Check tools
        tools = template.requires.get("tools", [])
        if isinstance(tools, str):
            tools = [tools]
        
        for tool_name in tools:
            status = self.check_tool(tool_name)
            result["tools"].append({
                "name": tool_name,
                **status
            })
            if not status["available"]:
                result["all_satisfied"] = False
        
        # Check packages
        packages = template.requires.get("packages", [])
        if isinstance(packages, str):
            packages = [packages]
        
        for pkg_name in packages:
            status = self.check_package(pkg_name)
            result["packages"].append({
                "name": pkg_name,
                **status
            })
            if not status["available"]:
                result["all_satisfied"] = False
        
        # Check environment variables
        env_vars = template.requires.get("env", [])
        if isinstance(env_vars, str):
            env_vars = [env_vars]
        
        for var_name in env_vars:
            status = self.check_env_var(var_name)
            result["env"].append({
                "name": var_name,
                **status
            })
            if not status["available"]:
                result["all_satisfied"] = False
        
        return result
    
    def get_install_hints(self, template: "TemplateConfig") -> List[str]:
        """
        Get install hints for missing dependencies.
        
        Args:
            template: Template configuration to check
            
        Returns:
            List of actionable install hints
        """
        hints = []
        deps = self.check_template_dependencies(template)
        
        # Tool hints
        for tool in deps["tools"]:
            if not tool["available"] and tool.get("install_hint"):
                hints.append(f"Tool '{tool['name']}': {tool['install_hint']}")
        
        # Package hints
        for pkg in deps["packages"]:
            if not pkg["available"] and pkg.get("install_hint"):
                hints.append(f"Package '{pkg['name']}': {pkg['install_hint']}")
        
        # Env hints
        for env in deps["env"]:
            if not env["available"]:
                hints.append(f"Environment variable '{env['name']}': export {env['name']}=<value>")
        
        return hints
    
    def enforce_strict_mode(self, template: "TemplateConfig") -> bool:
        """
        Enforce strict mode - fail if any dependency is missing.
        
        Args:
            template: Template configuration to check
            
        Returns:
            True if all dependencies satisfied
            
        Raises:
            StrictModeError: If any dependency is missing
        """
        deps = self.check_template_dependencies(template)
        
        if deps["all_satisfied"]:
            return True
        
        # Collect missing items
        missing = {
            "tools": [t["name"] for t in deps["tools"] if not t["available"]],
            "packages": [p["name"] for p in deps["packages"] if not p["available"]],
            "env": [e["name"] for e in deps["env"] if not e["available"]]
        }
        
        # Build error message
        messages = []
        if missing["tools"]:
            messages.append(f"Missing tools: {', '.join(missing['tools'])}")
        if missing["packages"]:
            messages.append(f"Missing packages: {', '.join(missing['packages'])}")
        if missing["env"]:
            messages.append(f"Missing environment variables: {', '.join(missing['env'])}")
        
        # Add hints
        hints = self.get_install_hints(template)
        if hints:
            messages.append("\nTo fix:")
            messages.extend(f"  - {hint}" for hint in hints)
        
        raise StrictModeError(
            "\n".join(messages),
            missing_items=missing
        )
