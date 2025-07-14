"""
Router Agent that can use different LLM models based on task requirements.

This module extends the base Agent class to support multiple models and intelligent
model selection based on task characteristics.
"""

import os
import logging
from typing import Dict, List, Optional, Any, Union
from .agent import Agent
from ..llm.model_router import ModelRouter
from ..llm import LLM

logger = logging.getLogger(__name__)


class RouterAgent(Agent):
    """
    An enhanced agent that can dynamically select and use different LLM models
    based on task requirements, optimizing for cost and performance.
    """
    
    def __init__(
        self,
        models: Optional[Union[List[str], Dict[str, Any]]] = None,
        model_router: Optional[ModelRouter] = None,
        routing_strategy: str = "auto",  # "auto", "manual", "cost-optimized", "performance-optimized"
        primary_model: Optional[str] = None,
        fallback_model: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize a RouterAgent.
        
        Args:
            models: List of model names or dict mapping model names to configurations
            model_router: Custom ModelRouter instance for model selection
            routing_strategy: Strategy for model selection
            primary_model: Primary model to use (overrides routing for simple tasks)
            fallback_model: Fallback model if selected model fails
            **kwargs: Additional arguments passed to parent Agent class
        """
        # Initialize model router
        self.model_router = model_router or ModelRouter()
        self.routing_strategy = routing_strategy
        self.fallback_model = fallback_model or os.getenv('OPENAI_MODEL_NAME', 'gpt-4o-mini')
        
        # Process models configuration
        self.available_models = self._process_models_config(models)
        
        # Set primary model for parent class initialization
        if primary_model:
            kwargs['llm'] = primary_model
        elif self.available_models:
            # Use the most cost-effective model as default
            cheapest_model = min(
                self.available_models.keys(),
                key=lambda m: self.model_router.get_model_info(m).cost_per_1k_tokens 
                if self.model_router.get_model_info(m) else float('inf')
            )
            kwargs['llm'] = cheapest_model
        
        # Store the original llm parameter for later use
        self._llm_config = kwargs.get('llm')
        
        # Store api_key and base_url for LLM initialization
        self._base_url = kwargs.get('base_url')
        self._api_key = kwargs.get('api_key')
        
        # Initialize parent Agent class
        super().__init__(**kwargs)
        
        # Initialize LLM instances for each model
        self._llm_instances: Dict[str, LLM] = {}
        self._initialize_llm_instances()
        
        # Track usage statistics
        self.model_usage_stats = {model: {'calls': 0, 'tokens': 0, 'cost': 0.0} 
                                  for model in self.available_models}
    
    def _process_models_config(self, models: Optional[Union[List[str], Dict[str, Any]]]) -> Dict[str, Any]:
        """Process the models configuration into a standardized format."""
        if not models:
            # Use default models from router
            return {m.name: {} for m in self.model_router.models}
        
        if isinstance(models, list):
            # Simple list of model names
            return {model: {} for model in models}
        
        # Already a dict with model configurations
        return models
    
    def _initialize_llm_instances(self):
        """Initialize LLM instances for each available model."""
        base_url = self._base_url
        api_key = self._api_key
        
        for model_name, config in self.available_models.items():
            try:
                # Merge base configuration with model-specific config
                llm_config = {
                    'model': model_name,
                    'base_url': config.get('base_url', base_url),
                    'api_key': config.get('api_key', api_key),
                    'verbose': self.verbose,
                    'markdown': self.markdown,
                    'stream': self.stream
                }
                
                # Add any model-specific parameters
                llm_config.update(config)
                
                # Create LLM instance
                self._llm_instances[model_name] = LLM(**llm_config)
                logger.debug(f"Initialized LLM instance for model: {model_name}")
                
            except Exception as e:
                logger.warning(f"Failed to initialize LLM for model {model_name}: {e}")
    
    def _select_model_for_task(
        self,
        task_description: str,
        tools: Optional[List[Any]] = None,
        context_size: Optional[int] = None
    ) -> str:
        """
        Select the most appropriate model for a given task.
        
        Args:
            task_description: Description of the task
            tools: Tools required for the task
            context_size: Estimated context size
            
        Returns:
            Selected model name
        """
        if self.routing_strategy == "manual":
            # Use the configured primary model from llm_model property
            llm_model = self.llm_model
            if hasattr(llm_model, 'model'):
                # If it's an LLM instance, get the model name
                return llm_model.model
            elif isinstance(llm_model, str):
                # If it's a string, use it directly
                return llm_model
            # Fallback if no model is configured
            return self.fallback_model
        
        # Determine required capabilities
        required_capabilities = []
        if tools:
            required_capabilities.append("function-calling")
        
        # Determine budget consciousness based on strategy
        budget_conscious = self.routing_strategy in ["auto", "cost-optimized"]
        
        # Get tool names for analysis
        tool_names = []
        if tools:
            tool_names = [t.__name__ if hasattr(t, '__name__') else str(t) for t in tools]
        
        # Use router to select model
        selected_model = self.model_router.select_model(
            task_description=task_description,
            required_capabilities=required_capabilities,
            tools_required=tool_names,
            context_size=context_size,
            budget_conscious=budget_conscious
        )
        
        # Ensure selected model is available
        if selected_model not in self._llm_instances:
            logger.warning(f"Selected model {selected_model} not available, using fallback")
            return self.fallback_model
        
        return selected_model
    
    def _execute_with_model(
        self,
        model_name: str,
        prompt: str,
        context: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        **kwargs
    ) -> str:
        """
        Execute a task with a specific model.
        
        Args:
            model_name: Name of the model to use
            prompt: The prompt to send to the model
            context: Additional context
            tools: Tools to make available
            **kwargs: Additional arguments for the LLM
            
        Returns:
            Model response
        """
        llm_instance = self._llm_instances.get(model_name)
        if not llm_instance:
            logger.error(f"Model {model_name} not initialized, using fallback")
            llm_instance = self._llm_instances.get(self.fallback_model)
            model_name = self.fallback_model
        
        if not llm_instance:
            raise ValueError("No LLM instance available for execution")
        
        # Prepare the full prompt
        full_prompt = prompt
        if context:
            full_prompt = f"{context}\n\n{prompt}"
        
        try:
            # Execute with the selected model
            response = llm_instance.get_response(
                prompt=full_prompt,
                system_prompt=self._build_system_prompt(),
                tools=tools,
                verbose=self.verbose,
                markdown=self.markdown,
                stream=self.stream,
                agent_name=self.name,
                agent_role=self.role,
                agent_tools=[t.__name__ if hasattr(t, '__name__') else str(t) for t in (tools or [])],
                execute_tool_fn=self.execute_tool if tools else None,
                **kwargs
            )
            
            # Update usage statistics
            self.model_usage_stats[model_name]['calls'] += 1
            
            # TODO: Implement token tracking when LLM.get_response() is updated to return token usage
            # The LLM response currently returns only text, but litellm provides usage info in:
            # response.get("usage") with prompt_tokens, completion_tokens, and total_tokens
            # This would require modifying the LLM class to return both text and metadata
            
            return response
            
        except Exception as e:
            logger.error(f"Error executing with model {model_name}: {e}")
            
            # Try fallback model if different
            if model_name != self.fallback_model and self.fallback_model in self._llm_instances:
                logger.info(f"Attempting with fallback model: {self.fallback_model}")
                return self._execute_with_model(
                    self.fallback_model, prompt, context, tools, **kwargs
                )
            
            raise
    
    def execute(
        self,
        task_description: str,
        context: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        **kwargs
    ) -> str:
        """
        Execute a task with automatic model selection.
        
        This method overrides the parent Agent's execute method to add
        intelligent model selection.
        
        Args:
            task_description: Description of the task to execute
            context: Optional context for the task
            tools: Optional tools to use
            **kwargs: Additional arguments
            
        Returns:
            Task execution result
        """
        # Estimate context size in tokens (rough estimate: ~4 chars per token)
        # This is a simplified heuristic; actual tokenization varies by model
        text_length = len(task_description) + (len(context) if context else 0)
        context_size = text_length // 4  # Approximate token count
        
        # Select the best model for this task
        selected_model = self._select_model_for_task(
            task_description=task_description,
            tools=tools,
            context_size=context_size
        )
        
        logger.info(f"RouterAgent '{self.name}' selected model: {selected_model} for task")
        
        # Execute with the selected model
        return self._execute_with_model(
            model_name=selected_model,
            prompt=task_description,
            context=context,
            tools=tools,
            **kwargs
        )
    
    def get_usage_report(self) -> Dict[str, Any]:
        """
        Get a report of model usage statistics.
        
        Returns:
            Dictionary containing usage statistics and cost estimates
        """
        total_cost = 0.0
        report = {
            'agent_name': self.name,
            'routing_strategy': self.routing_strategy,
            'model_usage': {}
        }
        
        for model, stats in self.model_usage_stats.items():
            model_info = self.model_router.get_model_info(model)
            if model_info and stats['tokens'] > 0:
                cost = self.model_router.estimate_cost(model, stats['tokens'])
                stats['cost'] = cost
                total_cost += cost
            
            report['model_usage'][model] = stats
        
        report['total_cost_estimate'] = total_cost
        report['total_calls'] = sum(s['calls'] for s in self.model_usage_stats.values())
        
        return report
    
    def _build_system_prompt(self) -> str:
        """Build system prompt (inherited from parent but can be customized)."""
        base_prompt = super()._build_system_prompt()
        
        # Add multi-model context if needed
        if self.routing_strategy == "auto":
            base_prompt += "\n\nNote: You are part of a multi-model system. Focus on your specific task."
        
        return base_prompt