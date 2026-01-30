import os
import time
import json
import logging
from typing import Any, Dict, Optional, List
from rich.console import Console
from ..main import display_error, TaskOutput
from ..agent.agent import Agent
from ..task.task import Task
from ..process.process import Process
import asyncio
import uuid
from enum import Enum

# Import token tracking
try:
    from ..telemetry.token_collector import _token_collector
except ImportError:
    _token_collector = None

# Task status constants
class TaskStatus(Enum):
    """Enumeration for task status values to ensure consistency"""
    COMPLETED = "completed"
    IN_PROGRESS = "in progress"
    NOT_STARTED = "not started"
    FAILED = "failed"
    UNKNOWN = "unknown"

# Set up logger
logger = logging.getLogger(__name__)

# Global variables for managing the shared servers
_agents_server_started = {}  # Dict of port -> started boolean
_agents_registered_endpoints = {}  # Dict of port -> Dict of path -> endpoint_id
_agents_shared_apps = {}  # Dict of port -> FastAPI app

def encode_file_to_base64(file_path: str) -> str:
    """Base64-encode a file."""
    import base64
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def process_video(video_path: str, seconds_per_frame=2):
    """Split video into frames (base64-encoded)."""
    import cv2
    import base64
    base64_frames = []
    video = cv2.VideoCapture(video_path)
    total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = video.get(cv2.CAP_PROP_FPS)
    frames_to_skip = int(fps * seconds_per_frame)
    curr_frame = 0
    while curr_frame < total_frames:
        video.set(cv2.CAP_PROP_POS_FRAMES, curr_frame)
        success, frame = video.read()
        if not success:
            break
        _, buffer = cv2.imencode(".jpg", frame)
        base64_frames.append(base64.b64encode(buffer).decode("utf-8"))
        curr_frame += frames_to_skip
    video.release()
    return base64_frames


def get_multimodal_message(text_prompt: str, images: list) -> list:
    """
    Build multimodal message content for LLM with text and images.
    
    DRY helper - replaces duplicate _get_multimodal_message in aexecute_task/execute_task.
    
    Args:
        text_prompt: The text content of the message
        images: List of image paths (local or URL)
        
    Returns:
        List of content items for multimodal LLM message
    """
    content = [{"type": "text", "text": text_prompt}]
    
    for img in images:
        # If local file path for a valid image
        if os.path.exists(img):
            ext = os.path.splitext(img)[1].lower()
            # If it's a .mp4, convert to frames
            if ext == ".mp4":
                frames = process_video(img, seconds_per_frame=1)
                content.append({"type": "text", "text": "These are frames from the video."})
                for f in frames:
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpg;base64,{f}"}
                    })
            else:
                encoded = encode_file_to_base64(img)
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{ext.lstrip('.')};base64,{encoded}"
                    }
                })
        else:
            # Treat as a remote URL
            content.append({
                "type": "image_url",
                "image_url": {"url": img}
            })
    return content


def process_task_context(context_item, verbose=0, user_id=None):
    """
    Process a single context item for task execution.
    This helper function avoids code duplication between async and sync execution methods.
    Args:
        context_item: The context item to process (can be string, list, task object, or dict)
        verbose: Verbosity level for logging
        user_id: User ID for database queries
        
    Returns:
        str: Formatted context string for this item
    """
    if isinstance(context_item, str):
        return f"Input Content:\n{context_item}"
    elif isinstance(context_item, list):
        return f"Input Content: {' '.join(str(x) for x in context_item)}"
    elif hasattr(context_item, 'result'):  # Task object
        # Ensure the previous task is completed before including its result
        task_status = getattr(context_item, 'status', None)
        task_name = context_item.name if context_item.name else context_item.description
        
        if context_item.result and task_status == TaskStatus.COMPLETED.value:
            # Log detailed result for debugging
            logger.debug(f"Previous task '{task_name}' result: {context_item.result.raw}")
            # Return actual result content without verbose label (essential for task chaining)
            return context_item.result.raw
        elif task_status == TaskStatus.COMPLETED.value and not context_item.result:
            return ""  # No result to include
        else:
            return ""  # Task not completed, no context to include
    elif isinstance(context_item, dict) and ("vector_store" in context_item or "embedding_db_config" in context_item):
        from ..knowledge.knowledge import Knowledge
        try:
            # Handle both string and dict configs - support both vector_store and embedding_db_config keys for backward compatibility
            cfg = context_item.get("vector_store") or context_item.get("embedding_db_config")
            if isinstance(cfg, str):
                cfg = json.loads(cfg)
            
            knowledge = Knowledge(config={"vector_store": cfg}, verbose=verbose)
            
            # Only use user_id as filter
            db_results = knowledge.search(
                context_item.get("query", ""),  # Use query from context if available
                user_id=user_id if user_id else None
            )
            
            # Log knowledge results for debugging (always available for troubleshooting)
            logger.debug(f"Knowledge search results ({len(db_results)} items): {str(db_results)}")
            
            # Return actual content without verbose "[DB Context]:" prefix
            return str(db_results)
        except Exception as e:
            # Log error for debugging (always available for troubleshooting)
            logger.debug(f"Vector DB Error: {e}")
            
            # Return empty string to avoid exposing error details in AI prompts
            # Error details are preserved in debug logs for troubleshooting
            return ""
    else:
        return str(context_item)  # Fallback for unknown types

class AgentManager:
    """
    Multi-agent coordinator that manages and delegates work to multiple agents.
    
    AgentManager orchestrates the execution of tasks across multiple Agent instances,
    supporting sequential, parallel, and hierarchical execution patterns.
    
    Example:
        from praisonaiagents import Agent, AgentManager, Task
        
        researcher = Agent(role="Researcher", instructions="Research topics")
        writer = Agent(role="Writer", instructions="Write content")
        
        task1 = Task(description="Research AI trends", agent=researcher)
        task2 = Task(description="Write article", agent=writer)
        
        manager = AgentManager(
            agents=[researcher, writer],
            tasks=[task1, task2],
            process="sequential"
        )
        result = manager.start()
    
    Note:
        The class was renamed from `Agents` to `AgentManager` in v0.14.16.
        `Agents` remains as a deprecated alias for backward compatibility.
    """
    
    def __init__(
        self,
        agents,
        tasks=None,
        process="sequential",
        manager_llm=None,
        name: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
        # Consolidated feature params (agent-centric API)
        memory: Optional[Any] = False,  # Union[bool, MultiAgentMemoryConfig]
        planning: Optional[Any] = False,  # Union[bool, MultiAgentPlanningConfig]
        context: Optional[Any] = False,  # Union[bool, ManagerConfig, ContextManager]
        output: Optional[Any] = None,  # Union[str, MultiAgentOutputConfig]
        execution: Optional[Any] = None,  # Union[str, MultiAgentExecutionConfig]
        hooks: Optional[Any] = None,  # MultiAgentHooksConfig
        # Additional consolidated params for feature parity with Agent
        autonomy: Optional[Any] = None,  # Union[bool, AutonomyConfig] - agent autonomy
        knowledge: Optional[Any] = None,  # Union[bool, List[str], KnowledgeConfig] - RAG
        guardrails: Optional[Any] = None,  # Union[bool, Callable, GuardrailConfig] - validation
        web: Optional[Any] = None,  # Union[bool, WebConfig] - web search/fetch
        reflection: Optional[Any] = None,  # Union[bool, ReflectionConfig] - self-reflection
        caching: Optional[Any] = None,  # Union[bool, CachingConfig] - caching
    ):
        """
        Initialize AgentManager with consolidated feature parameters.
        
        Args:
            agents: List of Agent instances
            tasks: Optional list of Task instances (auto-generated from agents if None)
            process: Execution process type ("sequential", "parallel", "hierarchical")
            manager_llm: LLM model for manager agent
            name: Name for this agent collection
            variables: Global variables for substitution
            memory: Memory configuration (bool | MultiAgentMemoryConfig)
            planning: Planning configuration (bool | MultiAgentPlanningConfig)
            context: Context management (bool | ManagerConfig | ContextManager)
            output: Output configuration (str | MultiAgentOutputConfig)
            execution: Execution configuration (str | MultiAgentExecutionConfig)
            hooks: Hooks configuration (MultiAgentHooksConfig)
            autonomy: Autonomy configuration (bool | AutonomyConfig)
            knowledge: Knowledge/RAG configuration (bool | List[str] | KnowledgeConfig)
            guardrails: Guardrails configuration (bool | Callable | GuardrailConfig)
            web: Web search/fetch configuration (bool | WebConfig)
            reflection: Self-reflection configuration (bool | ReflectionConfig)
        """
        # Store new params for propagation to agents
        self._autonomy = autonomy
        self._knowledge = knowledge
        self._guardrails = guardrails
        self._web = web
        self._reflection = reflection
        self._caching = caching
        # ─────────────────────────────────────────────────────────────────────
        # Extract values from consolidated params using UNIFIED CANONICAL resolver
        # Precedence: Instance > Config > Dict > Array > String > Bool > Default
        # ─────────────────────────────────────────────────────────────────────
        
        # Import canonical resolver and presets
        from ..config.param_resolver import resolve, ArrayMode
        from ..config.presets import (
            MULTI_AGENT_OUTPUT_PRESETS, MULTI_AGENT_EXECUTION_PRESETS,
            MEMORY_PRESETS, MEMORY_URL_SCHEMES,
        )
        
        # Import config classes for type checking
        try:
            from ..config.feature_configs import (
                MultiAgentMemoryConfig, MultiAgentPlanningConfig,
                MultiAgentOutputConfig, MultiAgentExecutionConfig,
                MultiAgentHooksConfig
            )
        except ImportError:
            MultiAgentMemoryConfig = None
            MultiAgentPlanningConfig = None
            MultiAgentOutputConfig = None
            MultiAgentExecutionConfig = None
            MultiAgentHooksConfig = None
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve OUTPUT param using canonical resolver
        # Supports: None, str preset, list [preset, overrides], Config, dict
        # ─────────────────────────────────────────────────────────────────────
        _output_config = resolve(
            value=output,
            param_name="output",
            config_class=MultiAgentOutputConfig,
            presets=MULTI_AGENT_OUTPUT_PRESETS,
            array_mode=ArrayMode.PRESET_OVERRIDE,
            default=MultiAgentOutputConfig() if MultiAgentOutputConfig else None,
        )
        if _output_config and hasattr(_output_config, 'verbose'):
            _verbose = _output_config.verbose
            _stream = _output_config.stream
        else:
            _verbose = 0
            _stream = True
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve EXECUTION param using canonical resolver
        # Supports: None, str preset, list [preset, overrides], Config, dict
        # ─────────────────────────────────────────────────────────────────────
        _exec_config = resolve(
            value=execution,
            param_name="execution",
            config_class=MultiAgentExecutionConfig,
            presets=MULTI_AGENT_EXECUTION_PRESETS,
            array_mode=ArrayMode.PRESET_OVERRIDE,
            default=MultiAgentExecutionConfig() if MultiAgentExecutionConfig else None,
        )
        if _exec_config and hasattr(_exec_config, 'max_iter'):
            _max_iter = _exec_config.max_iter
            _max_retries = _exec_config.max_retries
        else:
            _max_iter = 10
            _max_retries = 5
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve HOOKS param using canonical resolver
        # Supports: None, list, Config, dict
        # ─────────────────────────────────────────────────────────────────────
        _hooks_config = resolve(
            value=hooks,
            param_name="hooks",
            config_class=MultiAgentHooksConfig,
            array_mode=ArrayMode.PASSTHROUGH,
            default=None,
        )
        if _hooks_config and hasattr(_hooks_config, 'completion_checker'):
            _completion_checker = _hooks_config.completion_checker
            _on_task_start = _hooks_config.on_task_start
            _on_task_complete = _hooks_config.on_task_complete
        else:
            _completion_checker = None
            _on_task_start = None
            _on_task_complete = None
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve MEMORY param using canonical resolver
        # Supports: None, bool, str preset/URL, list, Config, dict, Instance
        # ─────────────────────────────────────────────────────────────────────
        _memory_config_resolved = resolve(
            value=memory,
            param_name="memory",
            config_class=MultiAgentMemoryConfig,
            presets=MEMORY_PRESETS,
            url_schemes=MEMORY_URL_SCHEMES,
            instance_check=lambda v: hasattr(v, 'database_url'),
            array_mode=ArrayMode.SINGLE_OR_LIST,
            default=None,
        )
        
        # Extract values from resolved memory config
        _user_id = "praison"
        _memory_config = None
        _embedder = None
        if _memory_config_resolved is not None:
            if hasattr(_memory_config_resolved, 'database_url'):
                # db() instance - pass through
                _memory_config = {"db_instance": _memory_config_resolved}
            elif MultiAgentMemoryConfig and isinstance(_memory_config_resolved, MultiAgentMemoryConfig):
                _user_id = _memory_config_resolved.user_id or "praison"
                _memory_config = _memory_config_resolved.config
                _embedder = _memory_config_resolved.embedder
            elif isinstance(_memory_config_resolved, dict):
                # Dict from preset resolution
                _memory_config = _memory_config_resolved
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve PLANNING param using canonical resolver
        # Supports: None, bool, str LLM, list, Config, dict
        # ─────────────────────────────────────────────────────────────────────
        _planning_config = resolve(
            value=planning,
            param_name="planning",
            config_class=MultiAgentPlanningConfig,
            string_mode="llm_model",
            array_mode=ArrayMode.PRESET_OVERRIDE,
            default=None,
        )
        
        # Extract values from resolved planning config
        _planning_llm = "gpt-4o-mini"
        _auto_approve_plan = False
        _planning_tools = None
        _planning_reasoning = False
        if _planning_config is not None:
            if MultiAgentPlanningConfig and isinstance(_planning_config, MultiAgentPlanningConfig):
                _planning_llm = _planning_config.llm or "gpt-4o-mini"
                _auto_approve_plan = _planning_config.auto_approve
                _planning_tools = _planning_config.tools
                _planning_reasoning = _planning_config.reasoning
        
        # ─────────────────────────────────────────────────────────────────────
        # Memory dependency check
        # ─────────────────────────────────────────────────────────────────────
        if memory:
            try:
                from ..memory.memory import Memory
            except ImportError:
                raise ImportError(
                    "Memory features requested but memory dependencies not installed. "
                    "Please install with: pip install \"praisonaiagents[memory]\""
                )

        if not agents:
            raise ValueError("At least one agent must be provided")
        
        # ─────────────────────────────────────────────────────────────────────
        # Core initialization
        # ─────────────────────────────────────────────────────────────────────
        self.run_id = str(uuid.uuid4())
        self.user_id = _user_id
        self.max_iter = _max_iter

        # Pass user_id to each agent
        for agent in agents:
            agent.user_id = self.user_id

        self.agents: List[Agent] = agents
        self.tasks: Dict[int, Task] = {}
        if _max_retries < 3:
            _max_retries = 3
        self.completion_checker = _completion_checker if _completion_checker else self.default_completion_checker
        self.task_id_counter = 0
        self.verbose = _verbose
        self.max_retries = _max_retries
        self.process = process
        self.stream = _stream
        self.name = name
        
        # Callbacks for workflow execution
        self.on_task_start = _on_task_start
        self.on_task_complete = _on_task_complete
        self.variables = variables if variables else {}
        
        # Check for manager_llm in environment variable if not provided
        self.manager_llm = manager_llm or os.getenv('OPENAI_MODEL_NAME', 'gpt-4o-mini')
        
        # Set logger level based on verbose
        if _verbose >= 5:
            logger.setLevel(logging.INFO)
        elif _verbose >= 3:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.WARNING)
            
        # Also set third-party loggers to WARNING
        logging.getLogger('chromadb').setLevel(logging.WARNING)
        logging.getLogger('openai').setLevel(logging.WARNING)
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)

        if self.verbose:
            logger.info(f"Using model {self.manager_llm} for manager")
        
        # If no tasks provided, generate them from agents
        if tasks is None:
            tasks = []
            for agent in self.agents:
                task = agent.generate_task()
                tasks.append(task)
            logger.info(f"Auto-generated {len(tasks)} tasks from agents")
        else:
            if not tasks:
                raise ValueError("If tasks are provided, at least one task must be present")
            logger.info(f"Using {len(tasks)} provided tasks")
        
        # Add tasks and set their status
        for task in tasks:
            self.add_task(task)
            task.status = "not started"
            
        # Set up sequential flow if needed
        if len(tasks) > 1 and (process == "sequential" or all(task.next_tasks == [] for task in tasks)):
            for i in range(len(tasks) - 1):
                tasks[i].next_tasks = [tasks[i + 1].name]
                if tasks[i + 1].context is None:
                    tasks[i + 1].context = []
                tasks[i + 1].context.append(tasks[i])
            logger.info("Set up sequential flow with automatic context passing")
        
        self._state = {}
        
        # Context management
        self._context_param = context
        self._context_manager = None
        self._context_manager_initialized = False
        
        # Planning mode
        self.planning = planning
        self.planning_llm = _planning_llm
        self.auto_approve_plan = _auto_approve_plan
        self.planning_tools = _planning_tools
        self.planning_reasoning = _planning_reasoning
        self._current_plan = None
        self._todo_list = None
        self._planning_agent = None
        
        # Memory system
        self.shared_memory = None
        if memory:
            try:
                from ..memory.memory import Memory
                
                mem_cfg = _memory_config
                if not mem_cfg:
                    mem_cfg = next((t.config.get('memory_config') for t in tasks if hasattr(t, 'config') and t.config), None)
                if not mem_cfg:
                    mem_cfg = {
                        "provider": "rag",
                        "use_embedding": True,
                        "storage": {
                            "type": "sqlite",
                            "path": "./.praison/memory.db"
                        },
                        "rag_db_path": "./.praison/chroma_db"
                    }
                if _embedder:
                    if isinstance(_embedder, dict):
                        mem_cfg = mem_cfg or {}
                        mem_cfg["embedder"] = _embedder
                    else:
                        mem_cfg = mem_cfg or {}
                        mem_cfg["embedder_function"] = _embedder

                if mem_cfg:
                    self.shared_memory = Memory(config=mem_cfg, verbose=_verbose)
                    if _verbose >= 5:
                        logger.info("Initialized shared memory for Agents")
                    for task in tasks:
                        if not task.memory:
                            task.memory = self.shared_memory
                            if _verbose >= 5:
                                logger.info(f"Assigned shared memory to task {task.id}")
            except Exception as e:
                logger.error(f"Failed to initialize shared memory: {e}")
        
        if self.shared_memory:
            for task in tasks:
                    task.memory = self.shared_memory
                    logger.info(f"Assigned shared memory to task {task.id}")

        # Telemetry
        try:
            from ..telemetry import get_telemetry
            self._telemetry = get_telemetry()
        except (ImportError, AttributeError):
            self._telemetry = None

    def add_task(self, task):
        task_id = self.task_id_counter
        task.id = task_id
        self.tasks[task_id] = task
        self.task_id_counter += 1
        return task_id

    def clean_json_output(self, output: str) -> str:
        cleaned = output.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[len("```json"):].strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[len("```"):].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        return cleaned

    @property
    def context_manager(self):
        """
        ContextManager instance for unified context management across all agents.
        
        Lazy initialized on first access when context=True or context=ManagerConfig.
        Returns None when context=False (zero overhead).
        
        For multi-agent scenarios, uses MultiAgentContextManager for per-agent isolation.
        """
        if self._context_manager_initialized:
            return self._context_manager
        
        # Initialize based on context param type
        if self._context_param is False or self._context_param is None:
            # Zero overhead - no context management
            self._context_manager = None
            self._context_manager_initialized = True
            return None
        
        # Lazy import to avoid overhead when not used
        try:
            from ..context import MultiAgentContextManager, ManagerConfig
        except ImportError:
            # Context module not available
            self._context_manager = None
            self._context_manager_initialized = True
            return None
        
        if self._context_param is True:
            # Enable with safe defaults for multi-agent
            self._context_manager = MultiAgentContextManager()
        elif isinstance(self._context_param, ManagerConfig):
            # Use provided config for all agents
            self._context_manager = MultiAgentContextManager(config=self._context_param)
        elif hasattr(self._context_param, 'get_agent_manager'):
            # Already a MultiAgentContextManager instance
            self._context_manager = self._context_param
        else:
            # Unknown type, disable
            self._context_manager = None
        
        self._context_manager_initialized = True
        return self._context_manager

    def default_completion_checker(self, task, agent_output):
        if task.output_json and task.result and task.result.json_dict:
            return True
        if task.output_pydantic and task.result and task.result.pydantic:
            return True
        return len(agent_output.strip()) > 0

    async def aexecute_task(self, task_id):
        """Async version of execute_task method"""
        if task_id not in self.tasks:
            display_error(f"Error: Task with ID {task_id} does not exist")
            return
        task = self.tasks[task_id]
        
        # Only import multimodal dependencies if task has images
        if task.images and task.status == "not started":
            try:
                import cv2  # noqa: F401 - availability check
                import base64  # noqa: F401 - availability check
                from moviepy import VideoFileClip  # noqa: F401 - availability check
            except ImportError as e:
                display_error(f"Error: Missing required dependencies for image/video processing: {e}")
                display_error("Please install with: pip install opencv-python moviepy")
                task.status = "failed"
                return None

        if task.status == "not started":
            task.status = "in progress"

        executor_agent = task.agent
        
        # Set current agent for token tracking
        llm = getattr(executor_agent, 'llm', None) or getattr(executor_agent, 'llm_instance', None)
        if llm and hasattr(llm, 'set_current_agent'):
            llm.set_current_agent(executor_agent.display_name)

        # Ensure tools are available from both task and agent
        tools = task.tools or []
        if executor_agent and executor_agent.tools:
            tools.extend(executor_agent.tools)

        task_prompt = f"""
You need to do the following task: {task.description}.
Expected Output: {task.expected_output}.
"""
        if task.context:
            context_results = []  # Use list to avoid duplicates
            for context_item in task.context:
                # Use the centralized helper function
                context_str = process_task_context(context_item, self.verbose, self.user_id)
                context_results.append(context_str)
            
            # Join unique context results with proper formatting
            unique_contexts = list(dict.fromkeys(context_results))  # Remove duplicates
            if self.verbose >= 3:
                logger.info(f"Task {task_id} context items: {len(unique_contexts)}")
                for i, ctx in enumerate(unique_contexts):
                    logger.debug(f"Context {i+1}: {ctx[:100]}...")
            context_separator = '\n\n'
            task_prompt += f"""
Context:

{context_separator.join(unique_contexts)}
"""
        task_prompt += "Please provide only the final result of your work. Do not add any conversation or extra explanation."

        if self.verbose >= 2:
            logger.info(f"Executing task {task_id}: {task.description} using {executor_agent.display_name}")
        logger.debug(f"Starting execution of task {task_id} with prompt:\n{task_prompt}")

        if task.images:
            # Use shared multimodal helper (DRY - defined at module level)
            agent_output = await executor_agent.achat(
                get_multimodal_message(task_prompt, task.images),
                tools=tools,
                output_json=task.output_json,
                output_pydantic=task.output_pydantic,
                task_name=task.name,
                task_description=task.description,
                task_id=task.id
            )
        else:
            agent_output = await executor_agent.achat(
                task_prompt,
                tools=tools,
                output_json=task.output_json,
                output_pydantic=task.output_pydantic,
                task_name=task.name,
                task_description=task.description,
                task_id=task.id
            )

        if agent_output:
            task_output = TaskOutput(
                description=task.description,
                summary=task.description[:10],
                raw=agent_output,
                agent=executor_agent.display_name,
                output_format="RAW"
            )
            
            # Add token metrics if available
            if llm and hasattr(llm, 'last_token_metrics'):
                token_metrics = llm.last_token_metrics
                if token_metrics:
                    task_output.token_metrics = token_metrics

            if task.output_json:
                cleaned = self.clean_json_output(agent_output)
                try:
                    parsed = json.loads(cleaned)
                    task_output.json_dict = parsed
                    task_output.output_format = "JSON"
                except Exception:
                    logger.warning(f"Warning: Could not parse output of task {task_id} as JSON")
                    logger.debug(f"Output that failed JSON parsing: {agent_output}")

            if task.output_pydantic:
                cleaned = self.clean_json_output(agent_output)
                try:
                    parsed = json.loads(cleaned)
                    pyd_obj = task.output_pydantic(**parsed)
                    task_output.pydantic = pyd_obj
                    task_output.output_format = "Pydantic"
                except Exception:
                    logger.warning(f"Warning: Could not parse output of task {task_id} as Pydantic Model")
                    logger.debug(f"Output that failed Pydantic parsing: {agent_output}")

            task.result = task_output
            return task_output
        else:
            task.status = "failed"
            return None

    async def arun_task(self, task_id):
        """Async version of run_task method"""
        if task_id not in self.tasks:
            display_error(f"Error: Task with ID {task_id} does not exist")
            return
        task = self.tasks[task_id]
        if task.status == "completed":
            logger.info(f"Task with ID {task_id} is already completed")
            return

        retries = 0
        while task.status != "completed" and retries < self.max_retries:
            logger.debug(f"Attempt {retries+1} for task {task_id}")
            if task.status in ["not started", "in progress"]:
                task_output = await self.aexecute_task(task_id)
                if task_output and self.completion_checker(task, task_output.raw):
                    task.status = "completed"
                    # Run execute_callback for memory operations
                    try:
                        # Use the new sync wrapper to avoid pending coroutine issues
                        task.execute_callback_sync(task_output)
                    except Exception as e:
                        logger.error(f"Error executing memory callback for task {task_id}: {e}")
                        logger.exception(e)
                    
                    # Run task callback if exists
                    if task.callback:
                        try:
                            if asyncio.iscoroutinefunction(task.callback):
                                try:
                                    loop = asyncio.get_running_loop()
                                    loop.create_task(task.callback(task_output))
                                except RuntimeError:
                                    # No event loop running, create new one
                                    asyncio.run(task.callback(task_output))
                            else:
                                task.callback(task_output)
                        except Exception as e:
                            logger.error(f"Error executing task callback for task {task_id}: {e}")
                            logger.exception(e)
                            
                    self.save_output_to_file(task, task_output)
                    if self.verbose >= 1:
                        logger.info(f"Task {task_id} completed successfully.")
                else:
                    task.status = "in progress"
                    if self.verbose >= 1:
                        logger.info(f"Task {task_id} not completed, retrying")
                    await asyncio.sleep(1)
                    retries += 1
            else:
                if task.status == "failed":
                    logger.info("Task is failed, resetting to in-progress for another try...")
                    task.status = "in progress"
                else:
                    logger.info("Invalid Task status")
                    break

        if retries == self.max_retries and task.status != "completed":
            logger.info(f"Task {task_id} failed after {self.max_retries} retries.")

    async def arun_all_tasks(self):
        """Async version of run_all_tasks method"""
        process = Process(
            tasks=self.tasks,
            agents=self.agents,
            manager_llm=self.manager_llm,
            verbose=self.verbose,
            max_iter=self.max_iter
        )
        
        if self.process == "workflow":
            tasks_to_run = []
            async for task_id in process.aworkflow():
                if self.tasks[task_id].async_execution:
                    tasks_to_run.append(self.arun_task(task_id))
                else:
                    # If we encounter a sync task, we must wait for the previous async tasks to finish.
                    if tasks_to_run:
                        await asyncio.gather(*tasks_to_run)
                        tasks_to_run = []
                    
                    # Run sync task in an executor to avoid blocking the event loop
                    # Use copy_context_to_callable to propagate contextvars (needed for trace emission)
                    from ..trace.context_events import copy_context_to_callable
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, copy_context_to_callable(lambda tid=task_id: self.run_task(tid)))

            if tasks_to_run:
                await asyncio.gather(*tasks_to_run)
                
        elif self.process == "sequential":
            async_tasks_to_run = []
            
            async def flush_async_tasks():
                """Execute all pending async tasks"""
                nonlocal async_tasks_to_run
                if async_tasks_to_run:
                    await asyncio.gather(*async_tasks_to_run)
                    async_tasks_to_run = []
            
            async for task_id in process.asequential():
                if self.tasks[task_id].async_execution:
                    # Collect async tasks to run in parallel
                    async_tasks_to_run.append(self.arun_task(task_id))
                else:
                    # Before running a sync task, execute all pending async tasks
                    await flush_async_tasks()
                    # Run sync task in an executor to avoid blocking the event loop
                    # Use copy_context_to_callable to propagate contextvars (needed for trace emission)
                    from ..trace.context_events import copy_context_to_callable
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, copy_context_to_callable(lambda tid=task_id: self.run_task(tid)))
            
            # Execute any remaining async tasks at the end
            await flush_async_tasks()
        elif self.process == "hierarchical":
            async for task_id in process.ahierarchical():
                if isinstance(task_id, Task):
                    task_id = self.add_task(task_id)
                if self.tasks[task_id].async_execution:
                    await self.arun_task(task_id)
                else:
                    # Run sync task in an executor to avoid blocking the event loop
                    # Use copy_context_to_callable to propagate contextvars (needed for trace emission)
                    from ..trace.context_events import copy_context_to_callable
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, copy_context_to_callable(lambda tid=task_id: self.run_task(tid)))

    async def astart(self, content=None, return_dict=False, **kwargs):
        """Async version of start method.
        
        Args:
            content: Optional content to add to all tasks' context
            return_dict: If True, returns the full results dictionary instead of only the final response
            **kwargs: Additional arguments
        """
        # Track execution via telemetry
        if hasattr(self, '_telemetry') and self._telemetry:
            self._telemetry.track_agent_execution(self.name, success=True, async_mode=True)
            
        if content:
            # Add content to context of all tasks
            for task in self.tasks.values():
                if isinstance(content, (str, list)):
                    if not task.context:
                        task.context = []
                    task.context.append(content)

        await self.arun_all_tasks()
        
        # Get results
        results = {
            "task_status": self.get_all_tasks_status(),
            "task_results": {task_id: self.get_task_result(task_id) for task_id in self.tasks}
        }
        
        # By default, return only the final agent's response
        if not return_dict:
            # Get the last task (assuming sequential processing)
            task_ids = list(self.tasks.keys())
            if task_ids:
                last_task_id = task_ids[-1]
                last_result = self.get_task_result(last_task_id)
                if last_result:
                    return last_result.raw
                    
        # Return full results dict if return_dict is True or if no final result was found
        return results

    def save_output_to_file(self, task, task_output):
        if task.output_file:
            try:
                if task.create_directory:
                    os.makedirs(os.path.dirname(task.output_file), exist_ok=True)
                with open(task.output_file, "w") as f:
                    f.write(str(task_output))
                if self.verbose >= 1:
                    logger.info(f"Task output saved to {task.output_file}")
            except Exception as e:
                display_error(f"Error saving task output to file: {e}")

    def execute_task(self, task_id):
        """Synchronous version of execute_task method"""
        if task_id not in self.tasks:
            display_error(f"Error: Task with ID {task_id} does not exist")
            return
        task = self.tasks[task_id]
        
        logger.info(f"Starting execution of task {task_id}")
        logger.info(f"Task config: {task.config}")
        
        # Initialize memory before task execution
        if not task.memory:
            task.memory = task.initialize_memory()
        
        logger.info(f"Task memory status: {'Initialized' if task.memory else 'Not initialized'}")
        
        # Only import multimodal dependencies if task has images
        if task.images and task.status == "not started":
            try:
                import cv2  # noqa: F401 - availability check
                import base64  # noqa: F401 - availability check
                from moviepy import VideoFileClip  # noqa: F401 - availability check
            except ImportError as e:
                display_error(f"Error: Missing required dependencies for image/video processing: {e}")
                display_error("Please install with: pip install opencv-python moviepy")
                task.status = "failed"
                return None

        if task.status == "not started":
            task.status = "in progress"

        executor_agent = task.agent
        
        # Create agent from agent_config if provided and no agent assigned
        if executor_agent is None and getattr(task, 'agent_config', None):
            executor_agent = self._create_agent_from_config(task.agent_config)
            task.agent = executor_agent
        
        # Set current agent for token tracking
        llm = getattr(executor_agent, 'llm', None) or getattr(executor_agent, 'llm_instance', None)
        if llm and hasattr(llm, 'set_current_agent'):
            llm.set_current_agent(executor_agent.display_name)

        # Substitute variables in task description if provided
        task_description = task.description
        if getattr(task, 'variables', None):
            for key, value in task.variables.items():
                task_description = task_description.replace(f"{{{{{key}}}}}", str(value))

        task_prompt = f"""
You need to do the following task: {task_description}.
Expected Output: {task.expected_output}.
"""
        if task.context:
            context_results = []  # Use list to avoid duplicates
            for context_item in task.context:
                # Use the centralized helper function
                context_str = process_task_context(context_item, self.verbose, self.user_id)
                context_results.append(context_str)
            
            # Join unique context results with proper formatting
            unique_contexts = list(dict.fromkeys(context_results))  # Remove duplicates
            if self.verbose >= 3:
                logger.info(f"Task {task_id} context items: {len(unique_contexts)}")
                for i, ctx in enumerate(unique_contexts):
                    logger.debug(f"Context {i+1}: {ctx[:100]}...")
            context_separator = '\n\n'
            task_prompt += f"""
Context:

{context_separator.join(unique_contexts)}
"""

        # Add memory context if available
        if task.memory:
            try:
                memory_context = task.memory.build_context_for_task(task.description)
                if memory_context:
                    # Log detailed memory context for debugging
                    logger.debug(f"Memory context for task '{task.description}': {memory_context}")
                    # Include actual memory content without verbose headers (essential for AI agent functionality)
                    task_prompt += f"\n\n{memory_context}"
            except Exception as e:
                logger.error(f"Error getting memory context: {e}")

        task_prompt += "Please provide only the final result of your work. Do not add any conversation or extra explanation."

        if self.verbose >= 2:
            logger.info(f"Executing task {task_id}: {task.description} using {executor_agent.display_name}")
        logger.debug(f"Starting execution of task {task_id} with prompt:\n{task_prompt}")

        if task.images:
            # Use shared multimodal helper (DRY - defined at module level)
            agent_output = executor_agent.chat(
                get_multimodal_message(task_prompt, task.images),
                tools=task.tools,
                output_json=task.output_json,
                output_pydantic=task.output_pydantic,
                task_name=task.name,
                task_description=task.description,
                task_id=task_id
            )
        else:
            agent_output = executor_agent.chat(
                task_prompt,
                tools=task.tools,
                output_json=task.output_json,
                output_pydantic=task.output_pydantic,
                stream=self.stream,
                task_name=task.name,
                task_description=task.description,
                task_id=task_id
            )

        if agent_output:
            # Store the response in memory
            if task.memory:
                try:
                    task.store_in_memory(
                        content=agent_output,
                        agent_name=executor_agent.display_name,
                        task_id=task_id
                    )
                except Exception as e:
                    logger.error(f"Failed to store agent output in memory: {e}")

            task_output = TaskOutput(
                description=task.description,
                summary=task.description[:10],
                raw=agent_output,
                agent=executor_agent.display_name,
                output_format="RAW"
            )
            
            # Add token metrics if available
            if llm and hasattr(llm, 'last_token_metrics'):
                token_metrics = llm.last_token_metrics
                if token_metrics:
                    task_output.token_metrics = token_metrics

            if task.output_json:
                cleaned = self.clean_json_output(agent_output)
                try:
                    parsed = json.loads(cleaned)
                    task_output.json_dict = parsed
                    task_output.output_format = "JSON"
                except Exception:
                    logger.warning(f"Warning: Could not parse output of task {task_id} as JSON")
                    logger.debug(f"Output that failed JSON parsing: {agent_output}")

            if task.output_pydantic:
                cleaned = self.clean_json_output(agent_output)
                try:
                    parsed = json.loads(cleaned)
                    pyd_obj = task.output_pydantic(**parsed)
                    task_output.pydantic = pyd_obj
                    task_output.output_format = "Pydantic"
                except Exception:
                    logger.warning(f"Warning: Could not parse output of task {task_id} as Pydantic Model")
                    logger.debug(f"Output that failed Pydantic parsing: {agent_output}")

            task.result = task_output
            return task_output
        else:
            task.status = "failed"
            return None

    def run_task(self, task_id):
        """Synchronous version of run_task method"""
        if task_id not in self.tasks:
            display_error(f"Error: Task with ID {task_id} does not exist")
            return
        task = self.tasks[task_id]
        if task.status == "completed":
            logger.info(f"Task with ID {task_id} is already completed")
            return

        # Call on_task_start callback if provided
        if self.on_task_start:
            try:
                self.on_task_start(task, task_id)
            except Exception as e:
                logger.error(f"Error in on_task_start callback: {e}")
        
        # Apply global variables to task if not already set
        if self.variables and not getattr(task, 'variables', None):
            task.variables = self.variables
        
        retries = 0
        while task.status != "completed" and retries < self.max_retries:
            logger.debug(f"Attempt {retries+1} for task {task_id}")
            if task.status in ["not started", "in progress"]:
                task_output = self.execute_task(task_id)
                if task_output and self.completion_checker(task, task_output.raw):
                    task.status = "completed"
                    # Run execute_callback for memory operations
                    try:
                        # Use the new sync wrapper to avoid pending coroutine issues
                        task.execute_callback_sync(task_output)
                    except Exception as e:
                        logger.error(f"Error executing memory callback for task {task_id}: {e}")
                        logger.exception(e)
                    
                    # Run task callback if exists
                    if task.callback:
                        try:
                            if asyncio.iscoroutinefunction(task.callback):
                                try:
                                    loop = asyncio.get_running_loop()
                                    loop.create_task(task.callback(task_output))
                                except RuntimeError:
                                    # No event loop running, create new one
                                    asyncio.run(task.callback(task_output))
                            else:
                                task.callback(task_output)
                        except Exception as e:
                            logger.error(f"Error executing task callback for task {task_id}: {e}")
                            logger.exception(e)
                            
                    self.save_output_to_file(task, task_output)
                    
                    # Call on_task_complete callback if provided
                    if self.on_task_complete:
                        try:
                            self.on_task_complete(task, task_output)
                        except Exception as e:
                            logger.error(f"Error in on_task_complete callback: {e}")
                    
                    if self.verbose >= 1:
                        logger.info(f"Task {task_id} completed successfully.")
                else:
                    task.status = "in progress"
                    if self.verbose >= 1:
                        logger.info(f"Task {task_id} not completed, retrying")
                    time.sleep(1)
                    retries += 1
            else:
                if task.status == "failed":
                    logger.info("Task is failed, resetting to in-progress for another try...")
                    task.status = "in progress"
                else:
                    logger.info("Invalid Task status")
                    break

        if retries == self.max_retries and task.status != "completed":
            logger.info(f"Task {task_id} failed after {self.max_retries} retries.")

    def run_all_tasks(self):
        """Synchronous version of run_all_tasks method"""
        process = Process(
            tasks=self.tasks,
            agents=self.agents,
            manager_llm=self.manager_llm,
            verbose=self.verbose,
            max_iter=self.max_iter
        )
        
        if self.process == "workflow":
            for task_id in process.workflow():
                self.run_task(task_id)
        elif self.process == "sequential":
            for task_id in process.sequential():
                self.run_task(task_id)
        elif self.process == "hierarchical":
            for task_id in process.hierarchical():
                if isinstance(task_id, Task):
                    task_id = self.add_task(task_id)
                self.run_task(task_id)

    def get_task_status(self, task_id):
        if task_id in self.tasks:
            return self.tasks[task_id].status
        return None

    def get_all_tasks_status(self):
        return {task_id: self.tasks[task_id].status for task_id in self.tasks}

    def get_task_result(self, task_id):
        if task_id in self.tasks:
            return self.tasks[task_id].result
        return None

    def get_task_details(self, task_id):
        if task_id in self.tasks:
            return str(self.tasks[task_id])
        return None

    def get_agent_details(self, agent_name):
        agent = [task.agent for task in self.tasks.values() if task.agent and task.agent.name == agent_name]
        if agent:
            return str(agent[0])
        return None

    def start(self, content=None, return_dict=False, output=None, **kwargs):
        """Start agent execution with verbose output (beginner-friendly).
        
        Shows Rich panels with workflow progress when in TTY. Use .run() for
        silent execution in production/scripts.
        
        Args:
            content: Optional content to add to all tasks' context
            return_dict: If True, returns the full results dictionary
            output: Output preset - "silent", "verbose", "normal", etc.
                    Default in TTY: "verbose" (shows progress)
                    Default non-TTY: "silent"
            **kwargs: Additional arguments
            
        Example:
            ```python
            # Interactive - shows Rich panels
            agents = AgentManager(agents=[agent1, agent2])
            result = agents.start()  # Verbose output by default
            
            # Force silent mode
            result = agents.start(output="silent")
            ```
        """
        # Track execution via telemetry
        if hasattr(self, '_telemetry') and self._telemetry:
            self._telemetry.track_agent_execution(self.name, success=True)
        import sys
        from ..main import PRAISON_COLORS
        
        # Determine if we're in an interactive TTY
        is_tty = sys.stdout.isatty()
        
        # Resolve output mode (TTY-aware)
        if output is None:
            # Default: verbose in TTY (beginner-friendly), silent otherwise
            # Note: Don't check self.verbose here - start() is for interactive use
            show_verbose = is_tty
        elif output == "silent":
            show_verbose = False
        elif output in ("verbose", "debug", "normal"):
            show_verbose = True
        else:
            show_verbose = is_tty
        
        # Add content to context if provided
        if content:
            for task in self.tasks.values():
                if isinstance(content, (str, list)):
                    if not task.context:
                        task.context = []
                    task.context.append(content)
        
        # ─────────────────────────────────────────────────────────────
        # Verbose Mode: Show Rich panels for multi-agent workflow
        # ─────────────────────────────────────────────────────────────
        if show_verbose and is_tty:
            from rich.panel import Panel
            console = Console()
            import time as time_module
            
            # Show workflow overview panel
            agent_names = " → ".join([a.display_name for a in self.agents])
            workflow_info = f"[bold {PRAISON_COLORS['metrics']}]Process:[/] {self.process}\n"
            workflow_info += f"[bold {PRAISON_COLORS['metrics']}]Agents:[/] {agent_names}"
            
            console.print(Panel(
                workflow_info,
                title="[bold]Multi-Agent Workflow[/]",
                border_style=PRAISON_COLORS["agent"],
                padding=(1, 2)
            ))
            console.print()
            
            # Execute tasks with verbose output
            total_agents = len(self.agents)
            workflow_start_time = time_module.time()
            
            for idx, (task_id, task) in enumerate(self.tasks.items(), 1):
                agent = task.agent
                agent_name = agent.display_name if agent else "Unknown"
                agent_model = getattr(agent, 'llm', 'gpt-4o-mini') if agent else "unknown"
                
                # Show agent task panel with model info
                task_desc = task.description[:100] + "..." if len(task.description) > 100 else task.description
                panel_content = f"[bold {PRAISON_COLORS['task_text']}]📋 Task:[/] {task_desc}\n"
                panel_content += f"[dim]🤖 Model: {agent_model}[/dim]"
                console.print(Panel.fit(
                    panel_content,
                    title=f"[bold]Agent [{idx}/{total_agents}]: {agent_name}[/]",
                    border_style=PRAISON_COLORS["task"]
                ))
                
                # Execute with timing and status
                start_time = time_module.time()
                
                # Show working spinner
                with console.status(
                    f"[bold yellow]Working...[/]  {agent_name} generating response...",
                    spinner="dots",
                    spinner_style="yellow"
                ):
                    # Run the task
                    if self.planning:
                        self._run_with_planning()
                        break  # Planning mode handles all tasks
                    else:
                        self.run_task(task_id)
                
                elapsed = time_module.time() - start_time
                
                # Show response panel - FULL response, no truncation
                result = self.get_task_result(task_id)
                if result:
                    response_text = str(result.raw)
                    # No truncation - show full response in verbose mode
                    from rich.markdown import Markdown
                    console.print(Panel(
                        Markdown(response_text),
                        title=f"[bold]Agent [{idx}/{total_agents}] Complete ({elapsed:.1f}s)[/]",
                        border_style=PRAISON_COLORS["response"],
                        padding=(1, 2)
                    ))
                console.print()
            
            # Workflow summary panel
            total_elapsed = time_module.time() - workflow_start_time
            console.print(Panel.fit(
                f"[bold green]Total Time:[/] {total_elapsed:.1f}s\n"
                f"[bold green]Agents Run:[/] {total_agents}/{total_agents}",
                title="[bold]✅ Workflow Complete[/]",
                border_style="green"
            ))
            console.print()
        else:
            # Silent mode: Run tasks without display
            if self.planning:
                self._run_with_planning()
            else:
                self.run_all_tasks()
        
        # Auto-display token metrics if any agent has metrics=True
        metrics_enabled = any(getattr(agent, 'metrics', False) for agent in self.agents)
        if metrics_enabled:
            try:
                self.display_token_usage()
            except (ImportError, AttributeError) as e:
                logging.debug(f"Could not auto-display token usage: {e}")
            except Exception as e:
                logging.debug(f"Unexpected error in token metrics display: {e}")
        
        # Get results
        results = {
            "task_status": self.get_all_tasks_status(),
            "task_results": {task_id: self.get_task_result(task_id) for task_id in self.tasks}
        }
        
        # By default, return only the final agent's response
        if not return_dict:
            task_ids = list(self.tasks.keys())
            if task_ids:
                last_task_id = task_ids[-1]
                last_result = self.get_task_result(last_task_id)
                if last_result:
                    return last_result.raw
                    
        return results

    def run(self, content=None, return_dict=False, **kwargs):
        """Run agents silently (production use).
        
        Unlike .start() which shows verbose output, .run() executes silently
        for programmatic/production use.
        
        Args:
            content: Optional content to add to all tasks' context
            return_dict: If True, returns the full results dictionary
            **kwargs: Additional arguments
        """
        # Always run silently - no verbose output
        return self.start(content=content, return_dict=return_dict, output="silent", **kwargs)

    def set_state(self, key: str, value: Any) -> None:
        """Set a state value"""
        self._state[key] = value

    def get_state(self, key: str, default: Any = None) -> Any:
        """Get a state value"""
        return self._state.get(key, default)

    def update_state(self, updates: Dict) -> None:
        """Update multiple state values"""
        self._state.update(updates)

    def clear_state(self) -> None:
        """Clear all state values"""
        self._state.clear()
    
    # Convenience methods for enhanced state management
    def has_state(self, key: str) -> bool:
        """Check if a state key exists"""
        return key in self._state
    
    def get_all_state(self) -> Dict[str, Any]:
        """Get a copy of the entire state dictionary"""
        return self._state.copy()
    
    def delete_state(self, key: str) -> bool:
        """Delete a state key if it exists. Returns True if deleted, False if key didn't exist."""
        if key in self._state:
            del self._state[key]
            return True
        return False
    
    def increment_state(self, key: str, amount: float = 1, default: float = 0) -> float:
        """Increment a numeric state value. Creates the key with default if it doesn't exist."""
        current = self._state.get(key, default)
        if not isinstance(current, (int, float)):
            raise TypeError(f"Cannot increment non-numeric value at key '{key}': {type(current).__name__}")
        new_value = current + amount
        self._state[key] = new_value
        return new_value
    
    def append_to_state(self, key: str, value: Any, max_length: Optional[int] = None) -> List[Any]:
        """Append a value to a list state. Creates the list if it doesn't exist.
        
        Args:
            key: State key
            value: Value to append
            max_length: Optional maximum length for the list
            
        Returns:
            The updated list
            
        Raises:
            TypeError: If the existing value is not a list and convert_to_list=False
        """
        if key not in self._state:
            self._state[key] = []
        elif not isinstance(self._state[key], list):
            # Be explicit about type conversion for better user experience
            current_value = self._state[key]
            self._state[key] = [current_value]
        
        self._state[key].append(value)
        
        # Trim list if max_length is specified
        if max_length and len(self._state[key]) > max_length:
            self._state[key] = self._state[key][-max_length:]
        
        return self._state[key]
    
    def save_session_state(self, session_id: str, include_memory: bool = True) -> None:
        """Save current state to memory for session persistence"""
        if self.shared_memory and include_memory:
            state_data = {
                "session_id": session_id,
                "user_id": self.user_id,
                "run_id": self.run_id,
                "state": self._state,
                "agents": [agent.display_name for agent in self.agents],
                "process": self.process
            }
            self.shared_memory.store_short_term(
                text=f"Session state for {session_id}",
                metadata={
                    "type": "session_state",
                    "session_id": session_id,
                    "user_id": self.user_id,
                    "state_data": state_data
                }
            )
    
    def restore_session_state(self, session_id: str) -> bool:
        """Restore state from memory for session persistence. Returns True if restored."""
        if not self.shared_memory:
            return False
        
        # Use metadata-based search for better SQLite compatibility
        results = self.shared_memory.search_short_term(
            query=f"type:session_state",
            limit=10  # Get more results to filter by session_id
        )
        
        # Filter results by session_id in metadata
        for result in results:
            metadata = result.get("metadata", {})
            if (metadata.get("type") == "session_state" and 
                metadata.get("session_id") == session_id):
                state_data = metadata.get("state_data", {})
                if "state" in state_data:
                    # Merge with existing state instead of replacing
                    self._state.update(state_data["state"])
                    return True
        
        return False

    def get_token_usage_summary(self) -> Dict[str, Any]:
        """Get a summary of token usage across all agents and tasks."""
        if not _token_collector:
            return {"error": "Token tracking not available"}
        
        return _token_collector.get_session_summary()
    
    def get_detailed_token_report(self) -> Dict[str, Any]:
        """Get a detailed token usage report."""
        if not _token_collector:
            return {"error": "Token tracking not available"}
        
        summary = _token_collector.get_session_summary()
        recent = _token_collector.get_recent_interactions(limit=20)
        
        # Calculate cost estimates (example rates)
        cost_per_1k_input = 0.0005  # $0.0005 per 1K input tokens
        cost_per_1k_output = 0.0015  # $0.0015 per 1K output tokens
        
        total_metrics = summary.get("total_metrics", {})
        input_cost = (total_metrics.get("input_tokens", 0) / 1000) * cost_per_1k_input
        output_cost = (total_metrics.get("output_tokens", 0) / 1000) * cost_per_1k_output
        total_cost = input_cost + output_cost
        
        return {
            "summary": summary,
            "recent_interactions": recent,
            "cost_estimate": {
                "input_cost": f"${input_cost:.4f}",
                "output_cost": f"${output_cost:.4f}",
                "total_cost": f"${total_cost:.4f}",
                "note": "Cost estimates based on example rates"
            }
        }
    
    def display_token_usage(self):
        """Display token usage in a formatted table."""
        if not _token_collector:
            print("Token tracking not available")
            return
        
        summary = _token_collector.get_session_summary()
        
        print("\n" + "="*50)
        print("TOKEN USAGE SUMMARY")
        print("="*50)
        
        total_metrics = summary.get("total_metrics", {})
        print(f"\nTotal Interactions: {summary.get('total_interactions', 0)}")
        print(f"Total Tokens: {total_metrics.get('total_tokens', 0):,}")
        print(f"  - Input Tokens: {total_metrics.get('input_tokens', 0):,}")
        print(f"  - Output Tokens: {total_metrics.get('output_tokens', 0):,}")
        print(f"  - Cached Tokens: {total_metrics.get('cached_tokens', 0):,}")
        print(f"  - Reasoning Tokens: {total_metrics.get('reasoning_tokens', 0):,}")
        
        # By model
        by_model = summary.get("by_model", {})
        if by_model:
            print("\nUsage by Model:")
            for model, metrics in by_model.items():
                print(f"  {model}: {metrics.get('total_tokens', 0):,} tokens")
        
        # By agent
        by_agent = summary.get("by_agent", {})
        if by_agent:
            print("\nUsage by Agent:")
            for agent, metrics in by_agent.items():
                print(f"  {agent}: {metrics.get('total_tokens', 0):,} tokens")
        
        print("="*50 + "\n")
        
    def launch(self, path: str = '/agents', port: int = 8000, host: str = '0.0.0.0', debug: bool = False, protocol: str = "http"):
        """
        Launch all agents as a single API endpoint (HTTP) or an MCP server. 
        In HTTP mode, the endpoint accepts a query and processes it through all agents in sequence.
        In MCP mode, an MCP server is started, exposing a tool to run the agent workflow.
        
        Args:
            path: API endpoint path (default: '/agents') for HTTP, or base path for MCP.
            port: Server port (default: 8000)
            host: Server host (default: '0.0.0.0')
            debug: Enable debug mode for uvicorn (default: False)
            protocol: "http" to launch as FastAPI, "mcp" to launch as MCP server.
            
        Returns:
            None
        """
        if protocol == "http":
            global _agents_server_started, _agents_registered_endpoints, _agents_shared_apps
            
            if not self.agents:
                logging.warning("No agents to launch for HTTP mode. Add agents to the Agents instance first.")
                return
                
            # Try to import FastAPI dependencies - lazy loading
            try:
                import uvicorn
                from fastapi import FastAPI, HTTPException, Request
                from fastapi.responses import JSONResponse
                from pydantic import BaseModel
                import threading
                import time
                import asyncio # Ensure asyncio is imported for HTTP mode too
                
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
            if port not in _agents_registered_endpoints:
                _agents_registered_endpoints[port] = {}
                
            # Initialize shared FastAPI app if not already created for this port
            if _agents_shared_apps.get(port) is None:
                _agents_shared_apps[port] = FastAPI(
                    title=f"PraisonAI Agents API (Port {port})",
                    description="API for interacting with multiple PraisonAI Agents"
                )
                
                # Add a root endpoint with a welcome message
                @_agents_shared_apps[port].get("/")
                async def root():
                    return {
                        "message": f"Welcome to PraisonAI Agents API on port {port}. See /docs for usage.",
                        "endpoints": list(_agents_registered_endpoints[port].keys())
                    }
                
                # Add healthcheck endpoint
                @_agents_shared_apps[port].get("/health")
                async def healthcheck():
                    return {
                        "status": "ok", 
                        "endpoints": list(_agents_registered_endpoints[port].keys())
                    }
            
            # Normalize path to ensure it starts with /
            if not path.startswith('/'):
                path = f'/{path}'
                
            # Check if path is already registered for this port
            if path in _agents_registered_endpoints[port]:
                logging.warning(f"Path '{path}' is already registered on port {port}. Please use a different path.")
                print(f"⚠️ Warning: Path '{path}' is already registered on port {port}.")
                # Use a modified path to avoid conflicts
                original_path = path
                instance_id = str(uuid.uuid4())[:6]
                path = f"{path}_{instance_id}"
                logging.warning(f"Using '{path}' instead of '{original_path}'")
                print(f"🔄 Using '{path}' instead")
            
            # Generate a unique ID for this agent group's endpoint
            endpoint_id = str(uuid.uuid4())
            _agents_registered_endpoints[port][path] = endpoint_id
            
            # Define the endpoint handler
            @_agents_shared_apps[port].post(path)
            async def handle_query(request: Request, query_data: Optional[AgentQuery] = None):
                # Handle both direct JSON with query field and form data
                if query_data is None:
                    try:
                        request_data = await request.json()
                        if "query" not in request_data:
                            raise HTTPException(status_code=400, detail="Missing 'query' field in request")
                        query = request_data["query"]
                    except Exception:
                        # Fallback to form data or query params
                        form_data = await request.form()
                        if "query" in form_data:
                            query = form_data["query"]
                        else:
                            raise HTTPException(status_code=400, detail="Missing 'query' field in request")
                else:
                    query = query_data.query
                
                try:
                    # Process the query sequentially through all agents
                    current_input = query
                    results = []
                    
                    for agent_instance in self.agents: # Corrected variable name to agent_instance
                        try:
                            # Use async version if available, otherwise use sync version
                            if asyncio.iscoroutinefunction(agent_instance.chat):
                                response = await agent_instance.achat(current_input, task_name=None, task_description=None, task_id=None)
                            else:
                                # Run sync function in a thread to avoid blocking
                                # Use copy_context_to_callable to propagate contextvars (needed for trace emission)
                                from ..trace.context_events import copy_context_to_callable
                                loop = asyncio.get_running_loop()
                                # Correctly pass current_input to the lambda for closure
                                response = await loop.run_in_executor(None, copy_context_to_callable(lambda ci=current_input: agent_instance.chat(ci)))
                            
                            # Store this agent's result
                            results.append({
                                "agent": agent_instance.display_name,
                                "response": response
                            })
                            
                            # Use this response as input to the next agent
                            current_input = response
                        except Exception as e:
                            logging.error(f"Error with agent {agent_instance.display_name}: {str(e)}", exc_info=True)
                            results.append({
                                "agent": agent_instance.display_name,
                                "error": str(e)
                            })
                            # Decide error handling: continue with original input, last good input, or stop? 
                            # For now, let's continue with the last successful 'current_input' or original 'query' if first agent fails
                            # This part might need refinement based on desired behavior.
                            # If an agent fails, its 'response' might be None or an error string.
                            # current_input will carry that forward. Or, we could choose to halt or use last good input.
                    
                    # Return all results and the final output
                    return {
                        "query": query,
                        "results": results,
                        "final_response": current_input
                    }
                except Exception as e:
                    logging.error(f"Error processing query: {str(e)}", exc_info=True)
                    return JSONResponse(
                        status_code=500,
                        content={"error": f"Error processing query: {str(e)}"}
                    )
            
            print(f"🚀 Multi-Agent HTTP API available at http://{host}:{port}{path}")
            agent_names = ", ".join([agent.display_name for agent in self.agents])
            print(f"📊 Available agents for this endpoint ({len(self.agents)}): {agent_names}")
            
            # Create per-agent endpoints for individual agent access
            # This allows n8n and other tools to call specific agents
            agents_dict = {agent.display_name.lower().replace(' ', '_'): agent for agent in self.agents}
            
            # Add GET endpoint to list available agents
            @_agents_shared_apps[port].get(f"{path}/list")
            async def list_agents():
                return {
                    "agents": [
                        {"name": agent.display_name, "id": agent.display_name.lower().replace(' ', '_')}
                        for agent in self.agents
                    ]
                }
            
            # Add per-agent POST endpoints
            for agent_id, agent_instance in agents_dict.items():
                agent_path = f"{path}/{agent_id}"
                
                # Create a closure to capture the agent instance
                def create_agent_handler(agent):
                    async def handle_single_agent(request: Request):
                        try:
                            request_data = await request.json()
                            query = request_data.get("query", "")
                            if not query:
                                raise HTTPException(status_code=400, detail="Missing 'query' field")
                        except Exception:
                            raise HTTPException(status_code=400, detail="Invalid JSON body")
                        
                        try:
                            if asyncio.iscoroutinefunction(agent.chat):
                                response = await agent.achat(query)
                            else:
                                # Use copy_context_to_callable to propagate contextvars (needed for trace emission)
                                from ..trace.context_events import copy_context_to_callable
                                loop = asyncio.get_running_loop()
                                response = await loop.run_in_executor(None, copy_context_to_callable(lambda q=query: agent.chat(q)))
                            
                            return {
                                "agent": agent.display_name,
                                "query": query,
                                "response": response
                            }
                        except Exception as e:
                            logging.error(f"Error with agent {agent.display_name}: {str(e)}", exc_info=True)
                            return JSONResponse(
                                status_code=500,
                                content={"error": f"Agent error: {str(e)}"}
                            )
                    return handle_single_agent
                
                # Register the endpoint
                _agents_shared_apps[port].post(agent_path)(create_agent_handler(agent_instance))
                _agents_registered_endpoints[port][agent_path] = f"{endpoint_id}_{agent_id}"
            
            print(f"🔗 Per-agent endpoints: {', '.join([f'{path}/{aid}' for aid in agents_dict.keys()])}")
            
            # Start the server if it's not already running for this port
            if not _agents_server_started.get(port, False):
                # Mark the server as started first to prevent duplicate starts
                _agents_server_started[port] = True
                
                # Start the server in a separate thread
                def run_server():
                    try:
                        print(f"✅ FastAPI server started at http://{host}:{port}")
                        print(f"📚 API documentation available at http://{host}:{port}/docs")
                        print(f"🔌 Registered HTTP endpoints on port {port}: {', '.join(list(_agents_registered_endpoints[port].keys()))}")
                        uvicorn.run(_agents_shared_apps[port], host=host, port=port, log_level="debug" if debug else "info")
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
                print(f"🔌 Registered HTTP endpoints on port {port}: {', '.join(list(_agents_registered_endpoints[port].keys()))}")
            
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
                    for line_content in lines[caller_line:]: # Renamed variable
                        if '.launch(' in line_content and not line_content.strip().startswith('#'):
                            has_more_launches = True
                            break
                    
                    # If this is the last launch call, block the main thread
                    if not has_more_launches:
                        try:
                            print("\nAll agent groups registered for HTTP mode. Press Ctrl+C to stop the servers.")
                            while True:
                                time.sleep(1)
                        except KeyboardInterrupt:
                            print("\nServers stopped")
                except Exception as e:
                    # If something goes wrong with detection, block anyway to be safe
                    logging.error(f"Error in HTTP launch detection: {e}")
                    try:
                        print("\nKeeping HTTP servers alive. Press Ctrl+C to stop.")
                        while True:
                            time.sleep(1)
                    except KeyboardInterrupt:
                        print("\nServers stopped")
            return None

        elif protocol == "mcp":
            if not self.agents:
                logging.warning("No agents to launch for MCP mode. Add agents to the Agents instance first.")
                return

            try:
                import uvicorn
                from mcp.server.fastmcp import FastMCP
                from mcp.server.sse import SseServerTransport
                from starlette.applications import Starlette
                from starlette.requests import Request
                from starlette.routing import Mount, Route
                # from mcp.server import Server as MCPServer # Not directly needed if using FastMCP's server
                import threading
                import time
                import inspect
                import asyncio
                # logging is already imported at the module level
                
            except ImportError as e:
                missing_module = str(e).split("No module named '")[-1].rstrip("'")
                display_error(f"Missing dependency: {missing_module}. Required for launch() method with MCP mode.")
                logging.error(f"Missing dependency: {missing_module}. Required for launch() method with MCP mode.")
                print(f"\nTo add MCP capabilities, install the required dependencies:")
                print(f"pip install {missing_module} mcp praison-mcp starlette uvicorn")
                print("\nOr install all MCP dependencies with relevant packages.")
                return None

            mcp_instance = FastMCP("praisonai_workflow_mcp_server")

            # Determine the MCP tool name for the workflow based on self.name
            actual_mcp_tool_name = (f"execute_{self.name.lower().replace(' ', '_').replace('-', '_')}_workflow" if self.name 
                                    else "execute_workflow")

            @mcp_instance.tool(name=actual_mcp_tool_name)
            async def execute_workflow_tool(query: str) -> str: # Renamed for clarity
                """Executes the defined agent workflow with the given query."""
                logging.info(f"MCP tool '{actual_mcp_tool_name}' called with query: {query}")
                current_input = query
                final_response = "No agents in workflow or workflow did not produce a final response."

                for agent_instance in self.agents:
                    try:
                        logging.debug(f"Processing with agent: {agent_instance.display_name}")
                        if hasattr(agent_instance, 'achat') and asyncio.iscoroutinefunction(agent_instance.achat):
                            response = await agent_instance.achat(current_input, tools=agent_instance.tools, task_name=None, task_description=None, task_id=None)
                        elif hasattr(agent_instance, 'chat'): # Fallback to sync chat if achat not suitable
                            # Use copy_context_to_callable to propagate contextvars (needed for trace emission)
                            from ..trace.context_events import copy_context_to_callable
                            loop = asyncio.get_running_loop()
                            response = await loop.run_in_executor(None, copy_context_to_callable(lambda ci=current_input: agent_instance.chat(ci, tools=agent_instance.tools)))
                        else:
                            logging.warning(f"Agent {agent_instance.display_name} has no suitable chat or achat method.")
                            response = f"Error: Agent {agent_instance.display_name} has no callable chat method."
                        
                        current_input = response if response is not None else "Agent returned no response."
                        final_response = current_input # Keep track of the last valid response
                        logging.debug(f"Agent {agent_instance.display_name} responded. Current intermediate output: {current_input}")

                    except Exception as e:
                        logging.error(f"Error during agent {agent_instance.display_name} execution in MCP workflow: {str(e)}", exc_info=True)
                        current_input = f"Error from agent {agent_instance.display_name}: {str(e)}"
                        final_response = current_input # Update final response to show error
                        # Optionally break or continue based on desired error handling for the workflow
                        # For now, we continue, and the error is passed to the next agent or returned.
                
                logging.info(f"MCP tool '{actual_mcp_tool_name}' completed. Final response: {final_response}")
                return final_response

            base_mcp_path = path.rstrip('/')
            sse_mcp_path = f"{base_mcp_path}/sse"
            messages_mcp_path_prefix = f"{base_mcp_path}/messages"
            if not messages_mcp_path_prefix.endswith('/'):
                messages_mcp_path_prefix += '/'

            sse_transport_mcp = SseServerTransport(messages_mcp_path_prefix)

            async def handle_mcp_sse_connection(request: Request) -> None:
                logging.debug(f"MCP SSE connection request from {request.client} for path {request.url.path}")
                async with sse_transport_mcp.connect_sse(
                        request.scope, request.receive, request._send,
                ) as (read_stream, write_stream):
                    await mcp_instance._mcp_server.run(
                        read_stream, write_stream, mcp_instance._mcp_server.create_initialization_options(),
                    )
            
            starlette_mcp_app = Starlette(
                debug=debug,
                routes=[
                    Route(sse_mcp_path, endpoint=handle_mcp_sse_connection),
                    Mount(messages_mcp_path_prefix, app=sse_transport_mcp.handle_post_message),
                ],
            )

            print(f"🚀 Agents MCP Workflow server starting on http://{host}:{port}")
            print(f"📡 MCP SSE endpoint available at {sse_mcp_path}")
            print(f"📢 MCP messages post to {messages_mcp_path_prefix}")
            # Instead of trying to extract tool names, hardcode the known tool name
            mcp_tool_names = [actual_mcp_tool_name]  # Use the determined dynamic tool name
            print(f"🛠️ Available MCP tools: {', '.join(mcp_tool_names)}")
            agent_names_in_workflow = ", ".join([a.display_name for a in self.agents])
            print(f"🔄 Agents in MCP workflow: {agent_names_in_workflow}")

            def run_praison_mcp_server():
                try:
                    uvicorn.run(starlette_mcp_app, host=host, port=port, log_level="debug" if debug else "info")
                except Exception as e:
                    logging.error(f"Error starting Agents MCP server: {str(e)}", exc_info=True)
                    print(f"❌ Error starting Agents MCP server: {str(e)}")

            mcp_server_thread = threading.Thread(target=run_praison_mcp_server, daemon=True)
            mcp_server_thread.start()
            time.sleep(0.5) 

            import inspect 
            stack = inspect.stack()
            if len(stack) > 1 and stack[1].filename.endswith('.py'):
                caller_frame = stack[1]
                caller_line = caller_frame.lineno
                try:
                    with open(caller_frame.filename, 'r') as f:
                        lines = f.readlines()
                    has_more_launches = False
                    for line_content in lines[caller_line:]:
                        if '.launch(' in line_content and not line_content.strip().startswith('#'):
                            has_more_launches = True
                            break
                    if not has_more_launches:
                        try:
                            print("\nAgents MCP server running. Press Ctrl+C to stop.")
                            while True:
                                time.sleep(1)
                        except KeyboardInterrupt:
                            print("\nAgents MCP Server stopped")
                except Exception as e:
                    logging.error(f"Error in Agents MCP launch detection: {e}")
                    try:
                        print("\nKeeping Agents MCP server alive. Press Ctrl+C to stop.")
                        while True:
                            time.sleep(1)
                    except KeyboardInterrupt:
                        print("\nAgents MCP Server stopped")
            return None
        else:
            display_error(f"Invalid protocol: {protocol}. Choose 'http' or 'mcp'.")
            return None

    # =========================================================================
    # Planning Mode Properties and Methods
    # =========================================================================
    
    @property
    def current_plan(self):
        """Get the current plan."""
        return self._current_plan
    
    @property
    def todo_list(self):
        """Get the current todo list."""
        return self._todo_list
    
    def _create_agent_from_config(self, agent_config: dict) -> 'Agent':
        """
        Create an Agent from a configuration dictionary.
        
        Args:
            agent_config: Dict with keys like 'name', 'role', 'goal', 'backstory', 'llm', 'tools'
            
        Returns:
            Agent instance
        """
        from ..agent.agent import Agent
        
        return Agent(
            name=agent_config.get('name', 'TaskAgent'),
            role=agent_config.get('role'),
            goal=agent_config.get('goal'),
            backstory=agent_config.get('backstory'),
            llm=agent_config.get('llm'),
            tools=agent_config.get('tools'),
            verbose=self.verbose >= 1,
            memory=self.memory
        )
    
    def _get_planning_agent(self):
        """Lazy load PlanningAgent."""
        if self._planning_agent is None and self.planning:
            from ..planning import PlanningAgent
            self._planning_agent = PlanningAgent(
                llm=self.planning_llm,
                read_only=True,
                verbose=self.verbose,
                tools=self.planning_tools,
                reasoning=self.planning_reasoning
            )
        return self._planning_agent
    
    async def _create_plan(self, request: str = None, context: str = None):
        """
        Create an implementation plan.
        
        Args:
            request: The request/goal to plan for
            context: Optional additional context
            
        Returns:
            Plan instance
        """
        planner = self._get_planning_agent()
        if planner is None:
            return None
            
        # Use first task description as request if not provided
        if request is None and self.tasks:
            first_task = list(self.tasks.values())[0]
            request = first_task.description
            
        plan = await planner.create_plan(
            request=request,
            agents=self.agents,
            tasks=list(self.tasks.values()),
            context=context
        )
        
        self._current_plan = plan
        
        # Create todo list from plan
        from ..planning import TodoList
        self._todo_list = TodoList.from_plan(plan)
        
        return plan
    
    def _create_plan_sync(self, request: str = None, context: str = None):
        """
        Synchronous version of _create_plan.
        
        Args:
            request: The request/goal to plan for
            context: Optional additional context
            
        Returns:
            Plan instance
        """
        planner = self._get_planning_agent()
        if planner is None:
            return None
            
        # Use first task description as request if not provided
        if request is None and self.tasks:
            first_task = list(self.tasks.values())[0]
            request = first_task.description
            
        plan = planner.create_plan_sync(
            request=request,
            agents=self.agents,
            tasks=list(self.tasks.values()),
            context=context
        )
        
        self._current_plan = plan
        
        # Create todo list from plan
        from ..planning import TodoList
        self._todo_list = TodoList.from_plan(plan)
        
        return plan
    
    async def _request_approval(self, plan):
        """
        Request approval for a plan.
        
        Args:
            plan: Plan to approve
            
        Returns:
            True if approved, False if rejected
        """
        if self.auto_approve_plan:
            plan.approve()
            return True
            
        from ..planning import ApprovalCallback
        callback = ApprovalCallback(auto_approve=self.auto_approve_plan)
        return await callback.async_call(plan)
    
    def _request_approval_sync(self, plan):
        """
        Synchronous version of _request_approval.
        
        Args:
            plan: Plan to approve
            
        Returns:
            True if approved, False if rejected
        """
        if self.auto_approve_plan:
            plan.approve()
            return True
            
        from ..planning import ApprovalCallback
        callback = ApprovalCallback(auto_approve=self.auto_approve_plan)
        return callback(plan)
    
    def get_plan_markdown(self) -> str:
        """
        Get the current plan as markdown.
        
        Returns:
            Markdown string or empty string if no plan
        """
        if self._current_plan:
            return self._current_plan.to_markdown()
        return ""
    
    def get_todo_markdown(self) -> str:
        """
        Get the current todo list as markdown.
        
        Returns:
            Markdown string or empty string if no todo list
        """
        if self._todo_list:
            return self._todo_list.to_markdown()
        return ""
    
    def update_plan_step_status(self, step_id: str, status: str) -> bool:
        """
        Update the status of a plan step.
        
        Args:
            step_id: ID of the step to update
            status: New status
            
        Returns:
            True if updated, False if not found
        """
        if self._current_plan:
            result = self._current_plan.update_step_status(step_id, status)
            # Sync todo list
            if self._todo_list:
                self._todo_list.sync_with_plan(self._current_plan)
            return result
        return False
    
    def _run_with_planning(self):
        """
        Run tasks with planning mode enabled.
        
        This method:
        1. Creates a plan using PlanningAgent
        2. Generates a todo list from the plan
        3. Creates proper Task objects from plan steps
        4. Executes each task using the full Task execution system
           (with memory, callbacks, guardrails, structured output, etc.)
        5. Tracks progress as items are completed
        """
        from rich.console import Console
        from rich.panel import Panel
        from rich.markdown import Markdown
        from ..task import Task
        
        console = Console()
        
        # Step 1: Create the plan
        console.print("\n[bold blue]📋 PLANNING PHASE[/bold blue]")
        console.print("[dim]Creating implementation plan...[/dim]\n")
        
        # Build request from tasks
        task_descriptions = [task.description for task in self.tasks.values()]
        request = " AND ".join(task_descriptions)
        
        plan = self._create_plan_sync(request=request)
        
        if not plan:
            console.print("[yellow]⚠️ Planning failed, falling back to normal execution[/yellow]")
            self.run_all_tasks()
            return
        
        # Display the plan
        console.print(Panel(
            Markdown(plan.to_markdown()),
            title="[bold green]Generated Plan[/bold green]",
            border_style="green"
        ))
        
        # Step 2: Request approval if not auto-approve
        if not self.auto_approve_plan:
            approved = self._request_approval_sync(plan)
            if not approved:
                console.print("[red]❌ Plan rejected. Aborting execution.[/red]")
                return
        else:
            plan.approve()
            console.print("[green]✅ Plan auto-approved[/green]")
        
        # Step 3: Create todo list for tracking
        from ..planning import TodoList
        self._todo_list = TodoList.from_plan(plan)
        
        console.print("\n[bold blue]📝 TODO LIST[/bold blue]")
        console.print(Panel(
            Markdown(self._todo_list.to_markdown()),
            title="[bold cyan]Tasks to Complete[/bold cyan]",
            border_style="cyan"
        ))
        
        # Step 4: Create proper Task objects from plan steps
        console.print("\n[bold blue]🚀 EXECUTION PHASE[/bold blue]\n")
        
        # Map agent names to agent instances
        agent_map = {agent.display_name: agent for agent in self.agents}
        
        # Store original tasks and create new tasks from plan
        original_tasks = self.tasks.copy()
        self.tasks = {}
        self.task_id_counter = 0
        
        # Create Task objects from plan steps
        plan_tasks = []
        step_to_task = {}  # Map step_id to task for context chaining
        
        for i, step in enumerate(plan.steps):
            # Get the appropriate agent
            agent = agent_map.get(step.agent, self.agents[0] if self.agents else None)
            
            if not agent:
                console.print(f"[yellow]⚠️ No agent found for '{step.agent}', using first available[/yellow]")
                agent = self.agents[0] if self.agents else None
            
            if not agent:
                console.print(f"[red]❌ No agents available for step: {step.description}[/red]")
                continue
            
            # Build context from dependencies (previous task results)
            context = []
            for dep_id in step.dependencies:
                # Convert step_X format to actual step index
                if dep_id.startswith("step_"):
                    try:
                        dep_index = int(dep_id.split("_")[1])
                        if dep_index < len(plan_tasks):
                            context.append(plan_tasks[dep_index])
                    except (ValueError, IndexError):
                        pass
                elif dep_id in step_to_task:
                    context.append(step_to_task[dep_id])
            
            # Find matching original task for additional config (memory, callbacks, etc.)
            original_task = None
            for orig_task in original_tasks.values():
                if orig_task.agent and orig_task.agent.display_name == agent.display_name:
                    original_task = orig_task
                    break
            
            # Create Task with full features from original task if available
            task = Task(
                description=step.description,
                expected_output=f"Complete: {step.description}",
                agent=agent,
                name=f"Plan Step {i + 1}",
                tools=agent.tools if agent.tools else [],
                context=context if context else None,
                # Inherit from original task if available
                memory=original_task.memory if original_task else None,
                callback=original_task.callback if original_task else None,
                guardrails=original_task.guardrail if original_task else None,
                max_retries=original_task.max_retries if original_task else 3,
                output_json=original_task.output_json if original_task else None,
                output_pydantic=original_task.output_pydantic if original_task else None,
                config=original_task.config if original_task else {}
            )
            
            # Add task to our task list
            task_id = self.add_task(task)
            plan_tasks.append(task)
            step_to_task[step.id] = task
        
        # Step 5: Execute tasks using the proper Task execution system
        for i, (task_id, task) in enumerate(self.tasks.items()):
            # Update todo list progress
            if i < len(self._todo_list.items):
                item = self._todo_list.items[i]
                
                # Display progress bar
                progress = self._todo_list.progress
                bar_length = 30
                filled = int(bar_length * progress)
                bar = "█" * filled + "░" * (bar_length - filled)
                console.print(f"[dim]Progress: [{bar}] {progress * 100:.0f}%[/dim]")
                
                console.print(f"\n[bold]📌 Step {i + 1}/{len(self.tasks)}:[/bold] {task.description[:60]}...")
                console.print(f"[dim]   Agent: {task.agent.display_name if task.agent else 'Unknown'}[/dim]")
                
                # Mark as in progress
                self._todo_list.start(item.id)
            
            # Execute using the full Task execution system
            # This includes: memory, callbacks, guardrails, structured output, retry logic
            try:
                self.run_task(task_id)
                
                if task.status == "completed":
                    if i < len(self._todo_list.items):
                        self._todo_list.complete(self._todo_list.items[i].id)
                    console.print("[green]   ✅ Completed[/green]")
                else:
                    console.print(f"[yellow]   ⚠️ Task status: {task.status}[/yellow]")
            except Exception as e:
                console.print(f"[red]   ❌ Error: {e}[/red]")
                logger.error(f"Error executing plan task {task_id}: {e}")
        
        # Final progress
        completed_count = len([t for t in self.tasks.values() if t.status == "completed"])
        console.print(f"\n[bold green]🎉 EXECUTION COMPLETE[/bold green]")
        console.print(f"[dim]Progress: [{'█' * 30}] 100%[/dim]")
        console.print(f"[green]Completed {completed_count}/{len(self.tasks)} tasks![/green]\n")
        
        # Restore original tasks reference for result retrieval
        self._plan_tasks = self.tasks.copy()
        # Keep plan tasks for results but note original tasks are preserved in _plan_tasks


# Backward compatibility aliases
# Agents is deprecated in favor of AgentManager (v0.14.16+)
Agents = AgentManager
PraisonAIAgents = AgentManager
