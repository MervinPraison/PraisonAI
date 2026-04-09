"""
Structured workflow execution with proper error handling.

Demonstrates how to replace string-based error handling with structured
result types that distinguish between recoverable and fatal errors.
"""

import logging
from typing import Optional, Dict, Any, List
from .results import StepResult, StepError, WorkflowResult, StepStatus, ErrorStrategy, WorkflowError, StepExecutionError
from ..errors import PraisonAIError
from ..agent.agent import Agent

logger = logging.getLogger(__name__)


class StructuredWorkflowExecutor:
    """
    Workflow executor that uses structured error handling.
    
    Replaces the pattern of converting exceptions to error strings
    with proper StepResult objects that enable retry logic and
    proper error propagation.
    """
    
    def __init__(self, default_agent: Optional[Agent] = None):
        self.default_agent = default_agent
        
    def execute_step_structured(
        self, 
        step_name: str,
        action: str,
        agent: Optional[Agent] = None,
        handler: Optional[callable] = None,
        context: Optional[Dict[str, Any]] = None,
        error_strategy: ErrorStrategy = ErrorStrategy.STOP,
        max_retries: int = 0,
        fallback_output: Optional[str] = None
    ) -> StepResult:
        """
        Execute a single workflow step with structured error handling.
        
        Args:
            step_name: Name of the step
            action: Action/prompt to execute
            agent: Agent to execute the step (optional if handler provided)
            handler: Custom handler function (optional if agent provided)
            context: Execution context variables
            error_strategy: How to handle errors (stop, skip, retry, fallback)
            max_retries: Maximum number of retries for failed steps
            
        Returns:
            StepResult with success/failure status and structured error info
        """
        import time
        start_time = time.time()
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                if handler:
                    # Custom handler function
                    result = handler(context or {})
                    if isinstance(result, StepResult):
                        return result
                    else:
                        output = str(result)
                        
                elif agent:
                    # Direct agent execution
                    output = agent.chat(action)
                    
                elif self.default_agent:
                    # Use default agent
                    output = self.default_agent.chat(action)
                    
                else:
                    # No execution mechanism available
                    error = StepError(
                        exception=ValueError("No agent or handler provided"),
                        step_name=step_name,
                        error_strategy=ErrorStrategy.STOP,
                        is_retryable=False,
                        fallback_output=fallback_output
                    )
                    return StepResult.failed_result(error, step_name)
                
                # Successful execution
                execution_time = (time.time() - start_time) * 1000
                return StepResult.success_result(
                    output=output,
                    step_name=step_name,
                    execution_time_ms=execution_time
                )
                
            except Exception as e:
                retry_count += 1
                
                # Determine if the error is retryable
                is_retryable = self._is_retryable_error(e) and retry_count <= max_retries
                
                # Create structured error
                step_error = StepError(
                    exception=e,
                    step_name=step_name,
                    retry_count=retry_count,
                    max_retries=max_retries,
                    is_retryable=is_retryable,
                    error_strategy=error_strategy,
                    fallback_output=fallback_output,
                    context=context or {}
                )
                
                if not is_retryable:
                    # Return failed result
                    return StepResult.failed_result(step_error, step_name)
                
                # Log retry attempt
                logger.warning(f"Step '{step_name}' failed (attempt {retry_count}/{max_retries + 1}): {e}")
                
                # Continue to retry
                continue
        
        # Max retries exceeded
        final_error = StepError(
            exception=RuntimeError(f"Max retries ({max_retries}) exceeded"),
            step_name=step_name,
            retry_count=retry_count,
            max_retries=max_retries,
            is_retryable=False,
            error_strategy=error_strategy,
            fallback_output=fallback_output,
            context=context or {}
        )
        
        return StepResult.failed_result(final_error, step_name)
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """
        Determine if an error is retryable.
        
        Returns True for network errors, rate limits, temporary failures.
        Returns False for validation errors, authentication issues, etc.
        """
        if isinstance(error, PraisonAIError):
            return error.is_retryable
        
        # Common retryable error patterns
        error_msg = str(error).lower()
        retryable_patterns = [
            'timeout', 'connection', 'network', 'rate limit', 
            'temporary', 'try again', 'service unavailable'
        ]
        
        return any(pattern in error_msg for pattern in retryable_patterns)
    
    def execute_workflow_structured(
        self,
        steps: List[Dict[str, Any]],
        variables: Optional[Dict[str, Any]] = None,
        error_strategy: ErrorStrategy = ErrorStrategy.STOP
    ) -> WorkflowResult:
        """
        Execute a complete workflow with structured error handling.
        
        Args:
            steps: List of step definitions
            variables: Workflow variables
            error_strategy: Default error handling strategy
            
        Returns:
            WorkflowResult with individual step results and overall status
        """
        import time
        start_time = time.time()
        
        step_results = []
        all_variables = variables or {}
        previous_output = ""
        
        for i, step_config in enumerate(steps):
            step_name = step_config.get('name', f'step_{i}')
            
            # Extract step configuration
            action = step_config.get('action', '')
            agent = step_config.get('agent')
            handler = step_config.get('handler')
            try:
                on_error = step_config.get('on_error', error_strategy.value)
                step_error_strategy = ErrorStrategy(on_error) if not isinstance(on_error, ErrorStrategy) else on_error
            except ValueError:
                logging.warning(f"Invalid error strategy '{on_error}', using default")
                step_error_strategy = error_strategy
                
            max_retries = step_config.get('max_retries', 0)
            fallback_output = step_config.get('fallback_output')
            
            # Substitute variables in action
            action = self._substitute_variables(action, all_variables, previous_output)
            
            # Execute step
            step_result = self.execute_step_structured(
                step_name=step_name,
                action=action,
                agent=agent,
                handler=handler,
                context=all_variables,
                error_strategy=step_error_strategy,
                max_retries=max_retries,
                fallback_output=fallback_output
            )
            
            step_results.append(step_result)
            
            # Handle step result
            if step_result.success:
                # Update variables and continue
                all_variables.update(step_result.variables)
                previous_output = step_result.output or ""
                
            elif step_result.failed:
                # Handle failure based on error strategy
                if step_result.error and step_result.error.should_stop_workflow:
                    # Stop workflow execution
                    break
                elif step_result.error and step_result.error.should_use_fallback:
                    # Use fallback output and continue
                    previous_output = step_result.error.get_output_for_next_step()
                elif step_error_strategy == ErrorStrategy.SKIP:
                    # Skip to next step
                    step_results[-1] = StepResult.skipped_result(
                        reason=f"Skipped due to error: {step_result.error.exception}",
                        step_name=step_name
                    )
                    continue
                else:
                    # Unknown strategy, stop workflow
                    break
        
        # Calculate overall success
        failed_steps = [r for r in step_results if r.failed]
        overall_success = len(failed_steps) == 0
        
        # Create summary
        error_summary = None
        if failed_steps:
            error_summary = f"{len(failed_steps)} of {len(step_results)} steps failed"
        
        total_time = (time.time() - start_time) * 1000
        
        return WorkflowResult(
            success=overall_success,
            steps=step_results,
            final_output=previous_output,
            error_summary=error_summary,
            total_execution_time_ms=total_time,
            variables=all_variables
        )
    
    def _substitute_variables(
        self, 
        text: str, 
        variables: Dict[str, Any], 
        previous_output: str
    ) -> str:
        """Substitute variables in text."""
        result = text
        
        # Replace {{previous_output}}
        result = result.replace('{{previous_output}}', str(previous_output))
        
        # Replace {{variable_name}} patterns
        for key, value in variables.items():
            pattern = f'{{{{{key}}}}}'
            result = result.replace(pattern, str(value))
        
        return result


# Example usage functions
def example_robust_workflow():
    """
    Example showing how to use structured workflow execution.
    
    This replaces error-string-based workflows with proper error handling
    that enables retry logic and prevents error strings from flowing
    as data to subsequent steps.
    """
    
    # Create executor with default agent
    agent = Agent(name="workflow_agent", instructions="Complete tasks step by step")
    executor = StructuredWorkflowExecutor(default_agent=agent)
    
    # Define workflow steps with error handling strategies
    steps = [
        {
            'name': 'research',
            'action': 'Research the topic: {{topic}}',
            'on_error': 'retry',
            'max_retries': 3
        },
        {
            'name': 'analyze', 
            'action': 'Analyze the research: {{previous_output}}',
            'on_error': 'fallback',
            'fallback_output': 'Analysis unavailable due to research failure'
        },
        {
            'name': 'report',
            'action': 'Write a report based on: {{previous_output}}',
            'on_error': 'stop'
        }
    ]
    
    # Execute workflow
    result = executor.execute_workflow_structured(
        steps=steps,
        variables={'topic': 'AI safety'},
        error_strategy=ErrorStrategy.STOP
    )
    
    # Handle workflow result
    if result.success:
        print(f"Workflow completed successfully: {result.final_output}")
    else:
        print(f"Workflow failed: {result.error_summary}")
        
        # Inspect failed steps for debugging
        for step in result.failed_steps:
            print(f"Step '{step.step_name}' failed: {step.error.exception}")
            if step.error.can_retry:
                print(f"  - Can be retried ({step.error.retry_count}/{step.error.max_retries})")
    
    return result


# Export main classes
__all__ = [
    "StructuredWorkflowExecutor"
]