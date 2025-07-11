import logging
import asyncio
import inspect
from typing import List, Optional, Dict, Any, Type, Callable, Union, Coroutine, Literal, Tuple, get_args, get_origin
from pydantic import BaseModel
from ..main import TaskOutput
from ..agent.agent import Agent
import uuid
import os
import time

# Set up logger
logger = logging.getLogger(__name__)

class Task:
    def __init__(
        self,
        description: str,
        expected_output: Optional[str] = None,
        agent: Optional[Agent] = None,
        name: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        context: Optional[List[Union[str, List, 'Task']]] = None,
        async_execution: Optional[bool] = False,
        config: Optional[Dict[str, Any]] = None,
        output_file: Optional[str] = None,
        output_json: Optional[Type[BaseModel]] = None,
        output_pydantic: Optional[Type[BaseModel]] = None,
        callback: Optional[Union[Callable[[TaskOutput], Any], Callable[[TaskOutput], Coroutine[Any, Any, Any]]]] = None,
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
        rerun: bool = False, # Renamed from can_rerun and logic inverted, default True for backward compatibility
        retain_full_context: bool = False, # By default, only use previous task output, not all previous tasks
        guardrail: Optional[Union[Callable[[TaskOutput], Tuple[bool, Any]], str]] = None,
        max_retries: int = 3,
        retry_count: int = 0
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

        self.input_file = input_file
        self.id = str(uuid.uuid4()) if id is None else str(id)
        self.name = name
        self.description = description
        self.expected_output = expected_output if expected_output is not None else "Complete the task successfully"
        self.agent = agent
        self.tools = tools if tools else []
        self.context = context if context else []
        self.async_execution = async_execution
        self.config = config if config else {}
        self.output_file = output_file
        self.output_json = output_json
        self.output_pydantic = output_pydantic
        self.callback = callback
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
        self.guardrail = guardrail
        self.max_retries = max_retries
        self.retry_count = retry_count
        self._guardrail_fn = None
        self.validation_feedback = None  # Store validation failure feedback for retry attempts

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
                return_annotation_args = get_args(return_annotation)
                if not (
                    get_origin(return_annotation) is tuple
                    and len(return_annotation_args) == 2
                    and return_annotation_args[0] is bool
                    and (
                        return_annotation_args[1] is Any
                        or return_annotation_args[1] is str
                        or return_annotation_args[1] is TaskOutput
                        or return_annotation_args[1] == Union[str, TaskOutput]
                    )
                ):
                    raise ValueError(
                        "If return type is annotated, it must be Tuple[bool, Any]"
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

        # Execute original callback
        if self.callback:
            try:
                if asyncio.iscoroutinefunction(self.callback):
                    await self.callback(task_output)
                else:
                    self.callback(task_output)
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
                        context_results.append(
                            f"Result of previous task {context_item.name if context_item.name else context_item.description}:\n{context_item.result.raw}"
                        )
                    else:
                        context_results.append(
                            f"Previous task {context_item.name if context_item.name else context_item.description} has no result yet."
                        )

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
            
            # Convert the result to a GuardrailResult
            return GuardrailResult.from_tuple(result)
            
        except Exception as e:
            logger.error(f"Task {self.id}: Error in guardrail validation: {e}")
            # On error, return failure
            return GuardrailResult(
                success=False,
                result=None,
                error=f"Guardrail validation error: {str(e)}"
            )