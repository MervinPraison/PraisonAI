"""Capability validation for Agent Skills.

This module implements the capability gate enforcement system for skills,
checking that required tools, servers, and environment variables are available
before allowing skill activation.
"""

import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum

from .models import SkillProperties, SkillRequirements, SkillState

logger = logging.getLogger(__name__)


class EnforcementLevel(Enum):
    """Enforcement level for capability gates."""
    DISABLED = "disabled"      # No enforcement (existing behavior)
    TELEMETRY = "telemetry"    # Log only, no blocking
    WARN = "warn"              # Warning but allow activation
    STRICT = "strict"          # Hard failure, block activation


@dataclass
class ValidationResult:
    """Result of capability validation for a skill."""
    skill_name: str
    state: SkillState
    satisfied_tools: List[str]
    missing_tools: List[str]
    satisfied_servers: List[str]
    missing_servers: List[str]
    satisfied_env_vars: List[str]
    missing_env_vars: List[str]
    warnings: List[str]
    errors: List[str]
    
    @property
    def is_fully_satisfied(self) -> bool:
        """Check if all requirements are satisfied."""
        return not any([
            self.missing_tools,
            self.missing_servers, 
            self.missing_env_vars,
            self.errors
        ])
    
    @property
    def has_critical_missing(self) -> bool:
        """Check if critical requirements are missing (tools, servers)."""
        return bool(self.missing_tools or self.missing_servers)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "skill_name": self.skill_name,
            "state": self.state.value,
            "satisfied_tools": self.satisfied_tools,
            "missing_tools": self.missing_tools,
            "satisfied_servers": self.satisfied_servers,
            "missing_servers": self.missing_servers,
            "satisfied_env_vars": self.satisfied_env_vars,
            "missing_env_vars": self.missing_env_vars,
            "warnings": self.warnings,
            "errors": self.errors,
            "is_fully_satisfied": self.is_fully_satisfied,
            "has_critical_missing": self.has_critical_missing
        }


class CapabilityValidator:
    """Validates skill requirements against available capabilities.
    
    This is the core capability gate enforcement engine. It checks skill
    requirements against the runtime context (available tools, servers, etc.)
    and determines whether a skill should be activated based on policy.
    """
    
    def __init__(self, enforcement_level: EnforcementLevel = EnforcementLevel.WARN):
        """Initialize the validator.
        
        Args:
            enforcement_level: How strictly to enforce requirements
        """
        self.enforcement_level = enforcement_level
        self._tool_cache: Optional[Set[str]] = None
        self._server_cache: Optional[Set[str]] = None
    
    def validate_skill(
        self,
        skill: SkillProperties,
        available_tools: Optional[Set[str]] = None,
        available_servers: Optional[Set[str]] = None
    ) -> ValidationResult:
        """Validate a skill's requirements against available capabilities.
        
        Args:
            skill: Skill to validate
            available_tools: Set of available tool names (auto-detected if None)
            available_servers: Set of available server names (auto-detected if None)
            
        Returns:
            ValidationResult with validation status and details
        """
        if not skill.requirements or skill.requirements.is_empty():
            # No requirements specified - skill is always available
            return ValidationResult(
                skill_name=skill.name,
                state=SkillState.ACTIVE,
                satisfied_tools=[],
                missing_tools=[],
                satisfied_servers=[],
                missing_servers=[],
                satisfied_env_vars=[],
                missing_env_vars=[],
                warnings=[],
                errors=[]
            )
        
        # Get available capabilities
        if available_tools is None:
            available_tools = self._get_available_tools()
        if available_servers is None:
            available_servers = self._get_available_servers()
            
        requirements = skill.requirements
        
        # Validate tools
        satisfied_tools = [tool for tool in requirements.tools if tool in available_tools]
        missing_tools = [tool for tool in requirements.tools if tool not in available_tools]
        
        # Validate servers
        satisfied_servers = [srv for srv in requirements.servers if srv in available_servers]
        missing_servers = [srv for srv in requirements.servers if srv not in available_servers]
        
        # Validate environment variables
        satisfied_env_vars = [var for var in requirements.env_vars if os.getenv(var)]
        missing_env_vars = [var for var in requirements.env_vars if not os.getenv(var)]
        
        # Determine warnings and errors
        warnings = []
        errors = []
        
        if missing_tools:
            msg = f"Missing required tools: {', '.join(missing_tools)}"
            if self.enforcement_level in (EnforcementLevel.STRICT,):
                errors.append(msg)
            else:
                warnings.append(msg)
                
        if missing_servers:
            msg = f"Missing required servers: {', '.join(missing_servers)}"
            if self.enforcement_level in (EnforcementLevel.STRICT,):
                errors.append(msg)
            else:
                warnings.append(msg)
                
        if missing_env_vars:
            msg = f"Missing required environment variables: {', '.join(missing_env_vars)}"
            if self.enforcement_level == EnforcementLevel.STRICT:
                errors.append(msg)
            else:
                warnings.append(msg)
        
        # Determine skill state
        if errors:
            state = SkillState.UNAVAILABLE
        elif warnings:
            state = SkillState.DEGRADED
        else:
            state = SkillState.ACTIVE
            
        result = ValidationResult(
            skill_name=skill.name,
            state=state,
            satisfied_tools=satisfied_tools,
            missing_tools=missing_tools,
            satisfied_servers=satisfied_servers,
            missing_servers=missing_servers,
            satisfied_env_vars=satisfied_env_vars,
            missing_env_vars=missing_env_vars,
            warnings=warnings,
            errors=errors
        )
        
        # Log based on enforcement level
        self._log_validation_result(result)
        
        return result
    
    def _get_available_tools(self) -> Set[str]:
        """Get set of available tool names from registry."""
        if self._tool_cache is None:
            try:
                from ..tools.registry import get_registry
                registry = get_registry()
                self._tool_cache = set(registry.list_tools())
            except ImportError:
                logger.debug("Tool registry not available")
                self._tool_cache = set()
        return self._tool_cache
    
    def _get_available_servers(self) -> Set[str]:
        """Get set of available MCP server names from the active MCP registry.

        The MCP registry is populated dynamically as servers connect during a
        run, so this is read live (not cached) to avoid a stale snapshot that
        would keep rejecting servers registered after the first validation
        (issue #3307). The read is a cheap set copy under a lock.
        """
        try:
            from ..mcp.mcp import MCP
            return set(MCP.list_active_server_names())
        except ImportError:
            logger.debug("MCP not available")
            return set()
    
    def _log_validation_result(self, result: ValidationResult) -> None:
        """Log validation result based on enforcement level."""
        if self.enforcement_level == EnforcementLevel.DISABLED:
            return
            
        skill_name = result.skill_name
        
        if result.state == SkillState.UNAVAILABLE:
            if self.enforcement_level == EnforcementLevel.STRICT:
                logger.error(f"Skill '{skill_name}' blocked: {'; '.join(result.errors)}")
            else:
                logger.warning(f"Skill '{skill_name}' has critical missing dependencies: {'; '.join(result.errors)}")
                
        elif result.state == SkillState.DEGRADED:
            logger.warning(f"Skill '{skill_name}' partially available: {'; '.join(result.warnings)}")
            
        elif result.state == SkillState.ACTIVE:
            logger.debug(f"Skill '{skill_name}' requirements satisfied")
            
    def clear_cache(self) -> None:
        """Clear cached capability information."""
        self._tool_cache = None
        self._server_cache = None
