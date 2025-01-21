import os
import time
import json
import logging
from typing import Any, Dict, Optional, List
from pydantic import BaseModel
from rich.text import Text
from rich.panel import Panel
from rich.console import Console
from ..main import display_error, TaskOutput, error_logs, client
from ..agent.agent import Agent
from ..task.task import Task
from ..process.process import Process, LoopItems
import asyncio
import uuid

# Set up logger
logger = logging.getLogger(__name__)

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

class PraisonAIAgents:
    def __init__(self, agents, tasks=None, verbose=0, completion_checker=None, max_retries=5, process="sequential", manager_llm=None, memory=False, memory_config=None, embedder=None, user_id=None, max_iter=10):
        if not agents:
            raise ValueError("At least one agent must be provided")
        
        self.run_id = str(uuid.uuid4())  # Auto-generate run_id
        self.user_id = user_id or "praison"  # Optional user_id
        self.max_iter = max_iter  # Add max_iter parameter

        # Pass user_id to each agent
        for agent in agents:
            agent.user_id = self.user_id

        self.agents = agents
        self.tasks = {}
        if max_retries < 3:
            max_retries = 3
        self.completion_checker = completion_checker if completion_checker else self.default_completion_checker
        self.task_id_counter = 0
        self.verbose = verbose
        self.max_retries = max_retries
        self.process = process
        
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
                elif isinstance(context_item, dict) and "vector_store" in context_item:
                    from ..knowledge.knowledge import Knowledge
                    try:
                        # Handle both string and dict configs
                        cfg = context_item["vector_store"]
                        if isinstance(cfg, str):
                            cfg = json.loads(cfg)
                        
                        knowledge = Knowledge(config={"vector_store": cfg}, verbose=self.verbose)
                        
                        # Only use user_id as filter
                        db_results = knowledge.search(
                            task.description,
                            user_id=self.user_id if self.user_id else None
                        )
                        context_results.append(f"[DB Context]: {str(db_results)}")
                    except Exception as e:
                        context_results.append(f"[Vector DB Error]: {e}")
            
            # Join unique context results
            unique_contexts = list(dict.fromkeys(context_results))  # Remove duplicates
            task_prompt += f"""
Context:

{'  '.join(unique_contexts)}
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
                        await task.execute_callback(task_output)
                    except Exception as e:
                        logger.error(f"Error executing memory callback for task {task_id}: {e}")
                        logger.exception(e)
                    
                    # Run task callback if exists
                    if task.callback:
                        try:
                            if asyncio.iscoroutinefunction(task.callback):
                                await task.callback(task_output)
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

    async def astart(self, content=None, **kwargs):
        """Async version of start method"""
        if content:
            # Add content to context of all tasks
            for task in self.tasks.values():
                if isinstance(content, (str, list)):
                    if not task.context:
                        task.context = []
                    task.context.append(content)

        await self.arun_all_tasks()
        return {
            "task_status": self.get_all_tasks_status(),
            "task_results": {task_id: self.get_task_result(task_id) for task_id in self.tasks}
        }

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
                elif isinstance(context_item, dict) and "vector_store" in context_item:
                    from ..knowledge.knowledge import Knowledge
                    try:
                        # Handle both string and dict configs
                        cfg = context_item["vector_store"]
                        if isinstance(cfg, str):
                            cfg = json.loads(cfg)
                        
                        knowledge = Knowledge(config={"vector_store": cfg}, verbose=self.verbose)
                        
                        # Only use user_id as filter
                        db_results = knowledge.search(
                            task.description,
                            user_id=self.user_id if self.user_id else None
                        )
                        context_results.append(f"[DB Context]: {str(db_results)}")
                    except Exception as e:
                        context_results.append(f"[Vector DB Error]: {e}")
            
            # Join unique context results
            unique_contexts = list(dict.fromkeys(context_results))  # Remove duplicates
            task_prompt += f"""
Context:

{'  '.join(unique_contexts)}
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
                output_pydantic=task.output_pydantic
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
                        if asyncio.get_event_loop().is_running():
                            asyncio.create_task(task.execute_callback(task_output))
                        else:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            loop.run_until_complete(task.execute_callback(task_output))
                    except Exception as e:
                        logger.error(f"Error executing memory callback for task {task_id}: {e}")
                        logger.exception(e)
                    
                    # Run task callback if exists
                    if task.callback:
                        try:
                            if asyncio.iscoroutinefunction(task.callback):
                                if asyncio.get_event_loop().is_running():
                                    asyncio.create_task(task.callback(task_output))
                                else:
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    loop.run_until_complete(task.callback(task_output))
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

    def start(self, content=None, **kwargs):
        """Start agent execution with optional content and config"""
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
        return {
            "task_status": self.get_all_tasks_status(),
            "task_results": {task_id: self.get_task_result(task_id) for task_id in self.tasks}
        }

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