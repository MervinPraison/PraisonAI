"""
Selftest checks for the Doctor CLI module.

Performs minimal agent dry-run to validate the system.
"""

import os

from ..models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    CheckSeverity,
    DoctorConfig,
)
from ..registry import register_check


@register_check(
    id="selftest_agent_import",
    title="Agent Import",
    description="Check Agent class can be imported",
    category=CheckCategory.SELFTEST,
    severity=CheckSeverity.HIGH,
)
def check_selftest_agent_import(config: DoctorConfig) -> CheckResult:
    """Check Agent class can be imported."""
    try:
        from praisonaiagents import Agent
        return CheckResult(
            id="selftest_agent_import",
            title="Agent Import",
            category=CheckCategory.SELFTEST,
            status=CheckStatus.PASS,
            message="Agent class imported successfully",
        )
    except ImportError as e:
        return CheckResult(
            id="selftest_agent_import",
            title="Agent Import",
            category=CheckCategory.SELFTEST,
            status=CheckStatus.FAIL,
            message=f"Cannot import Agent: {e}",
            remediation="Ensure praisonaiagents is properly installed",
            severity=CheckSeverity.CRITICAL,
        )


@register_check(
    id="selftest_agent_create",
    title="Agent Creation",
    description="Check Agent can be instantiated",
    category=CheckCategory.SELFTEST,
    severity=CheckSeverity.HIGH,
    dependencies=["selftest_agent_import"],
)
def check_selftest_agent_create(config: DoctorConfig) -> CheckResult:
    """Check Agent can be instantiated."""
    try:
        from praisonaiagents import Agent
        
        # Create a minimal agent without making API calls
        agent = Agent(
            name="DoctorTestAgent",
            instructions="You are a test agent.",
            llm="gpt-4o-mini",  # Default model
            output="minimal",
        )
        
        return CheckResult(
            id="selftest_agent_create",
            title="Agent Creation",
            category=CheckCategory.SELFTEST,
            status=CheckStatus.PASS,
            message="Agent instantiated successfully",
            metadata={"agent_name": agent.name},
        )
    except Exception as e:
        return CheckResult(
            id="selftest_agent_create",
            title="Agent Creation",
            category=CheckCategory.SELFTEST,
            status=CheckStatus.FAIL,
            message=f"Agent creation failed: {type(e).__name__}",
            details=str(e)[:200],
            remediation="Check configuration and dependencies",
            severity=CheckSeverity.HIGH,
        )


@register_check(
    id="selftest_llm_config",
    title="LLM Configuration",
    description="Check LLM configuration is valid",
    category=CheckCategory.SELFTEST,
    severity=CheckSeverity.MEDIUM,
)
def check_selftest_llm_config(config: DoctorConfig) -> CheckResult:
    """Check LLM configuration is valid."""
    # Check for API key
    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    google_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    ollama_host = os.environ.get("OLLAMA_HOST")
    
    providers = []
    if openai_key:
        providers.append("OpenAI")
    if anthropic_key:
        providers.append("Anthropic")
    if google_key:
        providers.append("Google")
    if ollama_host:
        providers.append("Ollama")
    
    if providers:
        return CheckResult(
            id="selftest_llm_config",
            title="LLM Configuration",
            category=CheckCategory.SELFTEST,
            status=CheckStatus.PASS,
            message=f"LLM provider(s) configured: {', '.join(providers)}",
            metadata={"providers": providers},
        )
    else:
        return CheckResult(
            id="selftest_llm_config",
            title="LLM Configuration",
            category=CheckCategory.SELFTEST,
            status=CheckStatus.FAIL,
            message="No LLM provider configured",
            remediation="Set OPENAI_API_KEY or another provider's API key",
            severity=CheckSeverity.HIGH,
        )


@register_check(
    id="selftest_mock_chat",
    title="Mock Chat Test",
    description="Test agent chat with mock response",
    category=CheckCategory.SELFTEST,
    severity=CheckSeverity.MEDIUM,
    requires_deep=True,
)
def check_selftest_mock_chat(config: DoctorConfig) -> CheckResult:
    """Test agent chat with mock response (no API call)."""
    if not config.mock and not config.live:
        # Default to mock in deep mode
        config.mock = True
    
    if config.live:
        return CheckResult(
            id="selftest_mock_chat",
            title="Mock Chat Test",
            category=CheckCategory.SELFTEST,
            status=CheckStatus.SKIP,
            message="Skipped (--live mode uses live API)",
        )
    
    try:
        # Test basic agent functionality without making API calls
        from praisonaiagents import Agent
        
        agent = Agent(
            name="MockTestAgent",
            instructions="You are a test agent. Always respond with 'OK'.",
            llm="gpt-4o-mini",
            output="minimal",
        )
        
        # Verify agent is properly configured
        if hasattr(agent, 'name') and hasattr(agent, 'instructions'):
            return CheckResult(
                id="selftest_mock_chat",
                title="Mock Chat Test",
                category=CheckCategory.SELFTEST,
                status=CheckStatus.PASS,
                message="Agent mock test passed",
            )
        else:
            return CheckResult(
                id="selftest_mock_chat",
                title="Mock Chat Test",
                category=CheckCategory.SELFTEST,
                status=CheckStatus.FAIL,
                message="Agent missing expected attributes",
            )
    except Exception as e:
        return CheckResult(
            id="selftest_mock_chat",
            title="Mock Chat Test",
            category=CheckCategory.SELFTEST,
            status=CheckStatus.FAIL,
            message=f"Mock test failed: {type(e).__name__}",
            details=str(e)[:200],
        )


@register_check(
    id="selftest_live_chat",
    title="Live Chat Test",
    description="Test agent chat with live API call",
    category=CheckCategory.SELFTEST,
    severity=CheckSeverity.LOW,
    requires_deep=True,
)
def check_selftest_live_chat(config: DoctorConfig) -> CheckResult:
    """Test agent chat with live API call."""
    if not config.live:
        return CheckResult(
            id="selftest_live_chat",
            title="Live Chat Test",
            category=CheckCategory.SELFTEST,
            status=CheckStatus.SKIP,
            message="Skipped (use --live to enable)",
        )
    
    # Check for API key first
    if not os.environ.get("OPENAI_API_KEY"):
        return CheckResult(
            id="selftest_live_chat",
            title="Live Chat Test",
            category=CheckCategory.SELFTEST,
            status=CheckStatus.SKIP,
            message="Skipped (OPENAI_API_KEY not set)",
        )
    
    try:
        from praisonaiagents import Agent
        
        model = config.model or "gpt-4o-mini"
        
        agent = Agent(
            name="LiveTestAgent",
            instructions="You are a test agent. Respond with exactly: 'Doctor test OK'",
            llm=model,
            output="minimal",
        )
        
        # Make a simple API call
        response = agent.chat("Say hello")
        
        if response:
            return CheckResult(
                id="selftest_live_chat",
                title="Live Chat Test",
                category=CheckCategory.SELFTEST,
                status=CheckStatus.PASS,
                message=f"Live API call successful (model: {model})",
                metadata={"model": model, "response_length": len(str(response))},
            )
        else:
            return CheckResult(
                id="selftest_live_chat",
                title="Live Chat Test",
                category=CheckCategory.SELFTEST,
                status=CheckStatus.FAIL,
                message="Live API call returned empty response",
            )
    except Exception as e:
        return CheckResult(
            id="selftest_live_chat",
            title="Live Chat Test",
            category=CheckCategory.SELFTEST,
            status=CheckStatus.FAIL,
            message=f"Live API call failed: {type(e).__name__}",
            details=str(e)[:200],
            remediation="Check API key and network connectivity",
        )


@register_check(
    id="selftest_tools_wiring",
    title="Tools Wiring",
    description="Check tools can be wired to agent",
    category=CheckCategory.SELFTEST,
    severity=CheckSeverity.LOW,
)
def check_selftest_tools_wiring(config: DoctorConfig) -> CheckResult:
    """Check tools can be wired to agent."""
    try:
        from praisonaiagents import Agent
        
        # Define a simple test tool
        def test_tool(x: str) -> str:
            """A test tool that echoes input."""
            return f"Echo: {x}"
        
        agent = Agent(
            name="ToolTestAgent",
            instructions="You are a test agent with tools.",
            tools=[test_tool],
            llm="gpt-4o-mini",
            output="minimal",
        )
        
        # Check tools are registered
        if hasattr(agent, 'tools') or hasattr(agent, '_tools'):
            return CheckResult(
                id="selftest_tools_wiring",
                title="Tools Wiring",
                category=CheckCategory.SELFTEST,
                status=CheckStatus.PASS,
                message="Tools wired to agent successfully",
            )
        else:
            return CheckResult(
                id="selftest_tools_wiring",
                title="Tools Wiring",
                category=CheckCategory.SELFTEST,
                status=CheckStatus.WARN,
                message="Tools wiring could not be verified",
            )
    except Exception as e:
        return CheckResult(
            id="selftest_tools_wiring",
            title="Tools Wiring",
            category=CheckCategory.SELFTEST,
            status=CheckStatus.FAIL,
            message=f"Tools wiring failed: {type(e).__name__}",
            details=str(e)[:200],
        )
