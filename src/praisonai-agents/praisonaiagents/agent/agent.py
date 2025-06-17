import os
import time
import json
import logging
import asyncio
from typing import List, Optional, Any, Dict, Union, Literal, TYPE_CHECKING, Callable, Tuple
from rich.console import Console
from rich.live import Live
from openai import AsyncOpenAI
from ..main import (
    display_error,
    display_tool_call,
    display_instruction,
    display_interaction,
    display_generating,
    display_self_reflection,
    ReflectionOutput,
    client,
    adisplay_instruction,
    approval_callback
)
import inspect
import uuid
from dataclasses import dataclass

# Global variables for API server
_server_started = {}  # Dict of port -> started boolean
_registered_agents = {}  # Dict of port -> Dict of path -> agent_id
_shared_apps = {}  # Dict of port -> FastAPI app

# Don't import FastAPI dependencies here - use lazy loading instead

if TYPE_CHECKING:
    from ..task.task import Task
    from ..main import TaskOutput

@dataclass
class ChatCompletionMessage:
    content: str
    role: str = "assistant"
    refusal: Optional[str] = None
    audio: Optional[str] = None
    function_call: Optional[dict] = None
    tool_calls: Optional[List] = None
    reasoning_content: Optional[str] = None

@dataclass
class Choice:
    finish_reason: Optional[str]
    index: int
    message: ChatCompletionMessage
    logprobs: Optional[dict] = None

@dataclass
class CompletionTokensDetails:
    accepted_prediction_tokens: Optional[int] = None
    audio_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    rejected_prediction_tokens: Optional[int] = None

@dataclass
class PromptTokensDetails:
    audio_tokens: Optional[int] = None
    cached_tokens: int = 0

@dataclass
class CompletionUsage:
    completion_tokens: int = 0
    prompt_tokens: int = 0
    total_tokens: int = 0
    completion_tokens_details: Optional[CompletionTokensDetails] = None
    prompt_tokens_details: Optional[PromptTokensDetails] = None
    prompt_cache_hit_tokens: int = 0
    prompt_cache_miss_tokens: int = 0

@dataclass
class ChatCompletion:
    id: str
    choices: List[Choice]
    created: int
    model: str
    object: str = "chat.completion"
    system_fingerprint: Optional[str] = None
    service_tier: Optional[str] = None
    usage: Optional[CompletionUsage] = None

def safe_get_response_content(response):
    """Safely extract content from response, handling None responses and missing choices"""
    if not response:
        return None
    if not hasattr(response, 'choices') or not response.choices:
        return None
    if len(response.choices) == 0:
        return None
    return response.choices[0].message.content

def safe_get_response_message(response):
    """Safely extract message from response, handling None responses and missing choices"""
    if not response:
        return None
    if not hasattr(response, 'choices') or not response.choices:
        return None
    if len(response.choices) == 0:
        return None
    return response.choices[0].message

def process_stream_chunks(chunks):
    """Process streaming chunks into combined response"""
    if not chunks:
        return None
    
    try:
        first_chunk = chunks[0]
        last_chunk = chunks[-1]
        
        # Basic metadata
        id = getattr(first_chunk, "id", None) 
        created = getattr(first_chunk, "created", None)
        model = getattr(first_chunk, "model", None)
        system_fingerprint = getattr(first_chunk, "system_fingerprint", None)
        
        # Track usage
        completion_tokens = 0
        prompt_tokens = 0
        
        content_list = []
        reasoning_list = []
        tool_calls = []
        current_tool_call = None

        # First pass: Get initial tool call data
        for chunk in chunks:
            if not hasattr(chunk, "choices") or not chunk.choices:
                continue
            
            delta = getattr(chunk.choices[0], "delta", None)
            if not delta:
                continue

            # Handle content and reasoning
            if hasattr(delta, "content") and delta.content:
                content_list.append(delta.content)
            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                reasoning_list.append(delta.reasoning_content)
            
            # Handle tool calls
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tool_call_delta in delta.tool_calls:
                    if tool_call_delta.index is not None and tool_call_delta.id:
                        # Found the initial tool call
                        current_tool_call = {
                            "id": tool_call_delta.id,
                            "type": "function",
                            "function": {
                                "name": tool_call_delta.function.name,
                                "arguments": ""
                            }
                        }
                        while len(tool_calls) <= tool_call_delta.index:
                            tool_calls.append(None)
                        tool_calls[tool_call_delta.index] = current_tool_call
                        current_tool_call = tool_calls[tool_call_delta.index]
                    elif current_tool_call is not None and hasattr(tool_call_delta.function, "arguments"):
                        if tool_call_delta.function.arguments:
                            current_tool_call["function"]["arguments"] += tool_call_delta.function.arguments

        # Remove any None values and empty tool calls
        tool_calls = [tc for tc in tool_calls if tc and tc["id"] and tc["function"]["name"]]

        combined_content = "".join(content_list) if content_list else ""
        combined_reasoning = "".join(reasoning_list) if reasoning_list else None
        finish_reason = getattr(last_chunk.choices[0], "finish_reason", None) if hasattr(last_chunk, "choices") and last_chunk.choices else None

        # Create ToolCall objects
        processed_tool_calls = []
        if tool_calls:
            try:
                from openai.types.chat import ChatCompletionMessageToolCall
                for tc in tool_calls:
                    tool_call = ChatCompletionMessageToolCall(
                        id=tc["id"],
                        type=tc["type"],
                        function={
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"]
                        }
                    )
                    processed_tool_calls.append(tool_call)
            except Exception as e:
                print(f"Error processing tool call: {e}")

        message = ChatCompletionMessage(
            content=combined_content,
            role="assistant",
            reasoning_content=combined_reasoning,
            tool_calls=processed_tool_calls if processed_tool_calls else None
        )
        
        choice = Choice(
            finish_reason=finish_reason or "tool_calls" if processed_tool_calls else None,
            index=0,
            message=message
        )

        usage = CompletionUsage(
            completion_tokens=completion_tokens,
            prompt_tokens=prompt_tokens,
            total_tokens=completion_tokens + prompt_tokens,
            completion_tokens_details=CompletionTokensDetails(),
            prompt_tokens_details=PromptTokensDetails()
        )
        
        return ChatCompletion(
            id=id,
            choices=[choice],
            created=created,
            model=model,
            system_fingerprint=system_fingerprint,
            usage=usage
        )
        
    except Exception as e:
        print(f"Error processing chunks: {e}")
        return None

class Agent:
    def _generate_tool_definition(self, function_name):
        """
        Generate a tool definition from a function name by inspecting the function.
        """
        logging.debug(f"Attempting to generate tool definition for: {function_name}")
        
        # First try to get the tool definition if it exists
        tool_def_name = f"{function_name}_definition"
        tool_def = globals().get(tool_def_name)
        logging.debug(f"Looking for {tool_def_name} in globals: {tool_def is not None}")
        
        if not tool_def:
            import __main__
            tool_def = getattr(__main__, tool_def_name, None)
            logging.debug(f"Looking for {tool_def_name} in __main__: {tool_def is not None}")
        
        if tool_def:
            logging.debug(f"Found tool definition: {tool_def}")
            return tool_def

        # Try to find the function in the agent's tools list first
        func = None
        for tool in self.tools:
            if callable(tool) and getattr(tool, '__name__', '') == function_name:
                func = tool
                break
        
        logging.debug(f"Looking for {function_name} in agent tools: {func is not None}")
        
        # If not found in tools, try globals and main
        if not func:
            func = globals().get(function_name)
            logging.debug(f"Looking for {function_name} in globals: {func is not None}")
            
            if not func:
                import __main__
                func = getattr(__main__, function_name, None)
                logging.debug(f"Looking for {function_name} in __main__: {func is not None}")

        if not func or not callable(func):
            logging.debug(f"Function {function_name} not found or not callable")
            return None

        import inspect
        # Langchain tools
        if inspect.isclass(func) and hasattr(func, 'run') and not hasattr(func, '_run'):
            original_func = func
            func = func.run
            function_name = original_func.__name__
        # CrewAI tools
        elif inspect.isclass(func) and hasattr(func, '_run'):
            original_func = func
            func = func._run
            function_name = original_func.__name__

        sig = inspect.signature(func)
        logging.debug(f"Function signature: {sig}")
        
        # Skip self, *args, **kwargs, so they don't get passed in arguments
        parameters_list = []
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            parameters_list.append((name, param))

        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        # Parse docstring for parameter descriptions
        docstring = inspect.getdoc(func)
        logging.debug(f"Function docstring: {docstring}")
        
        param_descriptions = {}
        if docstring:
            import re
            param_section = re.split(r'\s*Args:\s*', docstring)
            logging.debug(f"Param section split: {param_section}")
            if len(param_section) > 1:
                param_lines = param_section[1].split('\n')
                for line in param_lines:
                    line = line.strip()
                    if line and ':' in line:
                        param_name, param_desc = line.split(':', 1)
                        param_descriptions[param_name.strip()] = param_desc.strip()
        
        logging.debug(f"Parameter descriptions: {param_descriptions}")

        for name, param in parameters_list:
            param_type = "string"  # Default type
            if param.annotation != inspect.Parameter.empty:
                if param.annotation == int:
                    param_type = "integer"
                elif param.annotation == float:
                    param_type = "number"
                elif param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation == list:
                    param_type = "array"
                elif param.annotation == dict:
                    param_type = "object"
            
            param_info = {"type": param_type}
            if name in param_descriptions:
                param_info["description"] = param_descriptions[name]
            
            parameters["properties"][name] = param_info
            if param.default == inspect.Parameter.empty:
                parameters["required"].append(name)
        
        logging.debug(f"Generated parameters: {parameters}")

        # Extract description from docstring
        description = docstring.split('\n')[0] if docstring else f"Function {function_name}"
        
        tool_def = {
            "type": "function",
            "function": {
                "name": function_name,
                "description": description,
                "parameters": parameters
            }
        }
        logging.debug(f"Generated tool definition: {tool_def}")
        return tool_def

    def __init__(
        self,
        name: Optional[str] = None,
        role: Optional[str] = None,
        goal: Optional[str] = None,
        backstory: Optional[str] = None,
        instructions: Optional[str] = None,
        llm: Optional[Union[str, Any]] = None,
        tools: Optional[List[Any]] = None,
        function_calling_llm: Optional[Any] = None,
        max_iter: int = 20,
        max_rpm: Optional[int] = None,
        max_execution_time: Optional[int] = None,
        memory: Optional[Any] = None,
        verbose: bool = True,
        allow_delegation: bool = False,
        step_callback: Optional[Any] = None,
        cache: bool = True,
        system_template: Optional[str] = None,
        prompt_template: Optional[str] = None,
        response_template: Optional[str] = None,
        allow_code_execution: Optional[bool] = False,
        max_retry_limit: int = 2,
        respect_context_window: bool = True,
        code_execution_mode: Literal["safe", "unsafe"] = "safe",
        embedder_config: Optional[Dict[str, Any]] = None,
        knowledge: Optional[List[str]] = None,
        knowledge_config: Optional[Dict[str, Any]] = None,
        use_system_prompt: Optional[bool] = True,
        markdown: bool = True,
        self_reflect: bool = False,
        max_reflect: int = 3,
        min_reflect: int = 1,
        reflect_llm: Optional[str] = None,
        reflect_prompt: Optional[str] = None,
        user_id: Optional[str] = None,
        reasoning_steps: bool = False,
        guardrail: Optional[Union[Callable[['TaskOutput'], Tuple[bool, Any]], str]] = None,
        max_guardrail_retries: int = 3
    ):
        """Initialize an Agent instance.

        Args:
            name (Optional[str], optional): Name of the agent used for identification and logging.
                If None, defaults to "Agent". Defaults to None.
            role (Optional[str], optional): Role or job title that defines the agent's expertise
                and behavior patterns. Examples: "Data Analyst", "Content Writer". Defaults to None.
            goal (Optional[str], optional): Primary objective or goal the agent aims to achieve.
                Defines the agent's purpose and success criteria. Defaults to None.
            backstory (Optional[str], optional): Background story or context that shapes the agent's
                personality and decision-making approach. Defaults to None.
            instructions (Optional[str], optional): Direct instructions that override role, goal,
                and backstory when provided. Used for simple, task-specific agents. Defaults to None.
            llm (Optional[Union[str, Any]], optional): Language model configuration. Can be a model
                name string (e.g., "gpt-4o", "anthropic/claude-3-sonnet") or a configured LLM object.
                Defaults to environment variable OPENAI_MODEL_NAME or "gpt-4o".
            tools (Optional[List[Any]], optional): List of tools, functions, or capabilities
                available to the agent for task execution. Can include callables, tool objects,
                or MCP instances. Defaults to None.
            function_calling_llm (Optional[Any], optional): Dedicated language model for function
                calling operations. If None, uses the main llm parameter. Defaults to None.
            max_iter (int, optional): Maximum number of iterations the agent can perform during
                task execution to prevent infinite loops. Defaults to 20.
            max_rpm (Optional[int], optional): Maximum requests per minute to rate limit API calls
                and prevent quota exhaustion. If None, no rate limiting is applied. Defaults to None.
            max_execution_time (Optional[int], optional): Maximum execution time in seconds for
                agent operations before timeout. If None, no time limit is enforced. Defaults to None.
            memory (Optional[Any], optional): Memory system for storing and retrieving information
                across conversations. Requires memory dependencies to be installed. Defaults to None.
            verbose (bool, optional): Enable detailed logging and status updates during agent
                execution for debugging and monitoring. Defaults to True.
            allow_delegation (bool, optional): Allow the agent to delegate tasks to other agents
                or sub-processes when appropriate. Defaults to False.
            step_callback (Optional[Any], optional): Callback function called after each step
                of agent execution for custom monitoring or intervention. Defaults to None.
            cache (bool, optional): Enable caching of responses and computations to improve
                performance and reduce API costs. Defaults to True.
            system_template (Optional[str], optional): Custom template for system prompts that
                overrides the default system prompt generation. Defaults to None.
            prompt_template (Optional[str], optional): Template for formatting user prompts
                before sending to the language model. Defaults to None.
            response_template (Optional[str], optional): Template for formatting agent responses
                before returning to the user. Defaults to None.
            allow_code_execution (Optional[bool], optional): Enable the agent to execute code
                snippets during task completion. Use with caution for security. Defaults to False.
            max_retry_limit (int, optional): Maximum number of retry attempts for failed operations
                before giving up. Helps handle transient errors. Defaults to 2.
            respect_context_window (bool, optional): Automatically manage context window size
                to prevent token limit errors with large conversations. Defaults to True.
            code_execution_mode (Literal["safe", "unsafe"], optional): Safety mode for code execution.
                "safe" restricts dangerous operations, "unsafe" allows full code execution. Defaults to "safe".
            embedder_config (Optional[Dict[str, Any]], optional): Configuration dictionary for
                text embedding models used in knowledge retrieval and similarity search. Defaults to None.
            knowledge (Optional[List[str]], optional): List of knowledge sources (file paths, URLs,
                or text content) to be processed and made available to the agent. Defaults to None.
            knowledge_config (Optional[Dict[str, Any]], optional): Configuration for knowledge
                processing and retrieval system including chunking and indexing parameters. Defaults to None.
            use_system_prompt (Optional[bool], optional): Whether to include system prompts in
                conversations to establish agent behavior and context. Defaults to True.
            markdown (bool, optional): Enable markdown formatting in agent responses for better
                readability and structure. Defaults to True.
            self_reflect (bool, optional): Enable self-reflection capabilities where the agent
                evaluates and improves its own responses. Defaults to False.
            max_reflect (int, optional): Maximum number of self-reflection iterations to prevent
                excessive reflection loops. Defaults to 3.
            min_reflect (int, optional): Minimum number of self-reflection iterations required
                before accepting a response as satisfactory. Defaults to 1.
            reflect_llm (Optional[str], optional): Dedicated language model for self-reflection
                operations. If None, uses the main llm parameter. Defaults to None.
            reflect_prompt (Optional[str], optional): Custom prompt template for self-reflection
                that guides the agent's self-evaluation process. Defaults to None.
            user_id (Optional[str], optional): Unique identifier for the user or session to
                enable personalized responses and memory isolation. Defaults to "praison".
            reasoning_steps (bool, optional): Enable step-by-step reasoning output to show the
                agent's thought process during problem solving. Defaults to False.
            guardrail (Optional[Union[Callable[['TaskOutput'], Tuple[bool, Any]], str]], optional):
                Safety mechanism to validate agent outputs. Can be a validation function or
                description string for LLM-based validation. Defaults to None.
            max_guardrail_retries (int, optional): Maximum number of retry attempts when guardrail
                validation fails before giving up. Defaults to 3.

        Raises:
            ValueError: If all of name, role, goal, backstory, and instructions are None.
            ImportError: If memory or LLM features are requested but dependencies are not installed.
        """
        # Add check at start if memory is requested
        if memory is not None:
            try:
                from ..memory.memory import Memory
                MEMORY_AVAILABLE = True
            except ImportError:
                raise ImportError(
                    "Memory features requested in Agent but memory dependencies not installed. "
                    "Please install with: pip install \"praisonaiagents[memory]\""
                )

        # Handle backward compatibility for required fields
        if all(x is None for x in [name, role, goal, backstory, instructions]):
            raise ValueError("At least one of name, role, goal, backstory, or instructions must be provided")

        # Configure logging to suppress unwanted outputs
        logging.getLogger("litellm").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

        # If instructions are provided, use them to set role, goal, and backstory
        if instructions:
            self.name = name or "Agent"
            self.role = role or "Assistant"
            self.goal = goal or instructions
            self.backstory = backstory or instructions
            # Set self_reflect to False by default for instruction-based agents
            self.self_reflect = False if self_reflect is None else self_reflect
        else:
            # Use provided values or defaults
            self.name = name or "Agent"
            self.role = role or "Assistant"
            self.goal = goal or "Help the user with their tasks"
            self.backstory = backstory or "I am an AI assistant"
            # Default to True for traditional agents if not specified
            self.self_reflect = True if self_reflect is None else self_reflect
        
        self.instructions = instructions
        # Check for model name in environment variable if not provided
        self._using_custom_llm = False

        # If the user passes a dictionary (for advanced configuration)
        if isinstance(llm, dict) and "model" in llm:
            try:
                from ..llm.llm import LLM
                self.llm_instance = LLM(**llm)  # Pass all dict items as kwargs
                self._using_custom_llm = True
            except ImportError as e:
                raise ImportError(
                    "LLM features requested but dependencies not installed. "
                    "Please install with: pip install \"praisonaiagents[llm]\""
                ) from e
        # If the user passes a string with a slash (provider/model)
        elif isinstance(llm, str) and "/" in llm:
            try:
                from ..llm.llm import LLM
                # Pass the entire string so LiteLLM can parse provider/model
                self.llm_instance = LLM(model=llm)
                self._using_custom_llm = True
                
                # Ensure tools are properly accessible when using custom LLM
                if tools:
                    logging.debug(f"Tools passed to Agent with custom LLM: {tools}")
                    # Store the tools for later use
                    self.tools = tools
            except ImportError as e:
                raise ImportError(
                    "LLM features requested but dependencies not installed. "
                    "Please install with: pip install \"praisonaiagents[llm]\""
                ) from e
        # Otherwise, fall back to OpenAI environment/name
        else:
            self.llm = llm or os.getenv('OPENAI_MODEL_NAME', 'gpt-4o')
        self.tools = tools if tools else []  # Store original tools
        self.function_calling_llm = function_calling_llm
        self.max_iter = max_iter
        self.max_rpm = max_rpm
        self.max_execution_time = max_execution_time
        self.memory = memory
        self.verbose = verbose
        self.allow_delegation = allow_delegation
        self.step_callback = step_callback
        self.cache = cache
        self.system_template = system_template
        self.prompt_template = prompt_template
        self.response_template = response_template
        self.allow_code_execution = allow_code_execution
        self.max_retry_limit = max_retry_limit
        self.respect_context_window = respect_context_window
        self.code_execution_mode = code_execution_mode
        self.embedder_config = embedder_config
        self.knowledge = knowledge
        self.use_system_prompt = use_system_prompt
        self.chat_history = []
        self.markdown = markdown
        self.max_reflect = max_reflect
        self.min_reflect = min_reflect
        self.reflect_prompt = reflect_prompt
        # Use the same model selection logic for reflect_llm
        self.reflect_llm = reflect_llm or os.getenv('OPENAI_MODEL_NAME', 'gpt-4o')
        self.console = Console()  # Create a single console instance for the agent
        
        # Initialize system prompt
        self.system_prompt = f"""{self.backstory}\n
Your Role: {self.role}\n
Your Goal: {self.goal}
        """

        # Generate unique IDs
        self.agent_id = str(uuid.uuid4())

        # Store user_id
        self.user_id = user_id or "praison"
        self.reasoning_steps = reasoning_steps
        
        # Initialize guardrail settings
        self.guardrail = guardrail
        self.max_guardrail_retries = max_guardrail_retries
        self._guardrail_fn = None
        self._setup_guardrail()

        # Check if knowledge parameter has any values
        if not knowledge:
            self.knowledge = None
        else:
            # Initialize Knowledge with provided or default config
            from praisonaiagents.knowledge import Knowledge
            self.knowledge = Knowledge(knowledge_config or None)
            
            # Handle knowledge
            if knowledge:
                for source in knowledge:
                    self._process_knowledge(source)

    def _process_knowledge(self, knowledge_item):
        """Process and store knowledge from a file path, URL, or string."""
        try:
            if os.path.exists(knowledge_item):
                # It's a file path
                self.knowledge.add(knowledge_item, user_id=self.user_id, agent_id=self.agent_id)
            elif knowledge_item.startswith("http://") or knowledge_item.startswith("https://"):
                # It's a URL
                pass
            else:
                # It's a string content
                self.knowledge.store(knowledge_item, user_id=self.user_id, agent_id=self.agent_id)
        except Exception as e:
            logging.error(f"Error processing knowledge item: {knowledge_item}, error: {e}")

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
                raise ValueError("Agent guardrail function must accept exactly one parameter (TaskOutput)")
            
            # Check return annotation if present
            from typing import get_args, get_origin
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
                        or str(return_annotation_args[1]).endswith('TaskOutput')
                        or str(return_annotation_args[1]).startswith('typing.Union')
                    )
                ):
                    raise ValueError(
                        "If return type is annotated, it must be Tuple[bool, Any] or Tuple[bool, Union[str, TaskOutput]]"
                    )
            
            self._guardrail_fn = self.guardrail
        elif isinstance(self.guardrail, str):
            # Create LLM-based guardrail
            from ..guardrails import LLMGuardrail
            llm = getattr(self, 'llm', None) or getattr(self, 'llm_instance', None)
            self._guardrail_fn = LLMGuardrail(description=self.guardrail, llm=llm)
        else:
            raise ValueError("Agent guardrail must be either a callable or a string description")

    def _process_guardrail(self, task_output):
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
            logging.error(f"Agent {self.name}: Error in guardrail validation: {e}")
            # On error, return failure
            return GuardrailResult(
                success=False,
                result=None,
                error=f"Agent guardrail validation error: {str(e)}"
            )

    def _apply_guardrail_with_retry(self, response_text, prompt, temperature=0.2, tools=None):
        """Apply guardrail validation with retry logic.
        
        Args:
            response_text: The response to validate
            prompt: Original prompt for regeneration if needed
            temperature: Temperature for regeneration
            tools: Tools for regeneration
            
        Returns:
            str: The validated response text or None if validation fails after retries
        """
        if not self._guardrail_fn:
            return response_text
            
        from ..main import TaskOutput
        
        retry_count = 0
        current_response = response_text
        
        while retry_count <= self.max_guardrail_retries:
            # Create TaskOutput object
            task_output = TaskOutput(
                description="Agent response output",
                raw=current_response,
                agent=self.name
            )
            
            # Process guardrail
            guardrail_result = self._process_guardrail(task_output)
            
            if guardrail_result.success:
                logging.info(f"Agent {self.name}: Guardrail validation passed")
                # Return the potentially modified result
                if guardrail_result.result and hasattr(guardrail_result.result, 'raw'):
                    return guardrail_result.result.raw
                elif guardrail_result.result:
                    return str(guardrail_result.result)
                else:
                    return current_response
            
            # Guardrail failed
            if retry_count >= self.max_guardrail_retries:
                raise Exception(
                    f"Agent {self.name} response failed guardrail validation after {self.max_guardrail_retries} retries. "
                    f"Last error: {guardrail_result.error}"
                )
            
            retry_count += 1
            logging.warning(f"Agent {self.name}: Guardrail validation failed (retry {retry_count}/{self.max_guardrail_retries}): {guardrail_result.error}")
            
            # Regenerate response for retry
            try:
                retry_prompt = f"{prompt}\n\nNote: Previous response failed validation due to: {guardrail_result.error}. Please provide an improved response."
                response = self._chat_completion([{"role": "user", "content": retry_prompt}], temperature, tools)
                if response and response.choices:
                    current_response = response.choices[0].message.content.strip()
                else:
                    raise Exception("Failed to generate retry response")
            except Exception as e:
                logging.error(f"Agent {self.name}: Error during guardrail retry: {e}")
                # If we can't regenerate, fail the guardrail
                raise Exception(
                    f"Agent {self.name} guardrail retry failed: {e}"
                )
        
        return current_response

    def generate_task(self) -> 'Task':
        """Generate a Task object from the agent's instructions"""
        from ..task.task import Task
        
        description = self.instructions if self.instructions else f"Execute task as {self.role} with goal: {self.goal}"
        expected_output = "Complete the assigned task successfully"
        
        return Task(
            name=self.name,
            description=description,
            expected_output=expected_output,
            agent=self,
            tools=self.tools
        )

    def _cast_arguments(self, func, arguments):
        """Cast arguments to their expected types based on function signature."""
        if not callable(func) or not arguments:
            return arguments
        
        try:
            sig = inspect.signature(func)
            casted_args = {}
            
            for param_name, arg_value in arguments.items():
                if param_name in sig.parameters:
                    param = sig.parameters[param_name]
                    if param.annotation != inspect.Parameter.empty:
                        # Handle common type conversions
                        if param.annotation == int and isinstance(arg_value, (str, float)):
                            try:
                                casted_args[param_name] = int(float(arg_value))
                            except (ValueError, TypeError):
                                casted_args[param_name] = arg_value
                        elif param.annotation == float and isinstance(arg_value, (str, int)):
                            try:
                                casted_args[param_name] = float(arg_value)
                            except (ValueError, TypeError):
                                casted_args[param_name] = arg_value
                        elif param.annotation == bool and isinstance(arg_value, str):
                            casted_args[param_name] = arg_value.lower() in ('true', '1', 'yes', 'on')
                        else:
                            casted_args[param_name] = arg_value
                    else:
                        casted_args[param_name] = arg_value
                else:
                    casted_args[param_name] = arg_value
            
            return casted_args
        except Exception as e:
            logging.debug(f"Type casting failed for {getattr(func, '__name__', 'unknown function')}: {e}")
            return arguments

    def execute_tool(self, function_name, arguments):
        """
        Execute a tool dynamically based on the function name and arguments.
        """
        logging.debug(f"{self.name} executing tool {function_name} with arguments: {arguments}")

        # Check if approval is required for this tool
        from ..approval import is_approval_required, console_approval_callback, get_risk_level, mark_approved, ApprovalDecision
        if is_approval_required(function_name):
            risk_level = get_risk_level(function_name)
            logging.info(f"Tool {function_name} requires approval (risk level: {risk_level})")
            
            # Use global approval callback or default console callback
            callback = approval_callback or console_approval_callback
            
            try:
                decision = callback(function_name, arguments, risk_level)
                if not decision.approved:
                    error_msg = f"Tool execution denied: {decision.reason}"
                    logging.warning(error_msg)
                    return {"error": error_msg, "approval_denied": True}
                
                # Mark as approved in context to prevent double approval in decorator
                mark_approved(function_name)
                
                # Use modified arguments if provided
                if decision.modified_args:
                    arguments = decision.modified_args
                    logging.info(f"Using modified arguments: {arguments}")
                    
            except Exception as e:
                error_msg = f"Error during approval process: {str(e)}"
                logging.error(error_msg)
                return {"error": error_msg, "approval_error": True}

        # Special handling for MCP tools
        # Check if tools is an MCP instance with the requested function name
        from ..mcp.mcp import MCP
        if isinstance(self.tools, MCP):
            logging.debug(f"Looking for MCP tool {function_name}")
            
            # Handle SSE MCP client
            if hasattr(self.tools, 'is_sse') and self.tools.is_sse:
                if hasattr(self.tools, 'sse_client'):
                    for tool in self.tools.sse_client.tools:
                        if tool.name == function_name:
                            logging.debug(f"Found matching SSE MCP tool: {function_name}")
                            return tool(**arguments)
            # Handle stdio MCP client
            elif hasattr(self.tools, 'runner'):
                # Check if any of the MCP tools match the function name
                for mcp_tool in self.tools.runner.tools:
                    if hasattr(mcp_tool, 'name') and mcp_tool.name == function_name:
                        logging.debug(f"Found matching MCP tool: {function_name}")
                        return self.tools.runner.call_tool(function_name, arguments)

        # Try to find the function in the agent's tools list first
        func = None
        for tool in self.tools if isinstance(self.tools, (list, tuple)) else []:
            if (callable(tool) and getattr(tool, '__name__', '') == function_name) or \
               (inspect.isclass(tool) and tool.__name__ == function_name):
                func = tool
                break
        
        if func is None:
            # If not found in tools, try globals and main
            func = globals().get(function_name)
            if not func:
                import __main__
                func = getattr(__main__, function_name, None)

        if func:
            try:
                # Langchain: If it's a class with run but not _run, instantiate and call run
                if inspect.isclass(func) and hasattr(func, 'run') and not hasattr(func, '_run'):
                    instance = func()
                    run_params = {k: v for k, v in arguments.items() 
                                  if k in inspect.signature(instance.run).parameters 
                                  and k != 'self'}
                    casted_params = self._cast_arguments(instance.run, run_params)
                    return instance.run(**casted_params)

                # CrewAI: If it's a class with an _run method, instantiate and call _run
                elif inspect.isclass(func) and hasattr(func, '_run'):
                    instance = func()
                    run_params = {k: v for k, v in arguments.items() 
                                  if k in inspect.signature(instance._run).parameters 
                                  and k != 'self'}
                    casted_params = self._cast_arguments(instance._run, run_params)
                    return instance._run(**casted_params)

                # Otherwise treat as regular function
                elif callable(func):
                    casted_arguments = self._cast_arguments(func, arguments)
                    return func(**casted_arguments)
            except Exception as e:
                error_msg = str(e)
                logging.error(f"Error executing tool {function_name}: {error_msg}")
                return {"error": error_msg}
        
        error_msg = f"Tool '{function_name}' is not callable"
        logging.error(error_msg)
        return {"error": error_msg}

    def clear_history(self):
        self.chat_history = []

    def __str__(self):
        return f"Agent(name='{self.name}', role='{self.role}', goal='{self.goal}')"

    def _process_stream_response(self, messages, temperature, start_time, formatted_tools=None, reasoning_steps=False):
        """Process streaming response and return final response"""
        try:
            # Create the response stream
            response_stream = client.chat.completions.create(
                model=self.llm,
                messages=messages,
                temperature=temperature,
                tools=formatted_tools if formatted_tools else None,
                stream=True
            )
            
            full_response_text = ""
            reasoning_content = ""
            chunks = []
            
            # Create Live display with proper configuration
            with Live(
                display_generating("", start_time),
                console=self.console,
                refresh_per_second=4,
                transient=True,
                vertical_overflow="ellipsis",
                auto_refresh=True
            ) as live:
                for chunk in response_stream:
                    chunks.append(chunk)
                    if chunk.choices[0].delta.content:
                        full_response_text += chunk.choices[0].delta.content
                        live.update(display_generating(full_response_text, start_time))
                    
                    # Update live display with reasoning content if enabled
                    if reasoning_steps and hasattr(chunk.choices[0].delta, "reasoning_content"):
                        rc = chunk.choices[0].delta.reasoning_content
                        if rc:
                            reasoning_content += rc
                            live.update(display_generating(f"{full_response_text}\n[Reasoning: {reasoning_content}]", start_time))
            
            # Clear the last generating display with a blank line
            self.console.print()
            final_response = process_stream_chunks(chunks)
            return final_response
            
        except Exception as e:
            display_error(f"Error in stream processing: {e}")
            return None

    def _chat_completion(self, messages, temperature=0.2, tools=None, stream=True, reasoning_steps=False):
        start_time = time.time()
        logging.debug(f"{self.name} sending messages to LLM: {messages}")

        formatted_tools = []
        if tools is None:
            tools = self.tools
        if tools:
            for tool in tools:
                if isinstance(tool, str):
                    # Generate tool definition for string tool names
                    tool_def = self._generate_tool_definition(tool)
                    if tool_def:
                        formatted_tools.append(tool_def)
                    else:
                        logging.warning(f"Could not generate definition for tool: {tool}")
                elif isinstance(tool, dict):
                    formatted_tools.append(tool)
                elif hasattr(tool, "to_openai_tool"):
                    formatted_tools.append(tool.to_openai_tool())
                elif callable(tool):
                    formatted_tools.append(self._generate_tool_definition(tool.__name__))
                else:
                    logging.warning(f"Tool {tool} not recognized")

        try:
            # Use the custom LLM instance if available
            if self._using_custom_llm and hasattr(self, 'llm_instance'):
                if stream:
                    # Debug logs for tool info
                    if formatted_tools:
                        logging.debug(f"Passing {len(formatted_tools)} formatted tools to LLM instance: {formatted_tools}")
                    
                    # Use the LLM instance for streaming responses
                    final_response = self.llm_instance.get_response(
                        prompt=messages[1:],  # Skip system message as LLM handles it separately  
                        system_prompt=messages[0]['content'] if messages and messages[0]['role'] == 'system' else None,
                        temperature=temperature,
                        tools=formatted_tools if formatted_tools else None,
                        verbose=self.verbose,
                        markdown=self.markdown,
                        stream=True,
                        console=self.console,
                        execute_tool_fn=self.execute_tool,
                        agent_name=self.name,
                        agent_role=self.role,
                        reasoning_steps=reasoning_steps
                    )
                else:
                    # Non-streaming with custom LLM
                    final_response = self.llm_instance.get_response(
                        prompt=messages[1:],
                        system_prompt=messages[0]['content'] if messages and messages[0]['role'] == 'system' else None,
                        temperature=temperature,
                        tools=formatted_tools if formatted_tools else None,
                        verbose=self.verbose,
                        markdown=self.markdown,
                        stream=False,
                        console=self.console,
                        execute_tool_fn=self.execute_tool,
                        agent_name=self.name,
                        agent_role=self.role,
                        reasoning_steps=reasoning_steps
                    )
            else:
                # Use the standard OpenAI client approach
                # Continue tool execution loop until no more tool calls are needed
                max_iterations = 10  # Prevent infinite loops
                iteration_count = 0
                
                while iteration_count < max_iterations:
                    if stream:
                        # Process as streaming response with formatted tools
                        final_response = self._process_stream_response(
                            messages, 
                            temperature, 
                            start_time, 
                            formatted_tools=formatted_tools if formatted_tools else None,
                            reasoning_steps=reasoning_steps
                        )
                    else:
                        # Process as regular non-streaming response
                        final_response = client.chat.completions.create(
                            model=self.llm,
                            messages=messages,
                            temperature=temperature,
                            tools=formatted_tools if formatted_tools else None,
                            stream=False
                        )

                    message = safe_get_response_message(final_response)
                    if not message:
                        display_error("Invalid response from chat completion - no message choices")
                        return None
                        
                    tool_calls = getattr(message, 'tool_calls', None)

                    if tool_calls:
                        messages.append({
                            "role": "assistant", 
                            "content": message.content,
                            "tool_calls": tool_calls
                        })

                        for tool_call in tool_calls:
                            function_name = tool_call.function.name
                            arguments = json.loads(tool_call.function.arguments)

                            if self.verbose:
                                display_tool_call(f"Agent {self.name} is calling function '{function_name}' with arguments: {arguments}")

                            tool_result = self.execute_tool(function_name, arguments)
                            results_str = json.dumps(tool_result) if tool_result else "Function returned an empty output"

                            if self.verbose:
                                display_tool_call(f"Function '{function_name}' returned: {results_str}")

                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": results_str
                            })

                        # Check if we should continue (for tools like sequential thinking)
                        should_continue = False
                        for tool_call in tool_calls:
                            function_name = tool_call.function.name
                            arguments = json.loads(tool_call.function.arguments)
                            
                            # For sequential thinking tool, check if nextThoughtNeeded is True
                            if function_name == "sequentialthinking" and arguments.get("nextThoughtNeeded", False):
                                should_continue = True
                                break

                        if not should_continue:
                            # Get final response after tool calls
                            if stream:
                                final_response = self._process_stream_response(
                                    messages, 
                                    temperature, 
                                    start_time,
                                    formatted_tools=formatted_tools if formatted_tools else None,
                                    reasoning_steps=reasoning_steps
                                )
                            else:
                                final_response = client.chat.completions.create(
                                    model=self.llm,
                                    messages=messages,
                                    temperature=temperature,
                                    stream=False
                                )
                            break
                        
                        iteration_count += 1
                    else:
                        # No tool calls, we're done
                        break

            return final_response

        except Exception as e:
            display_error(f"Error in chat completion: {e}")
            return None

    def chat(self, prompt, temperature=0.2, tools=None, output_json=None, output_pydantic=None, reasoning_steps=False, stream=True):
        # Log all parameter values when in debug mode
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            param_info = {
                "prompt": str(prompt)[:100] + "..." if isinstance(prompt, str) and len(str(prompt)) > 100 else str(prompt),
                "temperature": temperature,
                "tools": [t.__name__ if hasattr(t, "__name__") else str(t) for t in tools] if tools else None,
                "output_json": str(output_json.__class__.__name__) if output_json else None,
                "output_pydantic": str(output_pydantic.__class__.__name__) if output_pydantic else None,
                "reasoning_steps": reasoning_steps,
                "agent_name": self.name,
                "agent_role": self.role,
                "agent_goal": self.goal
            }
            logging.debug(f"Agent.chat parameters: {json.dumps(param_info, indent=2, default=str)}")
        
        start_time = time.time()
        reasoning_steps = reasoning_steps or self.reasoning_steps
        # Search for existing knowledge if any knowledge is provided
        if self.knowledge:
            search_results = self.knowledge.search(prompt, agent_id=self.agent_id)
            if search_results:
                # Check if search_results is a list of dictionaries or strings
                if isinstance(search_results, dict) and 'results' in search_results:
                    # Extract memory content from the results
                    knowledge_content = "\n".join([result['memory'] for result in search_results['results']])
                else:
                    # If search_results is a list of strings, join them directly
                    knowledge_content = "\n".join(search_results)
                
                # Append found knowledge to the prompt
                prompt = f"{prompt}\n\nKnowledge: {knowledge_content}"

        if self._using_custom_llm:
            try:
                # Special handling for MCP tools when using provider/model format
                # Fix: Handle empty tools list properly - use self.tools if tools is None or empty
                if tools is None or (isinstance(tools, list) and len(tools) == 0):
                    tool_param = self.tools
                else:
                    tool_param = tools
                
                # Convert MCP tool objects to OpenAI format if needed
                if tool_param is not None:
                    from ..mcp.mcp import MCP
                    if isinstance(tool_param, MCP) and hasattr(tool_param, 'to_openai_tool'):
                        logging.debug("Converting MCP tool to OpenAI format")
                        openai_tool = tool_param.to_openai_tool()
                        if openai_tool:
                            # Handle both single tool and list of tools
                            if isinstance(openai_tool, list):
                                tool_param = openai_tool
                            else:
                                tool_param = [openai_tool]
                            logging.debug(f"Converted MCP tool: {tool_param}")
                
                # Pass everything to LLM class
                response_text = self.llm_instance.get_response(
                    prompt=prompt,
                    system_prompt=f"{self.backstory}\n\nYour Role: {self.role}\n\nYour Goal: {self.goal}" if self.use_system_prompt else None,
                    chat_history=self.chat_history,
                    temperature=temperature,
                    tools=tool_param,
                    output_json=output_json,
                    output_pydantic=output_pydantic,
                    verbose=self.verbose,
                    markdown=self.markdown,
                    self_reflect=self.self_reflect,
                    max_reflect=self.max_reflect,
                    min_reflect=self.min_reflect,
                    console=self.console,
                    agent_name=self.name,
                    agent_role=self.role,
                    agent_tools=[t.__name__ if hasattr(t, '__name__') else str(t) for t in (tools if tools is not None else self.tools)],
                    execute_tool_fn=self.execute_tool,  # Pass tool execution function
                    reasoning_steps=reasoning_steps
                )

                self.chat_history.append({"role": "user", "content": prompt})
                self.chat_history.append({"role": "assistant", "content": response_text})

                # Log completion time if in debug mode
                if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                    total_time = time.time() - start_time
                    logging.debug(f"Agent.chat completed in {total_time:.2f} seconds")

                # Apply guardrail validation for custom LLM response
                try:
                    validated_response = self._apply_guardrail_with_retry(response_text, prompt, temperature, tools)
                    return validated_response
                except Exception as e:
                    logging.error(f"Agent {self.name}: Guardrail validation failed for custom LLM: {e}")
                    return None
            except Exception as e:
                display_error(f"Error in LLM chat: {e}")
                return None
        else:
            if self.use_system_prompt:
                system_prompt = f"""{self.backstory}\n
Your Role: {self.role}\n
Your Goal: {self.goal}
                """
                if output_json:
                    system_prompt += f"\nReturn ONLY a JSON object that matches this Pydantic model: {json.dumps(output_json.model_json_schema())}"
                elif output_pydantic:
                    system_prompt += f"\nReturn ONLY a JSON object that matches this Pydantic model: {json.dumps(output_pydantic.model_json_schema())}"
            else:
                system_prompt = None

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.extend(self.chat_history)

            # Modify prompt if output_json or output_pydantic is specified
            original_prompt = prompt
            if output_json or output_pydantic:
                if isinstance(prompt, str):
                    prompt += "\nReturn ONLY a valid JSON object. No other text or explanation."
                elif isinstance(prompt, list):
                    # For multimodal prompts, append to the text content
                    for item in prompt:
                        if item["type"] == "text":
                            item["text"] += "\nReturn ONLY a valid JSON object. No other text or explanation."
                            break

            if isinstance(prompt, list):
                # If we receive a multimodal prompt list, place it directly in the user message
                messages.append({"role": "user", "content": prompt})
            else:
                messages.append({"role": "user", "content": prompt})

            final_response_text = None
            reflection_count = 0
            start_time = time.time()

            while True:
                try:
                    if self.verbose:
                        # Handle both string and list prompts for instruction display
                        display_text = prompt
                        if isinstance(prompt, list):
                            # Extract text content from multimodal prompt
                            display_text = next((item["text"] for item in prompt if item["type"] == "text"), "")
                        
                        if display_text and str(display_text).strip():
                            # Pass agent information to display_instruction
                            agent_tools = [t.__name__ if hasattr(t, '__name__') else str(t) for t in self.tools]
                            display_instruction(
                                f"Agent {self.name} is processing prompt: {display_text}", 
                                console=self.console,
                                agent_name=self.name,
                                agent_role=self.role,
                                agent_tools=agent_tools
                            )

                    response = self._chat_completion(messages, temperature=temperature, tools=tools if tools else None, reasoning_steps=reasoning_steps, stream=stream)
                    if not response:
                        return None

                    response_text = response.choices[0].message.content.strip()

                    # Handle output_json or output_pydantic if specified
                    if output_json or output_pydantic:
                        # Add to chat history and return raw response
                        self.chat_history.append({"role": "user", "content": original_prompt})
                        self.chat_history.append({"role": "assistant", "content": response_text})
                        if self.verbose:
                            display_interaction(original_prompt, response_text, markdown=self.markdown, 
                                             generation_time=time.time() - start_time, console=self.console)
                        return response_text

                    if not self.self_reflect:
                        self.chat_history.append({"role": "user", "content": original_prompt})
                        self.chat_history.append({"role": "assistant", "content": response_text})
                        if self.verbose:
                            logging.debug(f"Agent {self.name} final response: {response_text}")
                        display_interaction(original_prompt, response_text, markdown=self.markdown, generation_time=time.time() - start_time, console=self.console)
                        # Return only reasoning content if reasoning_steps is True
                        if reasoning_steps and hasattr(response.choices[0].message, 'reasoning_content'):
                            # Apply guardrail to reasoning content
                            try:
                                validated_reasoning = self._apply_guardrail_with_retry(response.choices[0].message.reasoning_content, original_prompt, temperature, tools)
                                return validated_reasoning
                            except Exception as e:
                                logging.error(f"Agent {self.name}: Guardrail validation failed for reasoning content: {e}")
                                return None
                        # Apply guardrail to regular response
                        try:
                            validated_response = self._apply_guardrail_with_retry(response_text, original_prompt, temperature, tools)
                            return validated_response
                        except Exception as e:
                            logging.error(f"Agent {self.name}: Guardrail validation failed: {e}")
                            return None

                    reflection_prompt = f"""
Reflect on your previous response: '{response_text}'.
{self.reflect_prompt if self.reflect_prompt else "Identify any flaws, improvements, or actions."}
Provide a "satisfactory" status ('yes' or 'no').
Output MUST be JSON with 'reflection' and 'satisfactory'.
                    """
                    logging.debug(f"{self.name} reflection attempt {reflection_count+1}, sending prompt: {reflection_prompt}")
                    messages.append({"role": "user", "content": reflection_prompt})

                    try:
                        reflection_response = client.beta.chat.completions.parse(
                            model=self.reflect_llm if self.reflect_llm else self.llm,
                            messages=messages,
                            temperature=temperature,
                            response_format=ReflectionOutput
                        )

                        reflection_output = reflection_response.choices[0].message.parsed

                        if self.verbose:
                            display_self_reflection(f"Agent {self.name} self reflection (using {self.reflect_llm if self.reflect_llm else self.llm}): reflection='{reflection_output.reflection}' satisfactory='{reflection_output.satisfactory}'", console=self.console)

                        messages.append({"role": "assistant", "content": f"Self Reflection: {reflection_output.reflection} Satisfactory?: {reflection_output.satisfactory}"})

                        # Only consider satisfactory after minimum reflections
                        if reflection_output.satisfactory == "yes" and reflection_count >= self.min_reflect - 1:
                            if self.verbose:
                                display_self_reflection("Agent marked the response as satisfactory after meeting minimum reflections", console=self.console)
                            self.chat_history.append({"role": "user", "content": prompt})
                            self.chat_history.append({"role": "assistant", "content": response_text})
                            display_interaction(prompt, response_text, markdown=self.markdown, generation_time=time.time() - start_time, console=self.console)
                            # Apply guardrail validation after satisfactory reflection
                            try:
                                validated_response = self._apply_guardrail_with_retry(response_text, prompt, temperature, tools)
                                return validated_response
                            except Exception as e:
                                logging.error(f"Agent {self.name}: Guardrail validation failed after reflection: {e}")
                                return None

                        # Check if we've hit max reflections
                        if reflection_count >= self.max_reflect - 1:
                            if self.verbose:
                                display_self_reflection("Maximum reflection count reached, returning current response", console=self.console)
                            self.chat_history.append({"role": "user", "content": prompt})
                            self.chat_history.append({"role": "assistant", "content": response_text})
                            display_interaction(prompt, response_text, markdown=self.markdown, generation_time=time.time() - start_time, console=self.console)
                            # Apply guardrail validation after max reflections
                            try:
                                validated_response = self._apply_guardrail_with_retry(response_text, prompt, temperature, tools)
                                return validated_response
                            except Exception as e:
                                logging.error(f"Agent {self.name}: Guardrail validation failed after max reflections: {e}")
                                return None

                        logging.debug(f"{self.name} reflection count {reflection_count + 1}, continuing reflection process")
                        messages.append({"role": "user", "content": "Now regenerate your response using the reflection you made"})
                        response = self._chat_completion(messages, temperature=temperature, tools=None, stream=stream)
                        response_text = response.choices[0].message.content.strip()
                        reflection_count += 1
                        continue  # Continue the loop for more reflections

                    except Exception as e:
                        display_error(f"Error in parsing self-reflection json {e}. Retrying", console=self.console)
                        logging.error("Reflection parsing failed.", exc_info=True)
                        messages.append({"role": "assistant", "content": f"Self Reflection failed."})
                        reflection_count += 1
                        continue  # Continue even after error to try again
                    
                except Exception as e:
                    display_error(f"Error in chat: {e}", console=self.console)
                    return None 

        # Log completion time if in debug mode
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            total_time = time.time() - start_time
            logging.debug(f"Agent.chat completed in {total_time:.2f} seconds")
        
        # Apply guardrail validation before returning    
        try:
            validated_response = self._apply_guardrail_with_retry(response_text, prompt, temperature, tools)
            return validated_response
        except Exception as e:
            logging.error(f"Agent {self.name}: Guardrail validation failed: {e}")
            if self.verbose:
                display_error(f"Guardrail validation failed: {e}", console=self.console)
            return None

    def clean_json_output(self, output: str) -> str:
        """Clean and extract JSON from response text."""
        cleaned = output.strip()
        # Remove markdown code blocks if present
        if cleaned.startswith("```json"):
            cleaned = cleaned[len("```json"):].strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[len("```"):].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        return cleaned  

    async def achat(self, prompt: str, temperature=0.2, tools=None, output_json=None, output_pydantic=None, reasoning_steps=False):
        """Async version of chat method with self-reflection support.""" 
        # Log all parameter values when in debug mode
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            param_info = {
                "prompt": str(prompt)[:100] + "..." if isinstance(prompt, str) and len(str(prompt)) > 100 else str(prompt),
                "temperature": temperature,
                "tools": [t.__name__ if hasattr(t, "__name__") else str(t) for t in tools] if tools else None,
                "output_json": str(output_json.__class__.__name__) if output_json else None,
                "output_pydantic": str(output_pydantic.__class__.__name__) if output_pydantic else None,
                "reasoning_steps": reasoning_steps,
                "agent_name": self.name,
                "agent_role": self.role,
                "agent_goal": self.goal
            }
            logging.debug(f"Agent.achat parameters: {json.dumps(param_info, indent=2, default=str)}")
        
        start_time = time.time()
        reasoning_steps = reasoning_steps or self.reasoning_steps
        try:
            # Default to self.tools if tools argument is None
            if tools is None:
                tools = self.tools

            # Search for existing knowledge if any knowledge is provided
            if self.knowledge:
                search_results = self.knowledge.search(prompt, agent_id=self.agent_id)
                if search_results:
                    if isinstance(search_results, dict) and 'results' in search_results:
                        knowledge_content = "\n".join([result['memory'] for result in search_results['results']])
                    else:
                        knowledge_content = "\n".join(search_results)
                    prompt = f"{prompt}\n\nKnowledge: {knowledge_content}"

            if self._using_custom_llm:
                try:
                    response_text = await self.llm_instance.get_response_async(
                        prompt=prompt,
                        system_prompt=f"{self.backstory}\n\nYour Role: {self.role}\n\nYour Goal: {self.goal}" if self.use_system_prompt else None,
                        chat_history=self.chat_history,
                        temperature=temperature,
                        tools=tools,
                        output_json=output_json,
                        output_pydantic=output_pydantic,
                        verbose=self.verbose,
                        markdown=self.markdown,
                        self_reflect=self.self_reflect,
                        max_reflect=self.max_reflect,
                        min_reflect=self.min_reflect,
                        console=self.console,
                        agent_name=self.name,
                        agent_role=self.role,
                        agent_tools=[t.__name__ if hasattr(t, '__name__') else str(t) for t in self.tools],
                        execute_tool_fn=self.execute_tool_async,
                        reasoning_steps=reasoning_steps
                    )

                    self.chat_history.append({"role": "user", "content": prompt})
                    self.chat_history.append({"role": "assistant", "content": response_text})

                    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                        total_time = time.time() - start_time
                        logging.debug(f"Agent.achat completed in {total_time:.2f} seconds")
                    return response_text
                except Exception as e:
                    display_error(f"Error in LLM chat: {e}")
                    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                        total_time = time.time() - start_time
                        logging.debug(f"Agent.achat failed in {total_time:.2f} seconds: {str(e)}")
                    return None

            # For OpenAI client
            if self.use_system_prompt:
                system_prompt = f"""{self.backstory}\n
Your Role: {self.role}\n
Your Goal: {self.goal}
                """
                if output_json:
                    system_prompt += f"\nReturn ONLY a JSON object that matches this Pydantic model: {json.dumps(output_json.model_json_schema())}"
                elif output_pydantic:
                    system_prompt += f"\nReturn ONLY a JSON object that matches this Pydantic model: {json.dumps(output_pydantic.model_json_schema())}"
            else:
                system_prompt = None

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.extend(self.chat_history)

            # Modify prompt if output_json or output_pydantic is specified
            original_prompt = prompt
            if output_json or output_pydantic:
                if isinstance(prompt, str):
                    prompt += "\nReturn ONLY a valid JSON object. No other text or explanation."
                elif isinstance(prompt, list):
                    for item in prompt:
                        if item["type"] == "text":
                            item["text"] += "\nReturn ONLY a valid JSON object. No other text or explanation."
                            break

            if isinstance(prompt, list):
                messages.append({"role": "user", "content": prompt})
            else:
                messages.append({"role": "user", "content": prompt})

            reflection_count = 0
            start_time = time.time()

            while True:
                try:
                    if self.verbose:
                        display_text = prompt
                        if isinstance(prompt, list):
                            display_text = next((item["text"] for item in prompt if item["type"] == "text"), "")
                        
                        if display_text and str(display_text).strip():
                            agent_tools = [t.__name__ if hasattr(t, '__name__') else str(t) for t in self.tools]
                            await adisplay_instruction(
                                f"Agent {self.name} is processing prompt: {display_text}",
                                console=self.console,
                                agent_name=self.name,
                                agent_role=self.role,
                                agent_tools=agent_tools
                            )

                    # Format tools if provided
                    formatted_tools = []
                    if tools:
                        for tool in tools:
                            if isinstance(tool, str):
                                tool_def = self._generate_tool_definition(tool)
                                if tool_def:
                                    formatted_tools.append(tool_def)
                            elif isinstance(tool, dict):
                                formatted_tools.append(tool)
                            elif hasattr(tool, "to_openai_tool"):
                                formatted_tools.append(tool.to_openai_tool())
                            elif callable(tool):
                                formatted_tools.append(self._generate_tool_definition(tool.__name__))

                    # Create async OpenAI client
                    async_client = AsyncOpenAI()

                    # Make the API call based on the type of request
                    if tools:
                        response = await async_client.chat.completions.create(
                            model=self.llm,
                            messages=messages,
                            temperature=temperature,
                            tools=formatted_tools,
                        )
                        result = await self._achat_completion(response, tools)
                        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                            total_time = time.time() - start_time
                            logging.debug(f"Agent.achat completed in {total_time:.2f} seconds")
                        return result
                    elif output_json or output_pydantic:
                        response = await async_client.chat.completions.create(
                            model=self.llm,
                            messages=messages,
                            temperature=temperature,
                            response_format={"type": "json_object"}
                        )
                        # Return the raw response
                        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                            total_time = time.time() - start_time
                            logging.debug(f"Agent.achat completed in {total_time:.2f} seconds")
                        content = safe_get_response_content(response)
                        if content is None:
                            display_error("Invalid response from chat completion - no message choices")
                            return None
                        return content
                    else:
                        response = await async_client.chat.completions.create(
                            model=self.llm,
                            messages=messages,
                            temperature=temperature
                        )
                        
                        response_text = safe_get_response_content(response)
                        if response_text is None:
                            display_error("Invalid response from chat completion - no message choices")
                            return None
                        
                        # Handle self-reflection if enabled
                        if self.self_reflect:
                            reflection_count = 0
                            
                            while True:
                                reflection_prompt = f"""
Reflect on your previous response: '{response_text}'.
{self.reflect_prompt if self.reflect_prompt else "Identify any flaws, improvements, or actions."}
Provide a "satisfactory" status ('yes' or 'no').
Output MUST be JSON with 'reflection' and 'satisfactory'.
                                """
                                
                                # Add reflection prompt to messages
                                reflection_messages = messages + [
                                    {"role": "assistant", "content": response_text},
                                    {"role": "user", "content": reflection_prompt}
                                ]
                                
                                try:
                                    reflection_response = await async_client.beta.chat.completions.parse(
                                        model=self.reflect_llm if self.reflect_llm else self.llm,
                                        messages=reflection_messages,
                                        temperature=temperature,
                                        response_format=ReflectionOutput
                                    )
                                    
                                    reflection_output = reflection_response.choices[0].message.parsed
                                    
                                    if self.verbose:
                                        display_self_reflection(f"Agent {self.name} self reflection (using {self.reflect_llm if self.reflect_llm else self.llm}): reflection='{reflection_output.reflection}' satisfactory='{reflection_output.satisfactory}'", console=self.console)
                                    
                                    # Only consider satisfactory after minimum reflections
                                    if reflection_output.satisfactory == "yes" and reflection_count >= self.min_reflect - 1:
                                        if self.verbose:
                                            display_self_reflection("Agent marked the response as satisfactory after meeting minimum reflections", console=self.console)
                                        break
                                    
                                    # Check if we've hit max reflections
                                    if reflection_count >= self.max_reflect - 1:
                                        if self.verbose:
                                            display_self_reflection("Maximum reflection count reached, returning current response", console=self.console)
                                        break
                                    
                                    # Regenerate response based on reflection
                                    regenerate_messages = reflection_messages + [
                                        {"role": "assistant", "content": f"Self Reflection: {reflection_output.reflection} Satisfactory?: {reflection_output.satisfactory}"},
                                        {"role": "user", "content": "Now regenerate your response using the reflection you made"}
                                    ]
                                    
                                    new_response = await async_client.chat.completions.create(
                                        model=self.llm,
                                        messages=regenerate_messages,
                                        temperature=temperature
                                    )
                                    response_text = safe_get_response_content(new_response)
                                    if response_text is None:
                                        display_error("Invalid response from chat completion - no message choices")
                                        break
                                    reflection_count += 1
                                    
                                except Exception as e:
                                    if self.verbose:
                                        display_error(f"Error in parsing self-reflection json {e}. Retrying", console=self.console)
                                    logging.error("Reflection parsing failed.", exc_info=True)
                                    reflection_count += 1
                                    if reflection_count >= self.max_reflect:
                                        break
                                    continue
                        
                        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                            total_time = time.time() - start_time
                            logging.debug(f"Agent.achat completed in {total_time:.2f} seconds")
                        return response_text
                except Exception as e:
                    display_error(f"Error in chat completion: {e}")
                    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                        total_time = time.time() - start_time
                        logging.debug(f"Agent.achat failed in {total_time:.2f} seconds: {str(e)}")
                    return None
        except Exception as e:
            display_error(f"Error in achat: {e}")
            if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                total_time = time.time() - start_time
                logging.debug(f"Agent.achat failed in {total_time:.2f} seconds: {str(e)}")
            return None

    async def _achat_completion(self, response, tools, reasoning_steps=False):
        """Async version of _chat_completion method"""
        try:
            message = safe_get_response_message(response)
            if not message:
                display_error("Invalid response from chat completion - no message choices")
                return None
            if not hasattr(message, 'tool_calls') or not message.tool_calls:
                return message.content

            results = []
            for tool_call in message.tool_calls:
                try:
                    function_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)
                    
                    # Find the matching tool
                    tool = next((t for t in tools if t.__name__ == function_name), None)
                    if not tool:
                        display_error(f"Tool {function_name} not found")
                        continue
                    
                    # Check if the tool is async
                    if asyncio.iscoroutinefunction(tool):
                        result = await tool(**arguments)
                    else:
                        # Run sync function in executor to avoid blocking
                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(None, lambda: tool(**arguments))
                    
                    results.append(result)
                except Exception as e:
                    display_error(f"Error executing tool {function_name}: {e}")
                    results.append(None)

            # If we have results, format them into a response
            if results:
                formatted_results = "\n".join([str(r) for r in results if r is not None])
                if formatted_results:
                    messages = [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "assistant", "content": "Here are the tool results:"},
                        {"role": "user", "content": formatted_results + "\nPlease process these results and provide a final response."}
                    ]
                    try:
                        async_client = AsyncOpenAI()
                        final_response = await async_client.chat.completions.create(
                            model=self.llm,
                            messages=messages,
                            temperature=0.2,
                            stream=True
                        )
                        full_response_text = ""
                        reasoning_content = ""
                        chunks = []
                        start_time = time.time()
                        
                        with Live(
                            display_generating("", start_time),
                            console=self.console,
                            refresh_per_second=4,
                            transient=True,
                            vertical_overflow="ellipsis",
                            auto_refresh=True
                        ) as live:
                            async for chunk in final_response:
                                chunks.append(chunk)
                                if chunk.choices[0].delta.content:
                                    full_response_text += chunk.choices[0].delta.content
                                    live.update(display_generating(full_response_text, start_time))
                                
                                if reasoning_steps and hasattr(chunk.choices[0].delta, "reasoning_content"):
                                    rc = chunk.choices[0].delta.reasoning_content
                                    if rc:
                                        reasoning_content += rc
                                        live.update(display_generating(f"{full_response_text}\n[Reasoning: {reasoning_content}]", start_time))
                        
                        self.console.print()
                        
                        final_response = process_stream_chunks(chunks)
                        # Return only reasoning content if reasoning_steps is True
                        if reasoning_steps:
                            message = safe_get_response_message(final_response)
                            if message and hasattr(message, 'reasoning_content'):
                                return message.reasoning_content
                        content = safe_get_response_content(final_response)
                        return content if content is not None else full_response_text

                    except Exception as e:
                        display_error(f"Error in final chat completion: {e}")
                        return formatted_results
                return formatted_results
            return None
        except Exception as e:
            display_error(f"Error in _achat_completion: {e}")
            return None

    async def astart(self, prompt: str, **kwargs):
        """Async version of start method"""
        return await self.achat(prompt, **kwargs)

    def run(self):
        """Alias for start() method"""
        return self.start() 

    def start(self, prompt: str, **kwargs):
        """Start the agent with a prompt. This is a convenience method that wraps chat()."""
        return self.chat(prompt, **kwargs) 

    async def execute_tool_async(self, function_name: str, arguments: Dict[str, Any]) -> Any:
        """Async version of execute_tool"""
        try:
            logging.info(f"Executing async tool: {function_name} with arguments: {arguments}")
            
            # Check if approval is required for this tool
            from ..approval import is_approval_required, request_approval
            if is_approval_required(function_name):
                decision = await request_approval(function_name, arguments)
                if not decision.approved:
                    error_msg = f"Tool execution denied: {decision.reason}"
                    logging.warning(error_msg)
                    return {"error": error_msg, "approval_denied": True}
                
                # Use modified arguments if provided
                if decision.modified_args:
                    arguments = decision.modified_args
                    logging.info(f"Using modified arguments: {arguments}")
            
            # Try to find the function in the agent's tools list first
            func = None
            for tool in self.tools:
                if (callable(tool) and getattr(tool, '__name__', '') == function_name):
                    func = tool
                    break
            
            if func is None:
                logging.error(f"Function {function_name} not found in tools")
                return {"error": f"Function {function_name} not found in tools"}

            try:
                if inspect.iscoroutinefunction(func):
                    logging.debug(f"Executing async function: {function_name}")
                    result = await func(**arguments)
                else:
                    logging.debug(f"Executing sync function in executor: {function_name}")
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, lambda: func(**arguments))
                
                # Ensure result is JSON serializable
                logging.debug(f"Raw result from tool: {result}")
                if result is None:
                    return {"result": None}
                try:
                    json.dumps(result)  # Test serialization
                    return result
                except TypeError:
                    logging.warning(f"Result not JSON serializable, converting to string: {result}")
                    return {"result": str(result)}

            except Exception as e:
                logging.error(f"Error executing {function_name}: {str(e)}", exc_info=True)
                return {"error": f"Error executing {function_name}: {str(e)}"}

        except Exception as e:
            logging.error(f"Error in execute_tool_async: {str(e)}", exc_info=True)
            return {"error": f"Error in execute_tool_async: {str(e)}"}

    def launch(self, path: str = '/', port: int = 8000, host: str = '0.0.0.0', debug: bool = False, protocol: str = "http"):
        """
        Launch the agent as an HTTP API endpoint or an MCP server.
        
        Args:
            path: API endpoint path (default: '/') for HTTP, or base path for MCP.
            port: Server port (default: 8000)
            host: Server host (default: '0.0.0.0')
            debug: Enable debug mode for uvicorn (default: False)
            protocol: "http" to launch as FastAPI, "mcp" to launch as MCP server.
            
        Returns:
            None
        """
        if protocol == "http":
            global _server_started, _registered_agents, _shared_apps
            
            # Try to import FastAPI dependencies - lazy loading
            try:
                import uvicorn
                from fastapi import FastAPI, HTTPException, Request
                from fastapi.responses import JSONResponse
                from pydantic import BaseModel
                import threading
                import time
                import asyncio
                
                # Define the request model here since we need pydantic
                class AgentQuery(BaseModel):
                    query: str
                    
            except ImportError as e:
                # Check which specific module is missing
                missing_module = str(e).split("No module named '")[-1].rstrip("'")
                display_error(f"Missing dependency: {missing_module}. Required for launch() method with HTTP mode.")
                logging.error(f"Missing dependency: {missing_module}. Required for launch() method with HTTP mode.")
                print(f"\nTo add API capabilities, install the required dependencies:")
                print(f"pip install {missing_module}")
                print("\nOr install all API dependencies with:")
                print("pip install 'praisonaiagents[api]'")
                return None
                
            # Initialize port-specific collections if needed
            if port not in _registered_agents:
                _registered_agents[port] = {}
                
            # Initialize shared FastAPI app if not already created for this port
            if _shared_apps.get(port) is None:
                _shared_apps[port] = FastAPI(
                    title=f"PraisonAI Agents API (Port {port})",
                    description="API for interacting with PraisonAI Agents"
                )
                
                # Add a root endpoint with a welcome message
                @_shared_apps[port].get("/")
                async def root():
                    return {
                        "message": f"Welcome to PraisonAI Agents API on port {port}. See /docs for usage.",
                        "endpoints": list(_registered_agents[port].keys())
                    }
                
                # Add healthcheck endpoint
                @_shared_apps[port].get("/health")
                async def healthcheck():
                    return {
                        "status": "ok", 
                        "endpoints": list(_registered_agents[port].keys())
                    }
            
            # Normalize path to ensure it starts with /
            if not path.startswith('/'):
                path = f'/{path}'
                
            # Check if path is already registered for this port
            if path in _registered_agents[port]:
                logging.warning(f"Path '{path}' is already registered on port {port}. Please use a different path.")
                print(f"⚠️ Warning: Path '{path}' is already registered on port {port}.")
                # Use a modified path to avoid conflicts
                original_path = path
                path = f"{path}_{self.agent_id[:6]}"
                logging.warning(f"Using '{path}' instead of '{original_path}'")
                print(f"🔄 Using '{path}' instead")
            
            # Register the agent to this path
            _registered_agents[port][path] = self.agent_id
            
            # Define the endpoint handler
            @_shared_apps[port].post(path)
            async def handle_agent_query(request: Request, query_data: Optional[AgentQuery] = None):
                # Handle both direct JSON with query field and form data
                if query_data is None:
                    try:
                        request_data = await request.json()
                        if "query" not in request_data:
                            raise HTTPException(status_code=400, detail="Missing 'query' field in request")
                        query = request_data["query"]
                    except:
                        # Fallback to form data or query params
                        form_data = await request.form()
                        if "query" in form_data:
                            query = form_data["query"]
                        else:
                            raise HTTPException(status_code=400, detail="Missing 'query' field in request")
                else:
                    query = query_data.query
                    
                try:
                    # Use async version if available, otherwise use sync version
                    if asyncio.iscoroutinefunction(self.chat):
                        response = await self.achat(query)
                    else:
                        # Run sync function in a thread to avoid blocking
                        loop = asyncio.get_event_loop()
                        response = await loop.run_in_executor(None, lambda p=query: self.chat(p))
                    
                    return {"response": response}
                except Exception as e:
                    logging.error(f"Error processing query: {str(e)}", exc_info=True)
                    return JSONResponse(
                        status_code=500,
                        content={"error": f"Error processing query: {str(e)}"}
                    )
            
            print(f"🚀 Agent '{self.name}' available at http://{host}:{port}")
            
            # Start the server if it's not already running for this port
            if not _server_started.get(port, False):
                # Mark the server as started first to prevent duplicate starts
                _server_started[port] = True
                
                # Start the server in a separate thread
                def run_server():
                    try:
                        print(f"✅ FastAPI server started at http://{host}:{port}")
                        print(f"📚 API documentation available at http://{host}:{port}/docs")
                        print(f"🔌 Available endpoints: {', '.join(list(_registered_agents[port].keys()))}")
                        uvicorn.run(_shared_apps[port], host=host, port=port, log_level="debug" if debug else "info")
                    except Exception as e:
                        logging.error(f"Error starting server: {str(e)}", exc_info=True)
                        print(f"❌ Error starting server: {str(e)}")
                
                # Run server in a background thread
                server_thread = threading.Thread(target=run_server, daemon=True)
                server_thread.start()
                
                # Wait for a moment to allow the server to start and register endpoints
                time.sleep(0.5)
            else:
                # If server is already running, wait a moment to make sure the endpoint is registered
                time.sleep(0.1)
                print(f"🔌 Available endpoints on port {port}: {', '.join(list(_registered_agents[port].keys()))}")
            
            # Get the stack frame to check if this is the last launch() call in the script
            import inspect
            stack = inspect.stack()
            
            # If this is called from a Python script (not interactive), try to detect if it's the last launch call
            if len(stack) > 1 and stack[1].filename.endswith('.py'):
                caller_frame = stack[1]
                caller_line = caller_frame.lineno
                
                try:
                    # Read the file to check if there are more launch calls after this one
                    with open(caller_frame.filename, 'r') as f:
                        lines = f.readlines()
                    
                    # Check if there are more launch() calls after the current line
                    has_more_launches = False
                    for line_content in lines[caller_line:]: # renamed line to line_content
                        if '.launch(' in line_content and not line_content.strip().startswith('#'):
                            has_more_launches = True
                            break
                    
                    # If this is the last launch call, block the main thread
                    if not has_more_launches:
                        try:
                            print("\nAll agents registered for HTTP mode. Press Ctrl+C to stop the servers.")
                            while True:
                                time.sleep(1)
                        except KeyboardInterrupt:
                            print("\nServers stopped")
                except Exception as e:
                    # If something goes wrong with detection, block anyway to be safe
                    logging.error(f"Error in launch detection: {e}")
                    try:
                        print("\nKeeping HTTP servers alive. Press Ctrl+C to stop.")
                        while True:
                            time.sleep(1)
                    except KeyboardInterrupt:
                        print("\nServers stopped")
            return None
            
        elif protocol == "mcp":
            try:
                import uvicorn
                from mcp.server.fastmcp import FastMCP
                from mcp.server.sse import SseServerTransport
                from starlette.applications import Starlette
                from starlette.requests import Request
                from starlette.routing import Mount, Route
                from mcp.server import Server as MCPServer # Alias to avoid conflict
                import threading
                import time
                import inspect
                import asyncio  # Import asyncio in the MCP scope
                # logging is already imported at the module level
                
            except ImportError as e:
                missing_module = str(e).split("No module named '")[-1].rstrip("'")
                display_error(f"Missing dependency: {missing_module}. Required for launch() method with MCP mode.")
                logging.error(f"Missing dependency: {missing_module}. Required for launch() method with MCP mode.")
                print(f"\nTo add MCP capabilities, install the required dependencies:")
                print(f"pip install {missing_module} mcp praison-mcp starlette uvicorn") # Added mcp, praison-mcp, starlette, uvicorn
                print("\nOr install all MCP dependencies with relevant packages.")
                return None

            mcp_server_instance_name = f"{self.name}_mcp_server" if self.name else "agent_mcp_server"
            mcp = FastMCP(mcp_server_instance_name)

            # Determine the MCP tool name based on self.name
            actual_mcp_tool_name = f"execute_{self.name.lower().replace(' ', '_').replace('-', '_')}_task" if self.name \
                else "execute_task"

            @mcp.tool(name=actual_mcp_tool_name)
            async def execute_agent_task(prompt: str) -> str:
                """Executes the agent's primary task with the given prompt."""
                logging.info(f"MCP tool '{actual_mcp_tool_name}' called with prompt: {prompt}")
                try:
                    # Ensure self.achat is used as it's the async version and pass its tools
                    if hasattr(self, 'achat') and asyncio.iscoroutinefunction(self.achat):
                        response = await self.achat(prompt, tools=self.tools)
                    elif hasattr(self, 'chat'): # Fallback for synchronous chat
                        loop = asyncio.get_event_loop()
                        response = await loop.run_in_executor(None, lambda p=prompt: self.chat(p, tools=self.tools))
                    else:
                        logging.error(f"Agent {self.name} has no suitable chat or achat method for MCP tool.")
                        return f"Error: Agent {self.name} misconfigured for MCP."
                    return response if response is not None else "Agent returned no response."
                except Exception as e:
                    logging.error(f"Error in MCP tool '{actual_mcp_tool_name}': {e}", exc_info=True)
                    return f"Error executing task: {str(e)}"

            # Normalize base_path for MCP routes
            base_path = path.rstrip('/')
            sse_path = f"{base_path}/sse"
            messages_path_prefix = f"{base_path}/messages" # Prefix for message posting
            
            # Ensure messages_path ends with a slash for Mount
            if not messages_path_prefix.endswith('/'):
                messages_path_prefix += '/'


            sse_transport = SseServerTransport(messages_path_prefix) # Pass the full prefix

            async def handle_sse_connection(request: Request) -> None:
                logging.debug(f"SSE connection request received from {request.client} for path {request.url.path}")
                async with sse_transport.connect_sse(
                        request.scope,
                        request.receive,
                        request._send,  # noqa: SLF001
                ) as (read_stream, write_stream):
                    await mcp._mcp_server.run( # Use the underlying server from FastMCP
                        read_stream,
                        write_stream,
                        mcp._mcp_server.create_initialization_options(),
                    )
            
            starlette_app = Starlette(
                debug=debug,
                routes=[
                    Route(sse_path, endpoint=handle_sse_connection),
                    Mount(messages_path_prefix, app=sse_transport.handle_post_message),
                ],
            )

            print(f"🚀 Agent '{self.name}' MCP server starting on http://{host}:{port}")
            print(f"📡 MCP SSE endpoint available at {sse_path}")
            print(f"📢 MCP messages post to {messages_path_prefix}")
            # Instead of trying to extract tool names, hardcode the known tool name
            tool_names = [actual_mcp_tool_name]  # Use the determined dynamic tool name
            print(f"🛠️ Available MCP tools: {', '.join(tool_names)}")

            # Uvicorn server running logic (similar to HTTP mode but standalone for MCP)
            def run_mcp_server():
                try:
                    uvicorn.run(starlette_app, host=host, port=port, log_level="debug" if debug else "info")
                except Exception as e:
                    logging.error(f"Error starting MCP server: {str(e)}", exc_info=True)
                    print(f"❌ Error starting MCP server: {str(e)}")

            server_thread = threading.Thread(target=run_mcp_server, daemon=True)
            server_thread.start()
            time.sleep(0.5) # Allow server to start

            # Blocking logic for MCP mode
            import inspect # Already imported but good for clarity
            stack = inspect.stack()
            if len(stack) > 1 and stack[1].filename.endswith('.py'):
                caller_frame = stack[1]
                caller_line = caller_frame.lineno
                try:
                    with open(caller_frame.filename, 'r') as f:
                        lines = f.readlines()
                    has_more_launches = False
                    for line_content in lines[caller_line:]: # renamed line to line_content
                        if '.launch(' in line_content and not line_content.strip().startswith('#'):
                            has_more_launches = True
                            break
                    if not has_more_launches:
                        try:
                            print("\nAgent MCP server running. Press Ctrl+C to stop.")
                            while True:
                                time.sleep(1)
                        except KeyboardInterrupt:
                            print("\nMCP Server stopped")
                except Exception as e:
                    logging.error(f"Error in MCP launch detection: {e}")
                    try:
                        print("\nKeeping MCP server alive. Press Ctrl+C to stop.")
                        while True:
                            time.sleep(1)
                    except KeyboardInterrupt:
                        print("\nMCP Server stopped")
            return None
        else:
            display_error(f"Invalid protocol: {protocol}. Choose 'http' or 'mcp'.")
            return None 