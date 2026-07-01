"""
Runtime compatibility checks for multi-agent setups.

Provides preflight validation for team YAML configurations to detect
runtime conflicts, missing capabilities, and handoff compatibility issues.
"""

import yaml
import os
from typing import Any, Dict, List, Optional, Set, Iterator
from dataclasses import dataclass

from ..models import CheckResult, CheckStatus, CheckCategory, CheckSeverity
from ..registry import CheckRegistry


@dataclass
class RuntimeCapability:
    """Represents a runtime capability requirement."""
    name: str
    description: str
    required: bool = True


@dataclass
class RuntimeInfo:
    """Information about a specific runtime."""
    id: str
    name: str
    available: bool
    capabilities: List[RuntimeCapability]
    supports_handoff: bool = False
    supports_tool_loop: bool = False


@dataclass
class AgentRuntimeConfig:
    """Runtime configuration for a specific agent."""
    role_name: str
    runtime_id: Optional[str]
    resolved_runtime: Optional[str]
    capabilities_needed: Set[str]
    handoff_targets: List[str]
    has_tools: bool


class RuntimeCompatibilityChecker:
    """Checks runtime compatibility for multi-agent setups."""
    
    def __init__(self):
        self.known_runtimes = self._get_known_runtimes()
    
    def _get_known_runtimes(self) -> Dict[str, RuntimeInfo]:
        """Get information about known runtimes."""
        runtimes = {}
        
        # Check framework availability using the same pattern as agents_generator
        try:
            from praisonai._framework_availability import is_available
        except ImportError:
            is_available = lambda x: False

        # Adapter-aware availability: a runtime is only "usable" if its adapter
        # is both installed AND implemented/registered. This keeps `doctor` in
        # sync with the registry-backed `--framework` choices so it never
        # reports a runtime as available when the matching framework cannot run
        # (e.g. unimplemented AutoGen v0.4 / AG2 entry-point placeholders).
        def _runtime_usable(framework_name: str, package_name: str) -> bool:
            try:
                from praisonai.framework_adapters.registry import get_default_registry
            except ImportError:
                # Fallback to raw package probe only when the registry module
                # itself cannot be imported (e.g. partial install).
                return is_available(package_name)

            registry = get_default_registry()
            # When the registry is the source of truth, an unregistered
            # framework is not runnable even if its packages are installed,
            # so doctor stays consistent with the `--framework` choices.
            if framework_name not in registry.list_names():
                return False
            return registry.is_available(framework_name)
        
        # PraisonAI Agents runtime
        runtimes['praisonai'] = RuntimeInfo(
            id='praisonai',
            name='PraisonAI Agents',
            available=is_available('praisonaiagents'),
            capabilities=[
                RuntimeCapability('agent_creation', 'Create and manage agents'),
                RuntimeCapability('tool_execution', 'Execute tools and functions'),
                RuntimeCapability('handoff_support', 'Agent-to-agent handoffs'),
                RuntimeCapability('context_sharing', 'Share conversation context'),
                RuntimeCapability('cli_backend', 'CLI backend integration'),
            ],
            supports_handoff=True,
            supports_tool_loop=True
        )
        
        # CrewAI runtime
        runtimes['crewai'] = RuntimeInfo(
            id='crewai',
            name='CrewAI',
            available=is_available('crewai'),
            capabilities=[
                RuntimeCapability('agent_creation', 'Create and manage agents'),
                RuntimeCapability('tool_execution', 'Execute tools and functions'),
                RuntimeCapability('sequential_execution', 'Sequential task execution'),
                RuntimeCapability('hierarchical_execution', 'Hierarchical task execution'),
            ],
            supports_handoff=False,
            supports_tool_loop=True
        )
        
        # AutoGen v0.2 runtime
        runtimes['autogen'] = RuntimeInfo(
            id='autogen',
            name='AutoGen v0.2',
            available=is_available('autogen'),
            capabilities=[
                RuntimeCapability('agent_creation', 'Create and manage agents'),
                RuntimeCapability('tool_execution', 'Execute tools and functions'),
                RuntimeCapability('group_chat', 'Multi-agent conversations'),
            ],
            supports_handoff=False,
            supports_tool_loop=True
        )
        
        # AutoGen v0.4 runtime (optional entry-point adapter)
        runtimes['autogen_v4'] = RuntimeInfo(
            id='autogen_v4',
            name='AutoGen v0.4',
            available=_runtime_usable('autogen_v4', 'autogen_v4'),
            capabilities=[
                RuntimeCapability('agent_creation', 'Create and manage agents'),
                RuntimeCapability('tool_execution', 'Execute tools and functions'),
                RuntimeCapability('handoff_support', 'Agent-to-agent handoffs', required=False),
            ],
            supports_handoff=True,
            supports_tool_loop=True
        )
        
        # AG2 runtime (optional entry-point adapter)
        runtimes['ag2'] = RuntimeInfo(
            id='ag2',
            name='AG2 (AutoGen Next)',
            available=_runtime_usable('ag2', 'ag2'),
            capabilities=[
                RuntimeCapability('agent_creation', 'Create and manage agents'),
                RuntimeCapability('tool_execution', 'Execute tools and functions'),
            ],
            supports_handoff=False,
            supports_tool_loop=True
        )

        runtimes['langgraph'] = RuntimeInfo(
            id='langgraph',
            name='LangGraph',
            available=_runtime_usable('langgraph', 'langgraph'),
            capabilities=[
                RuntimeCapability('agent_creation', 'Create and manage agents'),
                RuntimeCapability('tool_execution', 'Execute tools and functions'),
                RuntimeCapability('sequential_execution', 'Sequential task execution'),
            ],
            supports_handoff=False,
            supports_tool_loop=True
        )

        runtimes['openai_agents'] = RuntimeInfo(
            id='openai_agents',
            name='OpenAI Agents SDK',
            available=_runtime_usable('openai_agents', 'openai_agents'),
            capabilities=[
                RuntimeCapability('agent_creation', 'Create and manage agents'),
                RuntimeCapability('tool_execution', 'Execute tools and functions'),
                RuntimeCapability('handoff_support', 'Agent-to-agent handoffs', required=False),
            ],
            supports_handoff=True,
            supports_tool_loop=True
        )

        runtimes['agno'] = RuntimeInfo(
            id='agno',
            name='Agno',
            available=_runtime_usable('agno', 'agno'),
            capabilities=[
                RuntimeCapability('agent_creation', 'Create and manage agents'),
                RuntimeCapability('tool_execution', 'Execute tools and functions'),
                RuntimeCapability('sequential_execution', 'Sequential task execution'),
                RuntimeCapability('handoff_support', 'Agent-to-agent handoffs via Team route', required=False),
            ],
            supports_handoff=True,
            supports_tool_loop=True
        )

        runtimes['google_adk'] = RuntimeInfo(
            id='google_adk',
            name='Google ADK',
            available=_runtime_usable('google_adk', 'google_adk'),
            capabilities=[
                RuntimeCapability('agent_creation', 'Create and manage agents'),
                RuntimeCapability('tool_execution', 'Execute tools and functions'),
                RuntimeCapability('sequential_execution', 'Sequential task execution'),
                RuntimeCapability('handoff_support', 'Agent-to-agent handoffs via sub_agents', required=False),
            ],
            supports_handoff=True,
            supports_tool_loop=True
        )
        
        return runtimes
    
    def _check_autogen_v4(self) -> bool:
        """Check if AutoGen v0.4+ packages are installed."""
        try:
            from praisonai._framework_availability import is_available as fw_available
            return fw_available('autogen_v4')
        except ImportError:
            return False
    
    def _parse_yaml_config(self, yaml_path: str) -> Dict[str, Any]:
        """Parse team YAML configuration."""
        try:
            with open(yaml_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise ValueError(f"Failed to parse YAML file: {e}")
    
    def _extract_agent_configs(self, config: Dict[str, Any]) -> List[AgentRuntimeConfig]:
        """Extract agent runtime configurations from YAML."""
        agents = []
        
        # Handle both 'roles' (canonical) and 'agents' (legacy) sections
        entities = {}
        entities.update(config.get('roles', {}))
        entities.update(config.get('agents', {}))
        
        for role_name, role_config in entities.items():
            if not isinstance(role_config, dict):
                continue
            
            # Extract runtime information
            runtime_id = role_config.get('runtime')
            capabilities_needed = set()
            handoff_targets = []
            has_tools = bool(role_config.get('tools', []))
            
            # Check for handoff configuration
            handoff_config = role_config.get('handoff', {})
            if handoff_config:
                if isinstance(handoff_config, dict):
                    raw_targets = handoff_config.get('to', [])
                    if isinstance(raw_targets, str):
                        handoff_targets = [raw_targets]
                    elif isinstance(raw_targets, list):
                        handoff_targets = raw_targets
                    else:
                        handoff_targets = []
                elif isinstance(handoff_config, str):
                    handoff_targets = [handoff_config]
                elif isinstance(handoff_config, list):
                    handoff_targets = handoff_config
                
                if handoff_targets:
                    capabilities_needed.add('handoff_support')
            
            # Check for CLI backend usage
            if role_config.get('cli_backend'):
                capabilities_needed.add('cli_backend')
            
            # Check for tool requirements
            if has_tools:
                capabilities_needed.add('tool_execution')
            
            # Resolve runtime using framework selection logic
            resolved_runtime = self._resolve_runtime_for_agent(
                config, runtime_id, role_config
            )
            
            agents.append(AgentRuntimeConfig(
                role_name=role_name,
                runtime_id=runtime_id,
                resolved_runtime=resolved_runtime,
                capabilities_needed=capabilities_needed,
                handoff_targets=handoff_targets,
                has_tools=has_tools
            ))
        
        return agents
    
    def _resolve_runtime_for_agent(self, config: Dict[str, Any], 
                                 agent_runtime: Optional[str],
                                 agent_config: Dict[str, Any]) -> str:
        """Resolve the actual runtime that will be used for an agent."""
        # Agent-level runtime takes priority
        if agent_runtime:
            return agent_runtime
        
        # Fall back to global framework
        framework = config.get('framework', 'praisonai')
        
        # Handle AutoGen version selection logic
        if framework == 'autogen':
            autogen_version = str(
                config.get('autogen_version', os.environ.get('AUTOGEN_VERSION', 'auto'))
            ).lower()
            
            autogen_v4_runtime = self.known_runtimes.get('autogen_v4')
            autogen_runtime = self.known_runtimes.get('autogen')
            
            if autogen_version == 'v0.4' and autogen_v4_runtime and autogen_v4_runtime.available:
                return 'autogen_v4'
            elif autogen_version == 'v0.2' and autogen_runtime and autogen_runtime.available:
                return 'autogen'
            elif autogen_version == 'auto':
                if autogen_v4_runtime and autogen_v4_runtime.available:
                    return 'autogen_v4'
                elif autogen_runtime and autogen_runtime.available:
                    return 'autogen'
        
        return framework
    
    def validate_team_yaml(self, yaml_path: str) -> Iterator[CheckResult]:
        """Validate a team YAML file for runtime compatibility."""
        try:
            config = self._parse_yaml_config(yaml_path)
        except Exception as e:
            yield CheckResult(
                id="runtime.yaml_parse",
                title="YAML Parsing",
                category=CheckCategory.CONFIG,
                status=CheckStatus.ERROR,
                message=f"Failed to parse YAML: {e}",
                severity=CheckSeverity.CRITICAL
            )
            return
        
        # Extract agent configurations
        try:
            agents = self._extract_agent_configs(config)
        except Exception as e:
            yield CheckResult(
                id="runtime.config_extract",
                title="Configuration Extraction",
                category=CheckCategory.CONFIG,
                status=CheckStatus.ERROR,
                message=f"Failed to extract agent configs: {e}",
                severity=CheckSeverity.HIGH
            )
            return
        
        if not agents:
            yield CheckResult(
                id="runtime.no_agents",
                title="Agent Presence",
                category=CheckCategory.CONFIG,
                status=CheckStatus.WARN,
                message="No agents found in configuration",
                severity=CheckSeverity.LOW
            )
            return
        
        # Validate each agent's runtime
        yield from self._validate_agent_runtimes(agents)
        
        # Validate cross-agent compatibility
        yield from self._validate_handoff_compatibility(agents)
        
        # Validate mixed-runtime scenarios
        yield from self._validate_mixed_runtime_setup(agents)
    
    def _validate_agent_runtimes(self, agents: List[AgentRuntimeConfig]) -> Iterator[CheckResult]:
        """Validate individual agent runtime configurations."""
        for agent in agents:
            runtime_info = self.known_runtimes.get(agent.resolved_runtime)
            
            if not runtime_info:
                yield CheckResult(
                    id=f"runtime.unknown_runtime.{agent.role_name}",
                    title=f"Unknown Runtime ({agent.role_name})",
                    category=CheckCategory.CONFIG,
                    status=CheckStatus.FAIL,
                    message=f"Unknown runtime '{agent.resolved_runtime}' for agent '{agent.role_name}'",
                    details=f"Known runtimes: {', '.join(self.known_runtimes.keys())}",
                    severity=CheckSeverity.HIGH
                )
                continue
            
            if not runtime_info.available:
                yield CheckResult(
                    id=f"runtime.unavailable.{agent.role_name}",
                    title=f"Runtime Unavailable ({agent.role_name})",
                    category=CheckCategory.ENVIRONMENT,
                    status=CheckStatus.FAIL,
                    message=f"Runtime '{runtime_info.name}' is not available for agent '{agent.role_name}'",
                    details="Install required packages or check dependencies",
                    remediation=f"Install packages for {runtime_info.name}",
                    severity=CheckSeverity.HIGH
                )
                continue
            
            # Check capability requirements
            runtime_capabilities = {cap.name for cap in runtime_info.capabilities}
            missing_capabilities = agent.capabilities_needed - runtime_capabilities
            
            if missing_capabilities:
                yield CheckResult(
                    id=f"runtime.missing_capabilities.{agent.role_name}",
                    title=f"Missing Capabilities ({agent.role_name})",
                    category=CheckCategory.CONFIG,
                    status=CheckStatus.FAIL,
                    message=f"Runtime '{runtime_info.name}' missing required capabilities: {', '.join(missing_capabilities)}",
                    details=f"Agent '{agent.role_name}' requires: {', '.join(agent.capabilities_needed)}",
                    remediation="Use a compatible runtime or remove unsupported features",
                    severity=CheckSeverity.HIGH
                )
    
    def _validate_handoff_compatibility(self, agents: List[AgentRuntimeConfig]) -> Iterator[CheckResult]:
        """Validate handoff compatibility between agents."""
        agent_map = {agent.role_name: agent for agent in agents}
        
        for agent in agents:
            if not agent.handoff_targets:
                continue
            
            runtime_info = self.known_runtimes.get(agent.resolved_runtime)
            if not runtime_info or not runtime_info.supports_handoff:
                yield CheckResult(
                    id=f"runtime.handoff_unsupported.{agent.role_name}",
                    title=f"Handoff Unsupported ({agent.role_name})",
                    category=CheckCategory.CONFIG,
                    status=CheckStatus.FAIL,
                    message=f"Agent '{agent.role_name}' configured for handoffs but runtime '{runtime_info.name if runtime_info else agent.resolved_runtime}' doesn't support handoffs",
                    details=f"Handoff targets: {', '.join(agent.handoff_targets)}",
                    remediation="Use praisonai, autogen_v4, or openai_agents framework for handoff support",
                    severity=CheckSeverity.HIGH
                )
                continue
            
            # Check if handoff targets exist and are compatible
            for target in agent.handoff_targets:
                target_agent = agent_map.get(target)
                if not target_agent:
                    yield CheckResult(
                        id=f"runtime.handoff_target_missing.{agent.role_name}",
                        title=f"Handoff Target Missing ({agent.role_name})",
                        category=CheckCategory.CONFIG,
                        status=CheckStatus.FAIL,
                        message=f"Agent '{agent.role_name}' has handoff target '{target}' that doesn't exist",
                        severity=CheckSeverity.HIGH
                    )
                    continue
                
                target_runtime_info = self.known_runtimes.get(target_agent.resolved_runtime)
                if target_runtime_info and not target_runtime_info.supports_tool_loop:
                    yield CheckResult(
                        id=f"runtime.handoff_target_incompatible.{agent.role_name}",
                        title=f"Handoff Target Incompatible ({agent.role_name})",
                        category=CheckCategory.CONFIG,
                        status=CheckStatus.WARN,
                        message=f"Handoff target '{target}' uses runtime that may not support tool loops",
                        details=f"Target runtime: {target_runtime_info.name}",
                        severity=CheckSeverity.MEDIUM
                    )
    
    def _validate_mixed_runtime_setup(self, agents: List[AgentRuntimeConfig]) -> Iterator[CheckResult]:
        """Validate mixed-runtime scenario compatibility."""
        runtimes_used = {agent.resolved_runtime for agent in agents}
        
        if len(runtimes_used) <= 1:
            return  # Single runtime setup, no mixed-runtime issues
        
        yield CheckResult(
            id="runtime.mixed_runtimes",
            title="Mixed Runtime Setup",
            category=CheckCategory.CONFIG,
            status=CheckStatus.WARN,
            message=f"Multiple runtimes detected: {', '.join(runtimes_used)}",
            details="Mixed runtimes may have compatibility issues",
            remediation="Consider using a single runtime for consistency",
            severity=CheckSeverity.MEDIUM
        )
        
        # Check for specific problematic combinations
        handoff_agents = [a for a in agents if a.handoff_targets]
        if handoff_agents:
            handoff_runtimes = {a.resolved_runtime for a in handoff_agents}
            incompatible_handoff_runtimes = handoff_runtimes - {
                'praisonai',
                'autogen_v4',
                'openai_agents',
                'agno',
                'google_adk',
            }
            
            if incompatible_handoff_runtimes:
                yield CheckResult(
                    id="runtime.mixed_handoff_incompatible",
                    title="Mixed Runtime Handoff Issues",
                    category=CheckCategory.CONFIG,
                    status=CheckStatus.FAIL,
                    message=f"Handoffs configured with incompatible runtimes: {', '.join(incompatible_handoff_runtimes)}",
                    details="Only praisonai, autogen_v4, openai_agents, agno, and google_adk runtimes support handoffs",
                    remediation="Use praisonai, autogen_v4, openai_agents, agno, or google_adk for agents that need handoff capabilities",
                    severity=CheckSeverity.HIGH
                )


def lint_runtime_team(yaml_path: str) -> List[CheckResult]:
    """
    Public API for programmatic runtime linting.
    
    Args:
        yaml_path: Path to the team YAML file
        
    Returns:
        List of check results
    """
    checker = RuntimeCompatibilityChecker()
    return list(checker.validate_team_yaml(yaml_path))


# Register the runtime checks with the doctor framework


def runtime_team_check(config):
    """Runtime team compatibility check for the doctor framework."""
    team_file = getattr(config, 'team_file', None)
    
    if not team_file:
        return CheckResult(
            id="runtime.no_team_file",
            title="No Team File Specified",
            category=CheckCategory.RUNTIME,
            status=CheckStatus.SKIP,
            message="Use --team to specify a team YAML file for runtime validation"
        )
    
    if not os.path.exists(team_file):
        return CheckResult(
            id="runtime.team_file_not_found",
            title="Team File Not Found",
            category=CheckCategory.RUNTIME,
            status=CheckStatus.FAIL,
            message=f"Team YAML file not found: {team_file}",
            severity=CheckSeverity.HIGH
        )
    
    checker = RuntimeCompatibilityChecker()
    results = list(checker.validate_team_yaml(team_file))
    
    if not results:
        return CheckResult(
            id="runtime.team_validation_success",
            title="Runtime Team Compatibility",
            category=CheckCategory.RUNTIME,
            status=CheckStatus.PASS,
            message=f"No runtime compatibility issues found in {team_file}"
        )
    
    # Aggregate results into a single CheckResult as expected by the doctor engine
    has_failures = any(r.status in (CheckStatus.FAIL, CheckStatus.ERROR) for r in results)
    has_warnings = any(r.status == CheckStatus.WARN for r in results)
    
    if has_failures:
        status = CheckStatus.FAIL
        severity = CheckSeverity.HIGH
    elif has_warnings:
        status = CheckStatus.WARN
        severity = CheckSeverity.MEDIUM
    else:
        status = CheckStatus.PASS
        severity = CheckSeverity.LOW
    
    return CheckResult(
        id="runtime.team_validation_aggregate",
        title="Runtime Team Compatibility",
        category=CheckCategory.RUNTIME,
        status=status,
        message=f"Found {len(results)} runtime compatibility issue(s) in {team_file}",
        details="\n".join(f"- {r.id}: {r.message}" for r in results) if results else "No issues found",
        severity=severity,
        metadata={"findings": [r.to_dict() for r in results]}
    )


def workflow_runtime_check(config):
    """Workflow runtime compatibility check (placeholder for future implementation)."""
    workflow_file = getattr(config, 'workflow_file', None)
    
    if not workflow_file:
        return CheckResult(
            id="runtime.workflow_not_implemented",
            title="Workflow Runtime Validation",
            category=CheckCategory.RUNTIME,
            status=CheckStatus.SKIP,
            message="Workflow runtime validation not yet implemented"
        )
    
    return CheckResult(
        id="runtime.workflow_placeholder",
        title="Workflow Runtime Validation",
        category=CheckCategory.RUNTIME,
        status=CheckStatus.SKIP,
        message="Workflow runtime validation will be implemented in future versions"
    )


# Register checks when module is imported
try:
    registry = CheckRegistry()
    
    # Register team runtime check
    registry.register(
        id='runtime.team',
        title='Runtime Team Compatibility',
        description='Validate runtime compatibility for team YAML configurations',
        category=CheckCategory.RUNTIME,
        implementation=runtime_team_check,
        requires_deep=False
    )
    
    # Register workflow runtime check (placeholder)
    registry.register(
        id='runtime.workflow',
        title='Workflow Runtime Compatibility',
        description='Validate runtime compatibility for workflow YAML configurations',
        category=CheckCategory.RUNTIME,
        implementation=workflow_runtime_check,
        requires_deep=False
    )
    
except Exception as e:
    # Log registration failure but don't crash the module
    import logging
    logging.getLogger(__name__).warning(f"Failed to register runtime checks: {e}")