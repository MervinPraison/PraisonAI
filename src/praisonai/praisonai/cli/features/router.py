"""
Router Handler for CLI.

Provides smart model selection based on task complexity.
Usage: praisonai "Complex task" --router
"""

from typing import Any, Dict, Tuple
from .base import FlagHandler


class RouterHandler(FlagHandler):
    """
    Handler for --router flag.
    
    Automatically selects the best model based on task complexity.
    
    Example:
        praisonai "Simple question" --router
        praisonai "Complex analysis" --router
    """
    
    # Model tiers for routing
    MODEL_TIERS = {
        'simple': ['gpt-4o-mini', 'claude-3-haiku', 'gemini-1.5-flash'],
        'medium': ['gpt-4o', 'claude-3-sonnet', 'gemini-1.5-pro'],
        'complex': ['gpt-4-turbo', 'claude-3-opus', 'o1-preview'],
    }
    
    @property
    def feature_name(self) -> str:
        return "router"
    
    @property
    def flag_name(self) -> str:
        return "router"
    
    @property
    def flag_help(self) -> str:
        return "Auto-select best model based on task complexity"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Router is built-in, always available."""
        return True, ""
    
    def analyze_complexity(self, prompt: str) -> str:
        """
        Analyze prompt complexity.
        
        Args:
            prompt: The task prompt
            
        Returns:
            Complexity level: 'simple', 'medium', or 'complex'
        """
        # Simple heuristics for complexity
        prompt_lower = prompt.lower()
        word_count = len(prompt.split())
        
        # Complex indicators
        complex_keywords = [
            'analyze', 'research', 'comprehensive', 'detailed',
            'compare', 'evaluate', 'synthesize', 'multi-step',
            'code review', 'architecture', 'design pattern',
            'optimize', 'debug', 'refactor'
        ]
        
        # Simple indicators
        simple_keywords = [
            'what is', 'define', 'list', 'name', 'when',
            'where', 'who', 'simple', 'quick', 'brief'
        ]
        
        complex_count = sum(1 for kw in complex_keywords if kw in prompt_lower)
        simple_count = sum(1 for kw in simple_keywords if kw in prompt_lower)
        
        # Determine complexity
        if complex_count >= 2 or word_count > 100:
            return 'complex'
        elif simple_count >= 2 or word_count < 20:
            return 'simple'
        else:
            return 'medium'
    
    def select_model(self, prompt: str, preferred_provider: str = None) -> str:
        """
        Select the best model for the prompt.
        
        Args:
            prompt: The task prompt
            preferred_provider: Optional preferred provider (openai, anthropic, google)
            
        Returns:
            Selected model name
        """
        complexity = self.analyze_complexity(prompt)
        models = self.MODEL_TIERS.get(complexity, self.MODEL_TIERS['medium'])
        
        # Filter by provider if specified
        if preferred_provider:
            provider_prefixes = {
                'openai': ['gpt-', 'o1-'],
                'anthropic': ['claude-'],
                'google': ['gemini-']
            }
            prefixes = provider_prefixes.get(preferred_provider.lower(), [])
            filtered = [m for m in models if any(m.startswith(p) for p in prefixes)]
            if filtered:
                models = filtered
        
        selected = models[0] if models else 'gpt-4o-mini'
        
        self.print_status(f"🎯 Task complexity: {complexity}", "info")
        self.print_status(f"🤖 Selected model: {selected}", "success")
        
        return selected
    
    def apply_to_agent_config(self, config: Dict[str, Any], flag_value: Any) -> Dict[str, Any]:
        """
        Apply router configuration.
        
        Args:
            config: Agent configuration dictionary
            flag_value: Boolean or dict with provider preference
            
        Returns:
            Modified configuration with selected model
        """
        if not flag_value:
            return config
        
        # Get prompt from config if available
        prompt = config.get('prompt', config.get('goal', ''))
        
        preferred_provider = None
        if isinstance(flag_value, dict):
            preferred_provider = flag_value.get('provider')
        
        if prompt:
            selected_model = self.select_model(prompt, preferred_provider)
            config['llm'] = selected_model
        
        config['use_router'] = True
        return config
    
    def execute(self, prompt: str = None, provider: str = None, **kwargs) -> str:
        """
        Execute model selection.
        
        Args:
            prompt: Task prompt
            provider: Preferred provider
            
        Returns:
            Selected model name
        """
        if not prompt:
            return 'gpt-4o-mini'  # Default
        
        return self.select_model(prompt, provider)
