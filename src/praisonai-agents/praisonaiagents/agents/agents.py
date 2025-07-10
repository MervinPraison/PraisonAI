import os
import time
import json
import logging
from typing import Any, Dict, Optional, List
from pydantic import BaseModel
from rich.text import Text
from rich.panel import Panel
from rich.console import Console
from ..main import display_error, TaskOutput, error_logs
from ..agent.agent import Agent
from ..task.task import Task
from ..process.process import Process, LoopItems
import asyncio
import uuid
from enum import Enum

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
            return f"Result of previous task {task_name}:\n{context_item.result.raw}"
        elif task_status == TaskStatus.COMPLETED.value and not context_item.result:
            return f"Previous task {task_name} completed but produced no result."
        else:
            return f"Previous task {task_name} is not yet completed (status: {task_status or TaskStatus.UNKNOWN.value})."
    elif isinstance(context_item, dict) and "vector_store" in context_item:
        from ..knowledge.knowledge import Knowledge
        try:
            # Handle both string and dict configs
            cfg = context_item["vector_store"]
            if isinstance(cfg, str):
                cfg = json.loads(cfg)
            
            knowledge = Knowledge(config={"vector_store": cfg}, verbose=verbose)
            
            # Only use user_id as filter
            db_results = knowledge.search(
                context_item.get("query", ""),  # Use query from context if available
                user_id=user_id if user_id else None
            )
            return f"[DB Context]: {str(db_results)}"
        except Exception as e:
            return f"[Vector DB Error]: {e}"
    else:
        return str(context_item)  # Fallback for unknown types

class PraisonAIAgents:
    def __init__(self, agents, tasks=None, verbose=0, completion_checker=None, max_retries=5, process="sequential", manager_llm=None, memory=False, memory_config=None, embedder=None, user_id=None, max_iter=10, stream=True, name: Optional[str] = None):
        # Add check at the start if memory is requested
        if memory:
            try:
                from ..memory.memory import Memory
                MEMORY_AVAILABLE = True
            except ImportError:
                raise ImportError(
                    "Memory features requested but memory dependencies not installed. "
                    "Please install with: pip install \"praisonaiagents[memory]\""
                )

        if not agents:
            raise ValueError("At least one agent must be provided")
        
        self.run_id = str(uuid.uuid4())  # Auto-generate run_id
        self.user_id = user_id or "praison"  # Optional user_id
        self.max_iter = max_iter  # Add max_iter parameter

        # Pass user_id to each agent
        for agent in agents:
            agent.user_id = self.user_id

        self.agents: List[Agent] = agents
        self.tasks: Dict[int, Task] = {}
        if max_retries < 3:
            max_retries = 3
        self.completion_checker = completion_checker if completion_checker else self.default_completion_checker
        self.task_id_counter = 0
        self.verbose = verbose
        self.max_retries = max_retries
        self.process = process
        self.stream = stream
        self.name = name  # Store the name for the Agents collection
        
        # Check for manager_llm in environment variable if not provided
        self.manager_llm = manager_llm or os.getenv('OPENAI_MODEL_NAME', 'gpt-4o')
        
        # Set logger level based on verbose
        if verbose >= 5:
            logger.setLevel(logging.INFO)
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
            # Validate tasks for backward compatibility
            if not tasks:
                raise ValueError("If tasks are provided, at least one task must be present")
            logger.info(f"Using {len(tasks)} provided tasks")
        
        # Add tasks and set their status
        for task in tasks:
            self.add_task(task)
            task.status = "not started"
            
        # If tasks were auto-generated from agents or process is sequential, set up sequential flow
        if len(tasks) > 1 and (process == "sequential" or all(task.next_tasks == [] for task in tasks)):
            for i in range(len(tasks) - 1):
                # Set up next task relationship
                tasks[i].next_tasks = [tasks[i + 1].name]
                # Set up context for the next task to include the current task
                if tasks[i + 1].context is None:
                    tasks[i + 1].context = []
                tasks[i + 1].context.append(tasks[i])
            logger.info("Set up sequential flow with automatic context passing")
        
        self._state = {}  # Add state storage at PraisonAIAgents level
        
        # Initialize memory system
        self.shared_memory = None
        if memory:
            try:
                from ..memory.memory import Memory
                
                # Get memory config from parameter or first task
                mem_cfg = memory_config
                if not mem_cfg:
                    mem_cfg = next((t.config.get('memory_config') for t in tasks if hasattr(t, 'config') and t.config), None)
                # Set default memory config if none provided
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
                # Add embedder config if provided
                if embedder:
                    if isinstance(embedder, dict):
                        mem_cfg = mem_cfg or {}
                        mem_cfg["embedder"] = embedder
                    else:
                        # Handle direct embedder function
                        mem_cfg = mem_cfg or {}
                        mem_cfg["embedder_function"] = embedder

                if mem_cfg:
                    # Pass verbose level to Memory
                    self.shared_memory = Memory(config=mem_cfg, verbose=verbose)
                    if verbose >= 5:
                        logger.info("Initialized shared memory for PraisonAIAgents")
                    # Distribute memory to tasks
                    for task in tasks:
                        if not task.memory:
                            task.memory = self.shared_memory
                            if verbose >= 5:
                                logger.info(f"Assigned shared memory to task {task.id}")
            except Exception as e:
                logger.error(f"Failed to initialize shared memory: {e}")
        # Update tasks with shared memory
        if self.shared_memory:
            for task in tasks:
                if not task.memory:
                    task.memory = self.shared_memory
                    logger.info(f"Assigned shared memory to task {task.id}")

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
                import cv2
                import base64
                from moviepy import VideoFileClip
            except ImportError as e:
                display_error(f"Error: Missing required dependencies for image/video processing: {e}")
                display_error("Please install with: pip install opencv-python moviepy")
                task.status = "failed"
                return None

        if task.status == "not started":
            task.status = "in progress"

        executor_agent = task.agent

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
                    logger.info(f"Context {i+1}: {ctx[:100]}...")
            context_separator = '\n\n'
            task_prompt += f"""
Context:

{context_separator.join(unique_contexts)}
"""
        task_prompt += "Please provide only the final result of your work. Do not add any conversation or extra explanation."

        if self.verbose >= 2:
            logger.info(f"Executing task {task_id}: {task.description} using {executor_agent.name}")
        logger.debug(f"Starting execution of task {task_id} with prompt:\n{task_prompt}")

        if task.images:
            def _get_multimodal_message(text_prompt, images):
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

            agent_output = await executor_agent.achat(
                _get_multimodal_message(task_prompt, task.images),
                tools=tools,
                output_json=task.output_json,
                output_pydantic=task.output_pydantic
            )
        else:
            agent_output = await executor_agent.achat(
                task_prompt,
                tools=tools,
                output_json=task.output_json,
                output_pydantic=task.output_pydantic
            )

        if agent_output:
            task_output = TaskOutput(
                description=task.description,
                summary=task.description[:10],
                raw=agent_output,
                agent=executor_agent.name,
                output_format="RAW"
            )

            if task.output_json:
                cleaned = self.clean_json_output(agent_output)
                try:
                    parsed = json.loads(cleaned)
                    task_output.json_dict = parsed
                    task_output.output_format = "JSON"
                except:
                    logger.warning(f"Warning: Could not parse output of task {task_id} as JSON")
                    logger.debug(f"Output that failed JSON parsing: {agent_output}")

            if task.output_pydantic:
                cleaned = self.clean_json_output(agent_output)
                try:
                    parsed = json.loads(cleaned)
                    pyd_obj = task.output_pydantic(**parsed)
                    task_output.pydantic = pyd_obj
                    task_output.output_format = "Pydantic"
                except:
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
            # Collect all tasks that should run in parallel
            parallel_tasks = []
            async for task_id in process.aworkflow():
                if self.tasks[task_id].async_execution and self.tasks[task_id].is_start:
                    parallel_tasks.append(task_id)
                elif parallel_tasks:
                    # Execute collected parallel tasks
                    await asyncio.gather(*[self.arun_task(t) for t in parallel_tasks])
                    parallel_tasks = []
                    # Run the current non-parallel task
                    if self.tasks[task_id].async_execution:
                        await self.arun_task(task_id)
                    else:
                        self.run_task(task_id)
            
            # Execute any remaining parallel tasks
            if parallel_tasks:
                await asyncio.gather(*[self.arun_task(t) for t in parallel_tasks])
                
        elif self.process == "sequential":
            async for task_id in process.asequential():
                if self.tasks[task_id].async_execution:
                    await self.arun_task(task_id)
                else:
                    self.run_task(task_id)
        elif self.process == "hierarchical":
            async for task_id in process.ahierarchical():
                if isinstance(task_id, Task):
                    task_id = self.add_task(task_id)
                if self.tasks[task_id].async_execution:
                    await self.arun_task(task_id)
                else:
                    self.run_task(task_id)

    async def astart(self, content=None, return_dict=False, **kwargs):
        """Async version of start method
        
        Args:
            content: Optional content to add to all tasks' context
            return_dict: If True, returns the full results dictionary instead of only the final response
            **kwargs: Additional arguments
        """
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
                import cv2
                import base64
                from moviepy import VideoFileClip
            except ImportError as e:
                display_error(f"Error: Missing required dependencies for image/video processing: {e}")
                display_error("Please install with: pip install opencv-python moviepy")
                task.status = "failed"
                return None

        if task.status == "not started":
            task.status = "in progress"

        executor_agent = task.agent

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
                    logger.info(f"Context {i+1}: {ctx[:100]}...")
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
                    task_prompt += f"\n\nRelevant memory context:\n{memory_context}"
            except Exception as e:
                logger.error(f"Error getting memory context: {e}")

        task_prompt += "Please provide only the final result of your work. Do not add any conversation or extra explanation."

        if self.verbose >= 2:
            logger.info(f"Executing task {task_id}: {task.description} using {executor_agent.name}")
        logger.debug(f"Starting execution of task {task_id} with prompt:\n{task_prompt}")

        if task.images:
            def _get_multimodal_message(text_prompt, images):
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

            agent_output = executor_agent.chat(
                _get_multimodal_message(task_prompt, task.images),
                tools=task.tools,
                output_json=task.output_json,
                output_pydantic=task.output_pydantic
            )
        else:
            agent_output = executor_agent.chat(
                task_prompt,
                tools=task.tools,
                output_json=task.output_json,
                output_pydantic=task.output_pydantic,
                stream=self.stream,
            )

        if agent_output:
            # Store the response in memory
            if task.memory:
                try:
                    task.store_in_memory(
                        content=agent_output,
                        agent_name=executor_agent.name,
                        task_id=task_id
                    )
                except Exception as e:
                    logger.error(f"Failed to store agent output in memory: {e}")

            task_output = TaskOutput(
                description=task.description,
                summary=task.description[:10],
                raw=agent_output,
                agent=executor_agent.name,
                output_format="RAW"
            )

            if task.output_json:
                cleaned = self.clean_json_output(agent_output)
                try:
                    parsed = json.loads(cleaned)
                    task_output.json_dict = parsed
                    task_output.output_format = "JSON"
                except:
                    logger.warning(f"Warning: Could not parse output of task {task_id} as JSON")
                    logger.debug(f"Output that failed JSON parsing: {agent_output}")

            if task.output_pydantic:
                cleaned = self.clean_json_output(agent_output)
                try:
                    parsed = json.loads(cleaned)
                    pyd_obj = task.output_pydantic(**parsed)
                    task_output.pydantic = pyd_obj
                    task_output.output_format = "Pydantic"
                except:
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

    def start(self, content=None, return_dict=False, **kwargs):
        """Start agent execution with optional content and config
        
        Args:
            content: Optional content to add to all tasks' context
            return_dict: If True, returns the full results dictionary instead of only the final response
            **kwargs: Additional arguments
        """
        if content:
            # Add content to context of all tasks
            for task in self.tasks.values():
                if isinstance(content, (str, list)):
                    # If context is empty, initialize it
                    if not task.context:
                        task.context = []
                    # Add content to context
                    task.context.append(content)
                
        # Run tasks as before
        self.run_all_tasks()
        
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
                "agents": [agent.name for agent in self.agents],
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
                    # Process the query sequentially through all agents
                    current_input = query
                    results = []
                    
                    for agent_instance in self.agents: # Corrected variable name to agent_instance
                        try:
                            # Use async version if available, otherwise use sync version
                            if asyncio.iscoroutinefunction(agent_instance.chat):
                                response = await agent_instance.achat(current_input)
                            else:
                                # Run sync function in a thread to avoid blocking
                                loop = asyncio.get_event_loop()
                                # Correctly pass current_input to the lambda for closure
                                response = await loop.run_in_executor(None, lambda ci=current_input: agent_instance.chat(ci))
                            
                            # Store this agent's result
                            results.append({
                                "agent": agent_instance.name,
                                "response": response
                            })
                            
                            # Use this response as input to the next agent
                            current_input = response
                        except Exception as e:
                            logging.error(f"Error with agent {agent_instance.name}: {str(e)}", exc_info=True)
                            results.append({
                                "agent": agent_instance.name,
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
            agent_names = ", ".join([agent.name for agent in self.agents])
            print(f"📊 Available agents for this endpoint ({len(self.agents)}): {agent_names}")
            
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
                        logging.debug(f"Processing with agent: {agent_instance.name}")
                        if hasattr(agent_instance, 'achat') and asyncio.iscoroutinefunction(agent_instance.achat):
                            response = await agent_instance.achat(current_input, tools=agent_instance.tools)
                        elif hasattr(agent_instance, 'chat'): # Fallback to sync chat if achat not suitable
                            loop = asyncio.get_event_loop()
                            response = await loop.run_in_executor(None, lambda ci=current_input: agent_instance.chat(ci, tools=agent_instance.tools))
                        else:
                            logging.warning(f"Agent {agent_instance.name} has no suitable chat or achat method.")
                            response = f"Error: Agent {agent_instance.name} has no callable chat method."
                        
                        current_input = response if response is not None else "Agent returned no response."
                        final_response = current_input # Keep track of the last valid response
                        logging.debug(f"Agent {agent_instance.name} responded. Current intermediate output: {current_input}")

                    except Exception as e:
                        logging.error(f"Error during agent {agent_instance.name} execution in MCP workflow: {str(e)}", exc_info=True)
                        current_input = f"Error from agent {agent_instance.name}: {str(e)}"
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

            print(f"🚀 PraisonAIAgents MCP Workflow server starting on http://{host}:{port}")
            print(f"📡 MCP SSE endpoint available at {sse_mcp_path}")
            print(f"📢 MCP messages post to {messages_mcp_path_prefix}")
            # Instead of trying to extract tool names, hardcode the known tool name
            mcp_tool_names = [actual_mcp_tool_name]  # Use the determined dynamic tool name
            print(f"🛠️ Available MCP tools: {', '.join(mcp_tool_names)}")
            agent_names_in_workflow = ", ".join([a.name for a in self.agents])
            print(f"🔄 Agents in MCP workflow: {agent_names_in_workflow}")

            def run_praison_mcp_server():
                try:
                    uvicorn.run(starlette_mcp_app, host=host, port=port, log_level="debug" if debug else "info")
                except Exception as e:
                    logging.error(f"Error starting PraisonAIAgents MCP server: {str(e)}", exc_info=True)
                    print(f"❌ Error starting PraisonAIAgents MCP server: {str(e)}")

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
                            print("\nPraisonAIAgents MCP server running. Press Ctrl+C to stop.")
                            while True:
                                time.sleep(1)
                        except KeyboardInterrupt:
                            print("\nPraisonAIAgents MCP Server stopped")
                except Exception as e:
                    logging.error(f"Error in PraisonAIAgents MCP launch detection: {e}")
                    try:
                        print("\nKeeping PraisonAIAgents MCP server alive. Press Ctrl+C to stop.")
                        while True:
                            time.sleep(1)
                    except KeyboardInterrupt:
                        print("\nPraisonAIAgents MCP Server stopped")
            return None
        else:
            display_error(f"Invalid protocol: {protocol}. Choose 'http' or 'mcp'.")
            return None 