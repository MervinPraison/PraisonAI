"""
Metrics Plugin for PraisonAI Agents.

Provides metrics collection for agent lifecycle events.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..plugin import Plugin, PluginInfo, PluginHook


@dataclass
class ToolMetrics:
    """Metrics for a single tool."""
    name: str
    call_count: int = 0
    total_duration_ms: float = 0.0
    error_count: int = 0
    last_called: float = 0.0


@dataclass
class AgentMetrics:
    """Metrics for agent execution."""
    prompt_count: int = 0
    response_count: int = 0
    total_prompt_chars: int = 0
    total_response_chars: int = 0


@dataclass
class LLMMetrics:
    """Metrics for LLM calls."""
    call_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_duration_ms: float = 0.0


@dataclass
class PluginMetricsData:
    """Container for all metrics."""
    tools: Dict[str, ToolMetrics] = field(default_factory=dict)
    agent: AgentMetrics = field(default_factory=AgentMetrics)
    llm: LLMMetrics = field(default_factory=LLMMetrics)
    start_time: float = field(default_factory=time.time)


class MetricsPlugin(Plugin):
    """
    Plugin that collects metrics for agent lifecycle events.
    
    Useful for monitoring and performance analysis.
    
    Example:
        from praisonaiagents.plugins import PluginManager
        from praisonaiagents.plugins.builtin import MetricsPlugin
        
        metrics_plugin = MetricsPlugin()
        manager = PluginManager()
        manager.register(metrics_plugin)
        
        # After agent execution
        print(metrics_plugin.get_metrics())
    """
    
    def __init__(self):
        """Initialize the metrics plugin."""
        self._metrics = PluginMetricsData()
        self._tool_start_times: Dict[str, float] = {}
        self._llm_start_time: float = 0.0
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="metrics",
            version="1.0.0",
            description="Collects metrics for agent lifecycle events",
            author="PraisonAI",
            hooks=[
                PluginHook.BEFORE_TOOL,
                PluginHook.AFTER_TOOL,
                PluginHook.BEFORE_AGENT,
                PluginHook.AFTER_AGENT,
                PluginHook.BEFORE_LLM,
                PluginHook.AFTER_LLM,
            ],
        )
    
    def on_init(self, context: Dict[str, Any]) -> None:
        self._metrics = PluginMetricsData()
    
    def on_shutdown(self) -> None:
        pass
    
    def before_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        self._tool_start_times[tool_name] = time.time()
        
        if tool_name not in self._metrics.tools:
            self._metrics.tools[tool_name] = ToolMetrics(name=tool_name)
        
        return args
    
    def after_tool(self, tool_name: str, result: Any) -> Any:
        if tool_name in self._tool_start_times:
            duration_ms = (time.time() - self._tool_start_times[tool_name]) * 1000
            del self._tool_start_times[tool_name]
            
            if tool_name in self._metrics.tools:
                metrics = self._metrics.tools[tool_name]
                metrics.call_count += 1
                metrics.total_duration_ms += duration_ms
                metrics.last_called = time.time()
        
        return result
    
    def before_agent(self, prompt: str, context: Dict[str, Any]) -> str:
        self._metrics.agent.prompt_count += 1
        self._metrics.agent.total_prompt_chars += len(prompt) if prompt else 0
        return prompt
    
    def after_agent(self, response: str, context: Dict[str, Any]) -> str:
        self._metrics.agent.response_count += 1
        self._metrics.agent.total_response_chars += len(response) if response else 0
        return response
    
    def before_llm(self, messages: List[Dict], params: Dict[str, Any]) -> tuple:
        self._llm_start_time = time.time()
        return messages, params
    
    def after_llm(self, response: str, usage: Dict[str, Any]) -> str:
        duration_ms = (time.time() - self._llm_start_time) * 1000
        
        self._metrics.llm.call_count += 1
        self._metrics.llm.total_duration_ms += duration_ms
        
        if usage:
            self._metrics.llm.total_input_tokens += usage.get("prompt_tokens", 0)
            self._metrics.llm.total_output_tokens += usage.get("completion_tokens", 0)
        
        return response
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get all collected metrics.
        
        Returns:
            Dictionary containing all metrics
        """
        uptime = time.time() - self._metrics.start_time
        
        tool_metrics = {}
        for name, metrics in self._metrics.tools.items():
            avg_duration = (
                metrics.total_duration_ms / metrics.call_count
                if metrics.call_count > 0
                else 0
            )
            tool_metrics[name] = {
                "call_count": metrics.call_count,
                "total_duration_ms": metrics.total_duration_ms,
                "avg_duration_ms": avg_duration,
                "error_count": metrics.error_count,
            }
        
        return {
            "uptime_seconds": uptime,
            "tools": tool_metrics,
            "agent": {
                "prompt_count": self._metrics.agent.prompt_count,
                "response_count": self._metrics.agent.response_count,
                "total_prompt_chars": self._metrics.agent.total_prompt_chars,
                "total_response_chars": self._metrics.agent.total_response_chars,
            },
            "llm": {
                "call_count": self._metrics.llm.call_count,
                "total_input_tokens": self._metrics.llm.total_input_tokens,
                "total_output_tokens": self._metrics.llm.total_output_tokens,
                "total_duration_ms": self._metrics.llm.total_duration_ms,
            },
        }
    
    def reset_metrics(self) -> None:
        """Reset all collected metrics."""
        self._metrics = PluginMetricsData()
        self._tool_start_times.clear()
