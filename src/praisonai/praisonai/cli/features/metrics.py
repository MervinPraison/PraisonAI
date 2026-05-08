"""
Metrics Handler for CLI.

Provides token usage and cost tracking for agent executions.
Usage: praisonai "prompt" --metrics
"""

import logging
from typing import Any, Dict, Tuple
from .base import FlagHandler

logger = logging.getLogger(__name__)


class MetricsHandler(FlagHandler):
    """
    Handler for --metrics flag.
    
    Tracks and displays token usage and cost metrics after agent execution.
    
    Example:
        praisonai "Analyze data" --metrics
    """
    
    @property
    def feature_name(self) -> str:
        return "metrics"
    
    @property
    def flag_name(self) -> str:
        return "metrics"
    
    @property
    def flag_help(self) -> str:
        return "Display token usage and cost metrics after execution"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Metrics are built into praisonaiagents, always available."""
        return True, ""
    
    def apply_to_agent_config(self, config: Dict[str, Any], flag_value: Any) -> Dict[str, Any]:
        """
        Apply metrics configuration to agent config.
        
        Args:
            config: Agent configuration dictionary
            flag_value: Boolean indicating if metrics should be enabled
            
        Returns:
            Modified configuration with metrics enabled
        """
        if flag_value:
            config["metrics"] = True
        return config
    
    def format_metrics(self, metrics: Dict[str, Any]) -> str:
        """
        Format metrics dictionary into human-readable string.
        
        Args:
            metrics: Dictionary containing token and cost metrics
            
        Returns:
            Formatted string for display
        """
        lines = []
        lines.append("\n📊 Execution Metrics:")
        lines.append("-" * 40)
        
        # Token metrics
        if "prompt_tokens" in metrics:
            lines.append(f"  Prompt tokens:     {metrics['prompt_tokens']:,}")
        if "completion_tokens" in metrics:
            lines.append(f"  Completion tokens: {metrics['completion_tokens']:,}")
        if "total_tokens" in metrics:
            lines.append(f"  Total tokens:      {metrics['total_tokens']:,}")
        
        # Cost metrics
        if "cost" in metrics:
            cost = metrics["cost"]
            if isinstance(cost, (int, float)):
                lines.append(f"  Estimated cost:    ${cost:.6f}")
        
        # Timing metrics
        if "duration" in metrics:
            lines.append(f"  Duration:          {metrics['duration']:.2f}s")
        if "tokens_per_second" in metrics:
            lines.append(f"  Tokens/second:     {metrics['tokens_per_second']:.1f}")
        
        # Model info
        if "model" in metrics:
            lines.append(f"  Model:             {metrics['model']}")
        
        lines.append("-" * 40)
        return "\n".join(lines)
    
    def extract_metrics_from_agent(self, agent: Any) -> Dict[str, Any]:
        """
        Extract metrics from an agent instance.
        
        Args:
            agent: Agent instance that may have metrics
            
        Returns:
            Dictionary of metrics
        """
        metrics = {}
        
        # Try to get metrics from various possible locations
        if hasattr(agent, 'last_token_metrics'):
            metrics.update(agent.last_token_metrics or {})
        
        # Check llm_model property for model info
        if hasattr(agent, 'llm_model'):
            llm_model = agent.llm_model
            if hasattr(llm_model, 'model'):
                metrics['model'] = llm_model.model
            elif isinstance(llm_model, str):
                metrics['model'] = llm_model
        
        if hasattr(agent, 'llm') and agent.llm:
            llm = agent.llm
            if hasattr(llm, 'last_token_metrics'):
                metrics.update(llm.last_token_metrics or {})
            if hasattr(llm, 'model'):
                metrics['model'] = llm.model
        
        if hasattr(agent, 'metrics') and isinstance(agent.metrics, dict):
            metrics.update(agent.metrics or {})
        
        # Try to get from litellm's success callback data
        try:
            import litellm
            # Check if there's accumulated usage data
            if hasattr(litellm, '_thread_context') and litellm._thread_context:
                ctx = litellm._thread_context
                if hasattr(ctx, 'usage'):
                    usage = ctx.usage
                    metrics['prompt_tokens']     = getattr(usage, 'prompt_tokens', None)
                    metrics['completion_tokens'] = getattr(usage, 'completion_tokens', None)
                    metrics['total_tokens']      = getattr(usage, 'total_tokens', None)
        except ImportError:
            logger.debug("litellm not installed; skipping token metrics")
        except AttributeError as e:
            logger.debug("litellm internals changed (%s); skipping token metrics", e)
        
        # Try to get cost from litellm cost tracking
        try:
            from litellm import completion_cost
            if metrics.get('prompt_tokens') and metrics.get('completion_tokens'):
                model = metrics.get('model', 'gpt-4o-mini')
                try:
                    metrics['cost'] = completion_cost(
                        model=model,
                        prompt_tokens=metrics['prompt_tokens'],
                        completion_tokens=metrics['completion_tokens'],
                    )
                except Exception as e:
                    logger.debug("cost calc failed for model=%s: %s", model, e)
        except ImportError:
            logger.debug("litellm.completion_cost unavailable; skipping cost metrics")
        
        return metrics
    
    def post_process_result(self, result: Any, flag_value: Any) -> Any:
        """
        Post-process result to display metrics.
        
        Args:
            result: Agent output (may contain metrics)
            flag_value: Boolean indicating if metrics should be displayed
            
        Returns:
            Original result (metrics are printed)
        """
        if not flag_value:
            return result
        
        # Try to extract metrics from result if it's a TaskOutput
        metrics = {}
        if hasattr(result, 'token_metrics'):
            metrics = result.token_metrics or {}
        elif isinstance(result, dict) and 'metrics' in result:
            metrics = result['metrics']
        
        if metrics:
            formatted = self.format_metrics(metrics)
            self.print_status(formatted, "info")
        else:
            self.print_status("📊 No metrics available for this execution", "warning")
        
        return result
    
    def execute(self, agent: Any = None, **kwargs) -> Dict[str, Any]:
        """
        Execute metrics extraction and display.
        
        Args:
            agent: Agent instance to extract metrics from
            
        Returns:
            Dictionary of metrics
        """
        if agent:
            metrics = self.extract_metrics_from_agent(agent)
            if metrics:
                formatted = self.format_metrics(metrics)
                self.print_status(formatted, "info")
            return metrics
        return {}
