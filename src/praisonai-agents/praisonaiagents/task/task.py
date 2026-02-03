import logging
import asyncio
import inspect
from typing import List, Optional, Dict, Any, Type, Callable, Union, Coroutine, Literal, Tuple, get_args, get_origin
from pydantic import BaseModel
from ..output.models import TaskOutput
from ..agent.agent import Agent
import uuid
import os
import time

# Set up logger
logger = logging.getLogger(__name__)

class Task:
    """
    A unit of work that can be executed by an Agent or a custom handler function.
    
    Task is the unified abstraction for both AgentManager tasks and Workflow steps.
    It supports all features from the legacy Task class.
    
    Simple Usage:
        task = Task(description="Research AI trends")
        
    With action alias (from Task):
        task = Task(action="Write a blog post about {{topic}}")
        
    With custom handler function:
        task = Task(
            name="process_data",
            action="Process the input",
            handler=my_custom_function
        )
        
    With loop iteration:
        task = Task(
            action="Process {{item}}",
            loop_over="items",
            loop_var="item"
        )
    """
    def __init__(
        self,
        description: Optional[str] = None,
        expected_output: Optional[str] = None,
        agent: Optional[Agent] = None,
        name: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        context: Optional[List[Union[str, List, 'Task']]] = None,
        depends_on: Optional[List[Union[str, List, 'Task']]] = None,  # Alias for context (clearer semantics)
        async_execution: Optional[bool] = False,
        config: Optional[Dict[str, Any]] = None,
        output_file: Optional[str] = None,
        output_json: Optional[Type[BaseModel]] = None,
        output_pydantic: Optional[Type[BaseModel]] = None,
        callback: Optional[Union[Callable[[TaskOutput], Any], Callable[[TaskOutput], Coroutine[Any, Any, Any]]]] = None,
        on_task_complete: Optional[Union[Callable[[TaskOutput], Any], Callable[[TaskOutput], Coroutine[Any, Any, Any]]]] = None,
        status: str = "not started",
        result: Optional[TaskOutput] = None,
        create_directory: Optional[bool] = False,
        id: Optional[int] = None,
        images: Optional[List[str]] = None,
        next_tasks: Optional[List[str]] = None,
        task_type: str = "task",
        condition: Optional[Dict[str, List[str]]] = None,
        is_start: bool = False,
        loop_state: Optional[Dict[str, Union[str, int]]] = None,
        memory=None,
        quality_check=True,
        input_file: Optional[str] = None,
        rerun: bool = False,
        retain_full_context: bool = False,
        guardrail: Optional[Union[Callable[[TaskOutput], Tuple[bool, Any]], str]] = None,
        guardrails: Optional[Union[Callable[[TaskOutput], Tuple[bool, Any]], str]] = None,
        max_retries: int = 3,
        retry_count: int = 0,
        agent_config: Optional[Dict[str, Any]] = None,
        variables: Optional[Dict[str, Any]] = None,
        # ============================================================
        # ROBUSTNESS PARAMS (graceful degradation & retry control)
        # ============================================================
        skip_on_failure: bool = False,  # Allow workflow to continue if this task fails
        retry_delay: float = 0.0,  # Seconds between retries (supports exponential backoff)
        on_error: str = "stop",  # Flow control: "stop", "continue", or "retry"
        # ============================================================
        # NEW PARAMS FROM WORKFLOWSTEP (Phase 4 Consolidation)
        # ============================================================
        # Action alias - alternative to description (user-friendly)
        action: Optional[str] = None,
        # Handler function - custom function instead of agent
        handler: Optional[Callable] = None,
        # Condition function - check if task should run
        should_run: Optional[Callable] = None,
        # Loop support - iterate over a list
        loop_over: Optional[str] = None,
        loop_var: str = "item",
        # Consolidated config objects (from Task)
        execution: Optional[Any] = None,
        routing: Optional[Dict[str, List[str]]] = None,  # Renamed from condition for clarity
        output_config: Optional[Any] = None,
        # ============================================================
        # UNIFIED OUTPUT PARAMETER (consolidates all output configs)
        # ============================================================
        # Single output param that handles: file path (str), Pydantic model, TaskOutputConfig
        output: Optional[Any] = None,
        # ============================================================
        # UNIFIED CONDITION SYNTAX (same as AgentFlow)
        # ============================================================
        # String-based condition expression (e.g., "{{score}} > 80")
        when: Optional[str] = None,
        # Task to route to when condition is True
        then_task: Optional[str] = None,
        # Task to route to when condition is False
        else_task: Optional[str] = None,
        # Feature configs (from Task)
        autonomy: Optional[Any] = None,
        knowledge: Optional[Any] = None,
        web: Optional[Any] = None,
        reflection: Optional[Any] = None,
        planning: Optional[Any] = None,
        hooks: Optional[Any] = None,
        caching: Optional[Any] = None,
        # Output variable name for workflow variable assignment
        output_variable: Optional[str] = None,
    ):
        # Add check if memory config is provided
        if memory is not None or (config and config.get('memory_config')):
            try:
                from ..memory.memory import Memory
                MEMORY_AVAILABLE = True
            except ImportError as e:
                logger.warning(f"Memory dependency missing: {e}")
                logger.warning("Some memory features may not work. Install with: pip install \"praisonaiagents[memory]\"")
                MEMORY_AVAILABLE = False
                # Don't raise - let it continue with limited functionality

        # Handle action as alias for description (from Task)
        # If action provided but description not, use action as description
        if action is not None and description is None:
            description = action
        # Store both - action is the user-friendly alias
        self.action = action if action is not None else description
        
        # Validate that we have either description, action, or handler
        # A handler (callable) is valid on its own - it IS the task logic
        if description is None and handler is None:
            raise ValueError("Task requires either 'description', 'action', or 'handler' parameter")
        
        self.input_file = input_file
        self.id = str(uuid.uuid4()) if id is None else str(id)
        self.name = name
        self.description = description
        self.expected_output = expected_output if expected_output is not None else "Complete the task successfully"
        self.agent = agent
        self.tools = tools if tools else []
        # Handle depends_on as alias for context (depends_on takes precedence)
        if depends_on is not None:
            self.context = depends_on
        else:
            self.context = context if context else []
        # Store depends_on as property alias for context
        self._depends_on = self.context
        self.async_execution = async_execution
        self.config = config if config else {}
        self.output_file = output_file
        self.output_json = output_json
        self.output_pydantic = output_pydantic
        # Handle callback/on_task_complete: on_task_complete is canonical, callback is deprecated
        if callback is not None and on_task_complete is None:
            import warnings
            warnings.warn(
                "Parameter 'callback' is deprecated, use 'on_task_complete' instead. "
                "Example: Task(on_task_complete=my_fn) instead of Task(callback=my_fn)",
                DeprecationWarning,
                stacklevel=2
            )
            self.callback = callback
        elif callback is not None and on_task_complete is not None:
            raise ValueError(
                "Cannot specify both 'callback' and 'on_task_complete'. "
                "Use 'on_task_complete' only (callback is deprecated)."
            )
        else:
            # on_task_complete takes precedence (or both are None)
            self.callback = on_task_complete
        self.status = status
        self.result = result
        self.create_directory = create_directory
        self.images = images if images else []
        self.next_tasks = next_tasks if next_tasks else []
        self.task_type = task_type
        self.condition = condition if condition else {}
        self.is_start = is_start
        self.loop_state = loop_state if loop_state else {}
        self.memory = memory
        self.quality_check = quality_check
        self.rerun = rerun # Assigning the rerun parameter
        self.retain_full_context = retain_full_context
        # Handle guardrail/guardrails: guardrails (plural) is canonical, guardrail (singular) is deprecated
        if guardrail is not None and guardrails is None:
            import warnings
            warnings.warn(
                "Parameter 'guardrail' is deprecated, use 'guardrails' instead. "
                "Example: Task(guardrails=my_fn) instead of Task(guardrail=my_fn)",
                DeprecationWarning,
                stacklevel=2
            )
        # guardrails takes precedence over guardrail
        self.guardrail = guardrails if guardrails is not None else guardrail
        self.max_retries = max_retries
        self.retry_count = retry_count
        self._guardrail_fn = None
        self.validation_feedback = None  # Store validation failure feedback for retry attempts
        self.agent_config = agent_config  # Per-task agent configuration {role, goal, backstory, llm}
        self.variables = variables if variables else {}  # Variables for substitution in description

        # ============================================================
        # ROBUSTNESS PARAMS (graceful degradation & retry control)
        # ============================================================
        self.skip_on_failure = skip_on_failure
        self.retry_delay = retry_delay

        # ============================================================
        # NEW PARAMS FROM WORKFLOWSTEP (Phase 4 Consolidation)
        # ============================================================
        # Handler function - custom function instead of agent
        self.handler = handler
        # Condition function - check if task should run
        self.should_run = should_run
        # Loop support - iterate over a list
        self.loop_over = loop_over
        self.loop_var = loop_var
        # Consolidated config objects (from Task)
        self.execution = execution
        # Resolve on_error from execution config or direct param
        # execution config takes precedence if it has on_error set
        if execution is not None and hasattr(execution, 'on_error'):
            self.on_error = execution.on_error
        else:
            self.on_error = on_error
        # Handle routing parameter - use routing if provided, else fall back to condition
        if routing is not None:
            self.condition = routing
        self.routing = self.condition  # Alias for backward compat
        self.output_config = output_config
        # ============================================================
        # UNIFIED OUTPUT PARAMETER RESOLUTION
        # ============================================================
        # Resolve unified 'output' param (consolidates output_file, output_json, output_pydantic, output_config)
        # Priority: unified 'output' param > individual params (for backward compat)
        if output is not None:
            if isinstance(output, str):
                # String = file path
                self.output_file = output
            elif hasattr(output, 'model_fields') or hasattr(output, '__fields__'):
                # Pydantic model class (v2 or v1)
                if isinstance(output, type):
                    # It's a class, use for output_json
                    self.output_json = output
                else:
                    # It's an instance, use for output_pydantic
                    self.output_pydantic = type(output)
            elif hasattr(output, 'file') or hasattr(output, 'variable'):
                # TaskOutputConfig or similar config object
                if hasattr(output, 'file') and output.file:
                    self.output_file = output.file
                if hasattr(output, 'json_model') and output.json_model:
                    self.output_json = output.json_model
                if hasattr(output, 'pydantic_model') and output.pydantic_model:
                    self.output_pydantic = output.pydantic_model
                if hasattr(output, 'variable') and output.variable:
                    self.output_variable = output.variable
            elif isinstance(output, dict):
                # Dict config
                if 'file' in output:
                    self.output_file = output['file']
                if 'json_model' in output or 'json' in output:
                    self.output_json = output.get('json_model') or output.get('json')
                if 'pydantic_model' in output or 'pydantic' in output:
                    self.output_pydantic = output.get('pydantic_model') or output.get('pydantic')
                if 'variable' in output:
                    self.output_variable = output.get('variable')
        # Store the original output param for reference
        self.output = output
        # ============================================================
        # UNIFIED CONDITION SYNTAX (same as AgentFlow)
        # ============================================================
        self.when = when
        self.then_task = then_task
        self.else_task = else_task
        # Feature configs (from Task)
        self.autonomy = autonomy
        self.knowledge = knowledge
        self.web = web
        self.reflection = reflection
        self.planning = planning
        self.hooks = hooks
        self.caching = caching
        # Output variable name - for storing output in workflow variables
        # Only set from param if explicitly provided (unified output may have set it)
        if output_variable is not None:
            self.output_variable = output_variable
        elif not hasattr(self, 'output_variable'):
            self.output_variable = None

        # Set logger level based on config verbose level
        verbose = self.config.get("verbose", 0)
        if verbose >= 5:
            logger.setLevel(logging.INFO)
        else:
            logger.setLevel(logging.WARNING)

        # Also set third-party loggers to WARNING
        logging.getLogger('chromadb').setLevel(logging.WARNING)
        logging.getLogger('openai').setLevel(logging.WARNING)
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)

        if self.output_json and self.output_pydantic:
            raise ValueError("Only one output type can be defined")

        # Track previous tasks based on next_tasks relationships
        self.previous_tasks = []

        # If task_type="decision" and output_pydantic is not set
        if self.task_type == "decision" and not self.output_pydantic:
            from pydantic import BaseModel
            from typing import Literal

            # Gather condition keys for the "decision" field
            condition_keys = list(self.condition.keys())
            if not condition_keys:
                # Fall back to placeholders if nothing is specified
                condition_keys = ["next_task", "exit"]

            # Create a dynamic literal type from condition keys
            DecisionLiteral = Literal.__getitem__(tuple(condition_keys))

            class DecisionModel(BaseModel):
                response: str
                decision: DecisionLiteral

            self.output_pydantic = DecisionModel

        # If task_type="loop" and output_pydantic is not set
        if self.task_type == "loop" and not self.output_pydantic:
            from pydantic import BaseModel
            from typing import Literal

            # Gather condition keys for the "decision" field
            condition_keys = list(self.condition.keys())
            if not condition_keys:
                # Fall back to placeholders if nothing is specified
                condition_keys = ["next_item", "exit"]

            # Create a dynamic literal type
            LoopLiteral = Literal.__getitem__(tuple(condition_keys))

            class LoopModel(BaseModel):
                response: str
                decision: LoopLiteral
                loop_id: str  # Additional field for loop

            self.output_pydantic = LoopModel

        # Initialize guardrail
        self._setup_guardrail()

    @property
    def depends_on(self):
        """Alias for context - returns the list of dependent tasks."""
        return self.context
    
    @depends_on.setter
    def depends_on(self, value):
        """Alias for context - sets the list of dependent tasks."""
        self.context = value

    def _setup_guardrail(self):
        """Setup the guardrail function based on the provided guardrail parameter."""
        if self.guardrail is None:
            self._guardrail_fn = None
            return
            
        if callable(self.guardrail):
            # Validate function signature
            sig = inspect.signature(self.guardrail)
            positional_args = [
                param for param in sig.parameters.values()
                if param.default is inspect.Parameter.empty
            ]
            if len(positional_args) != 1:
                raise ValueError("Guardrail function must accept exactly one parameter (TaskOutput)")
            
            # Check return annotation if present
            return_annotation = sig.return_annotation
            if return_annotation != inspect.Signature.empty:
                # Import GuardrailResult for checking
                from ..guardrails import GuardrailResult
                
                # Check if it's a GuardrailResult type
                is_guardrail_result = return_annotation is GuardrailResult
                
                # Check for tuple return type
                return_annotation_args = get_args(return_annotation)
                is_tuple = (
                    get_origin(return_annotation) is tuple
                    and len(return_annotation_args) == 2
                    and return_annotation_args[0] is bool
                    and (
                        return_annotation_args[1] is Any
                        or return_annotation_args[1] is str
                        or return_annotation_args[1] is TaskOutput
                        or return_annotation_args[1] == Union[str, TaskOutput]
                    )
                )
                
                if not (is_guardrail_result or is_tuple):
                    raise ValueError(
                        "If return type is annotated, it must be GuardrailResult or Tuple[bool, Any]"
                    )
            
            self._guardrail_fn = self.guardrail
        elif isinstance(self.guardrail, str):
            # Create LLM-based guardrail
            from ..guardrails import LLMGuardrail
            if not self.agent:
                raise ValueError("Agent is required for string-based guardrails")
            llm = getattr(self.agent, 'llm', None) or getattr(self.agent, 'llm_instance', None)
            self._guardrail_fn = LLMGuardrail(description=self.guardrail, llm=llm)
        else:
            raise ValueError("Guardrail must be either a callable or a string description")

    def __str__(self):
        return f"Task(name='{self.name if self.name else 'None'}', description='{self.description}', agent='{self.agent.name if self.agent else 'None'}', status='{self.status}')"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the Task to a dictionary.
        
        Returns:
            Dictionary representation of the Task.
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "action": self.action,
            "expected_output": self.expected_output,
            "status": self.status,
            "task_type": self.task_type,
            "tools": self.tools,
            "context": [str(c) if hasattr(c, '__str__') else c for c in self.context] if self.context else [],
            "next_tasks": self.next_tasks,
            "condition": self.condition,
            "routing": self.routing,
            "is_start": self.is_start,
            "max_retries": self.max_retries,
            "async_execution": self.async_execution,
            "output_file": self.output_file,
            "output_variable": self.output_variable,
            "retain_full_context": self.retain_full_context,
            "loop_over": self.loop_over,
            "loop_var": self.loop_var,
            "when": self.when,
            "then_task": self.then_task,
            "else_task": self.else_task,
            "agent_config": self.agent_config,
            "variables": self.variables,
        }

    def initialize_memory(self):
        """Initialize memory if config exists but memory doesn't"""
        if not self.memory and self.config.get('memory_config'):
            try:
                from ..memory.memory import Memory
                logger.info(f"Task {self.id}: Initializing memory from config: {self.config['memory_config']}")
                self.memory = Memory(config=self.config['memory_config'])
                logger.info(f"Task {self.id}: Memory initialized successfully")

                # Verify database was created
                if os.path.exists(self.config['memory_config']['storage']['path']):
                    logger.info(f"Task {self.id}: Memory database exists after initialization")
                else:
                    logger.error(f"Task {self.id}: Failed to create memory database!")
                return self.memory
            except Exception as e:
                logger.error(f"Task {self.id}: Failed to initialize memory: {e}")
                logger.exception(e)
        return None

    def store_in_memory(self, content: str, agent_name: str = None, task_id: str = None):
        """Store content in memory with metadata"""
        if self.memory:
            try:
                logger.info(f"Task {self.id}: Storing content in memory...")
                self.memory.store_long_term(
                    text=content,
                    metadata={
                        "agent_name": agent_name or "Agent",
                        "task_id": task_id or self.id,
                        "timestamp": time.time()
                    }
                )
                logger.info(f"Task {self.id}: Content stored in memory")
            except Exception as e:
                logger.error(f"Task {self.id}: Failed to store content in memory: {e}")
                logger.exception(e)

    async def execute_callback(self, task_output: TaskOutput) -> None:
        """Execute callback and store quality metrics if enabled"""
        logger.info(f"Task {self.id}: execute_callback called")
        logger.info(f"Quality check enabled: {self.quality_check}")

        # Process guardrail if configured
        if self._guardrail_fn:
            try:
                guardrail_result = self._process_guardrail(task_output)
                if not guardrail_result.success:
                    if self.retry_count >= self.max_retries:
                        raise Exception(
                            f"Task failed guardrail validation after {self.max_retries} retries. "
                            f"Last error: {guardrail_result.error}"
                        )
                    
                    self.retry_count += 1
                    logger.warning(f"Task {self.id}: Guardrail validation failed (retry {self.retry_count}/{self.max_retries}): {guardrail_result.error}")
                    # Note: In a real execution, this would trigger a retry, but since this is a callback
                    # the retry logic would need to be handled at the agent/execution level
                    return
                
                # If guardrail passed and returned a modified result
                if guardrail_result.result is not None:
                    if isinstance(guardrail_result.result, str):
                        # Update the task output with the modified result
                        task_output.raw = guardrail_result.result
                    elif isinstance(guardrail_result.result, TaskOutput):
                        # Replace with the new task output
                        task_output = guardrail_result.result
                
                logger.info(f"Task {self.id}: Guardrail validation passed")
            except Exception as e:
                logger.error(f"Task {self.id}: Error in guardrail processing: {e}")
                # Continue execution even if guardrail fails to avoid breaking the task

        # Initialize memory if not already initialized
        if not self.memory:
            self.memory = self.initialize_memory()

        logger.info(f"Memory object exists: {self.memory is not None}")
        if self.memory:
            logger.info(f"Memory config: {self.memory.cfg}")
            # Store task output in memory
            try:
                logger.info(f"Task {self.id}: Storing task output in memory...")
                self.store_in_memory(
                    content=task_output.raw,
                    agent_name=self.agent.name if self.agent else "Agent",
                    task_id=self.id
                )
                logger.info(f"Task {self.id}: Task output stored in memory")
            except Exception as e:
                logger.error(f"Task {self.id}: Failed to store task output in memory: {e}")
                logger.exception(e)

        logger.info(f"Task output: {task_output.raw[:100]}...")

        if self.quality_check and self.memory:
            try:
                logger.info(f"Task {self.id}: Starting memory operations")
                logger.info(f"Task {self.id}: Calculating quality metrics for output: {task_output.raw[:100]}...")

                # Get quality metrics from LLM
                # Determine which LLM model to use based on agent configuration
                llm_model = None
                if self.agent:
                    if getattr(self.agent, '_using_custom_llm', False) and hasattr(self.agent, 'llm_instance'):
                        # For custom LLM instances (like Ollama)
                        # Extract the model name from the LLM instance
                        if hasattr(self.agent.llm_instance, 'model'):
                            llm_model = self.agent.llm_instance.model
                        else:
                            llm_model = "gpt-4o-mini"  # Default fallback
                    elif hasattr(self.agent, 'llm') and self.agent.llm:
                        # For standard model strings
                        llm_model = self.agent.llm
                
                metrics = self.memory.calculate_quality_metrics(
                    task_output.raw,
                    self.expected_output,
                    llm=llm_model
                )
                logger.info(f"Task {self.id}: Quality metrics calculated: {metrics}")

                quality_score = metrics.get("accuracy", 0.0)
                logger.info(f"Task {self.id}: Quality score: {quality_score}")

                # Store in both short and long-term memory with higher threshold
                logger.info(f"Task {self.id}: Finalizing task output in memory...")
                self.memory.finalize_task_output(
                    content=task_output.raw,
                    agent_name=self.agent.name if self.agent else "Agent",
                    quality_score=quality_score,
                    threshold=0.7,  # Only high quality outputs in long-term memory
                    metrics=metrics,
                    task_id=self.id
                )
                logger.info(f"Task {self.id}: Finalized task output in memory")

                # Store quality metrics separately
                logger.info(f"Task {self.id}: Storing quality metrics...")
                self.memory.store_quality(
                    text=task_output.raw,
                    quality_score=quality_score,
                    task_id=self.id,
                    metrics=metrics
                )

                # Store in both short and long-term memory with higher threshold
                self.memory.finalize_task_output(
                    content=task_output.raw,
                    agent_name=self.agent.name if self.agent else "Agent",
                    quality_score=quality_score,
                    threshold=0.7  # Only high quality outputs in long-term memory
                )

                # Build context for next tasks
                if self.next_tasks:
                    logger.info(f"Task {self.id}: Building context for next tasks...")
                    context = self.memory.build_context_for_task(
                        task_descr=task_output.raw,
                        max_items=5
                    )
                    logger.info(f"Task {self.id}: Built context for next tasks: {len(context)} items")

                logger.info(f"Task {self.id}: Memory operations complete")
            except Exception as e:
                logger.error(f"Task {self.id}: Failed to process memory operations: {e}")
                logger.exception(e)  # Print full stack trace
                # Continue execution even if memory operations fail

        # Execute original callback with metadata support
        if self.callback:
            try:
                await self._execute_callback_with_metadata(task_output)
            except Exception as e:
                logger.error(f"Task {self.id}: Failed to execute callback: {e}")
                logger.exception(e)

        task_prompt = f"""
You need to do the following task: {self.description}.
Expected Output: {self.expected_output}.
"""
        if self.context:
            context_results = []  # Use list to avoid duplicates
            for context_item in self.context:
                if isinstance(context_item, str):
                    context_results.append(f"Input Content:\n{context_item}")
                elif isinstance(context_item, list):
                    context_results.append(f"Input Content: {' '.join(str(x) for x in context_item)}")
                elif hasattr(context_item, 'result'):  # Task object
                    if context_item.result:
                        task_name = context_item.name if context_item.name else context_item.description
                        # Log detailed result for debugging
                        logger.debug(f"Previous task '{task_name}' result: {context_item.result.raw}")
                        # Include actual result content without verbose labels (essential for task chaining)
                        context_results.append(context_item.result.raw)
                    else:
                        # Task has no result yet, don't include verbose status message
                        pass

            # Join unique context results
            unique_contexts = list(dict.fromkeys(context_results))  # Remove duplicates
            task_prompt += f"""
Context:

{'  '.join(unique_contexts)}
"""

    def execute_callback_sync(self, task_output: TaskOutput) -> None:
        """
        Synchronous wrapper to ensure that execute_callback is awaited,
        preventing 'Task was destroyed but pending!' warnings if called
        from non-async code.
        """
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self.execute_callback(task_output))
            else:
                loop.run_until_complete(self.execute_callback(task_output))
        except RuntimeError:
            # If no loop is running in this context
            asyncio.run(self.execute_callback(task_output))

    def _process_guardrail(self, task_output: TaskOutput):
        """Process the guardrail validation for a task output.
        
        Args:
            task_output: The task output to validate
            
        Returns:
            GuardrailResult: The result of the guardrail validation
        """
        from ..guardrails import GuardrailResult
        
        if not self._guardrail_fn:
            return GuardrailResult(success=True, result=task_output)
        
        try:
            # Call the guardrail function
            result = self._guardrail_fn(task_output)
            
            # Check if result is already a GuardrailResult
            if isinstance(result, GuardrailResult):
                return result
            
            # Otherwise, convert the tuple result to a GuardrailResult
            return GuardrailResult.from_tuple(result)
            
        except Exception as e:
            logger.error(f"Task {self.id}: Error in guardrail validation: {e}")
            # On error, return failure
            return GuardrailResult(
                success=False,
                result=None,
                error=f"Guardrail validation error: {str(e)}"
            )
    
    async def _execute_callback_with_metadata(self, task_output):
        """Execute callback with metadata support while maintaining backward compatibility.
        
        This method automatically detects the callback signature:
        - Single parameter callbacks receive only TaskOutput (backward compatible)
        - Two parameter callbacks receive TaskOutput and metadata dict (enhanced)
        
        Args:
            task_output: The TaskOutput object to pass to the callback
        """
        if not self.callback:
            return
            
        try:
            # Inspect the callback signature to determine parameter count
            sig = inspect.signature(self.callback)
            param_count = len(sig.parameters)
            
            if param_count == 1:
                # Backward compatible: single parameter callback
                if asyncio.iscoroutinefunction(self.callback):
                    await self.callback(task_output)
                else:
                    self.callback(task_output)
            elif param_count >= 2:
                # Enhanced: two parameter callback with metadata
                metadata = {
                    'task_id': self.id,
                    'task_name': self.name,
                    'agent_name': self.agent.name if self.agent else None,
                    'task_type': self.task_type,
                    'task_status': self.status,
                    'task_description': self.description,
                    'expected_output': self.expected_output,
                    'input_file': getattr(self, 'input_file', None),
                    'loop_state': self.loop_state,
                    'retry_count': getattr(self, 'retry_count', 0),
                    'async_execution': self.async_execution
                }
                
                if asyncio.iscoroutinefunction(self.callback):
                    await self.callback(task_output, metadata)
                else:
                    self.callback(task_output, metadata)
            else:
                # No parameter callback - unusual but handle gracefully
                if asyncio.iscoroutinefunction(self.callback):
                    await self.callback()
                else:
                    self.callback()
                    
        except TypeError as e:
            # Fallback for signature inspection issues
            logger.warning(f"Task {self.id}: Callback signature inspection failed, falling back to single parameter: {e}")
            if asyncio.iscoroutinefunction(self.callback):
                await self.callback(task_output)
            else:
                self.callback(task_output)

    def evaluate_when(self, context: Dict[str, Any]) -> bool:
        """
        Evaluate the 'when' condition against the given context.
        
        Uses the shared evaluate_condition function from the conditions module
        for DRY compliance with AgentFlow condition evaluation.
        
        Args:
            context: Dictionary containing variables for evaluation.
                     May include workflow variables, previous outputs, etc.
            
        Returns:
            True if condition is met or no condition is set.
            False if condition is not met.
        """
        if self.when is None:
            return True
        
        from ..conditions.evaluator import evaluate_condition
        return evaluate_condition(
            self.when,
            context,
            previous_output=context.get('previous_output')
        )
    
    def get_next_task(self, context: Dict[str, Any]) -> Optional[str]:
        """
        Get the next task name based on the 'when' condition evaluation.
        
        This provides a simple routing mechanism for Task objects,
        similar to AgentFlow's when() function.
        
        Args:
            context: Dictionary containing variables for evaluation.
            
        Returns:
            then_task if condition is True, else_task if False.
            None if no routing is configured.
        """
        if self.when is None and self.then_task is None and self.else_task is None:
            return None
        
        if self.evaluate_when(context):
            return self.then_task
        else:
            return self.else_task