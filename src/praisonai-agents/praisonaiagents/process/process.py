import logging
import asyncio
import json
from typing import Dict, Optional, List, Any, AsyncGenerator
from pydantic import BaseModel, ConfigDict
from ..agent.agent import Agent
from ..task.task import Task
from ..main import display_error, client
import csv
import os
from openai import AsyncOpenAI

class LoopItems(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    items: List[Any]

class Process:
    DEFAULT_RETRY_LIMIT = 3  # Predefined retry limit in a common place

    def __init__(self, tasks: Dict[str, Task], agents: List[Agent], manager_llm: Optional[str] = None, verbose: bool = False, max_iter: int = 10):
        logging.debug(f"=== Initializing Process ===")
        logging.debug(f"Number of tasks: {len(tasks)}")
        logging.debug(f"Number of agents: {len(agents)}")
        logging.debug(f"Manager LLM: {manager_llm}")
        logging.debug(f"Verbose mode: {verbose}")
        logging.debug(f"Max iterations: {max_iter}")

        self.tasks = tasks
        self.agents = agents
        self.manager_llm = manager_llm
        self.verbose = verbose
        self.max_iter = max_iter
        self.task_retry_counter: Dict[str, int] = {} # Initialize retry counter
        self.workflow_finished = False # ADDED: Workflow finished flag

    def _build_task_context(self, current_task: Task) -> str:
        """Build context for a task based on its retain_full_context setting"""
        if not (current_task.previous_tasks or current_task.context):
            return ""
            
        context = "\nInput data from previous tasks:"
        
        if current_task.retain_full_context:
            # Original behavior: include all previous tasks
            for prev_name in current_task.previous_tasks:
                prev_task = next((t for t in self.tasks.values() if t.name == prev_name), None)
                if prev_task and prev_task.result:
                    context += f"\n{prev_name}: {prev_task.result.raw}"
                    
            # Add data from context tasks
            if current_task.context:
                for ctx_task in current_task.context:
                    if ctx_task.result and ctx_task.name != current_task.name:
                        context += f"\n{ctx_task.name}: {ctx_task.result.raw}"
        else:
            # New behavior: only include the most recent previous task
            if current_task.previous_tasks:
                # Get the most recent previous task (last in the list)
                prev_name = current_task.previous_tasks[-1]
                prev_task = next((t for t in self.tasks.values() if t.name == prev_name), None)
                if prev_task and prev_task.result:
                    context += f"\n{prev_name}: {prev_task.result.raw}"
                    
            # For context tasks, still include the most recent one
            if current_task.context:
                # Get the most recent context task with a result
                for ctx_task in reversed(current_task.context):
                    if ctx_task.result and ctx_task.name != current_task.name:
                        context += f"\n{ctx_task.name}: {ctx_task.result.raw}"
                        break  # Only include the most recent one
                        
        return context

    def _find_next_not_started_task(self) -> Optional[Task]:
        """Fallback mechanism to find the next 'not started' task."""
        fallback_attempts = 0
        temp_current_task = None
        
        # Clear previous task context before finding next task
        for task in self.tasks.values():
            if hasattr(task, 'description') and 'Input data from previous tasks:' in task.description:
                task.description = task.description.split('Input data from previous tasks:')[0].strip()
        
        while fallback_attempts < Process.DEFAULT_RETRY_LIMIT and not temp_current_task:
            fallback_attempts += 1
            logging.debug(f"Fallback attempt {fallback_attempts}: Trying to find next 'not started' task.")
            for task_candidate in self.tasks.values():
                if task_candidate.status == "not started":
                    # Check if there's a condition path to this task
                    current_conditions = task_candidate.condition or {}
                    leads_to_task = any(
                        task_value for task_value in current_conditions.values() 
                        if isinstance(task_value, (list, str)) and task_value
                    )
                    
                    if not leads_to_task and not task_candidate.next_tasks:
                        continue  # Skip if no valid path exists
                        
                    if self.task_retry_counter.get(task_candidate.id, 0) < Process.DEFAULT_RETRY_LIMIT:
                        self.task_retry_counter[task_candidate.id] = self.task_retry_counter.get(task_candidate.id, 0) + 1
                        temp_current_task = task_candidate
                        logging.debug(f"Fallback attempt {fallback_attempts}: Found 'not started' task: {temp_current_task.name}, retry count: {self.task_retry_counter[temp_current_task.id]}")
                        return temp_current_task # Return the found task immediately
                    else:
                        logging.debug(f"Max retries reached for task {task_candidate.name} in fallback mode, marking as failed.")
                        task_candidate.status = "failed"
            if not temp_current_task:
                logging.debug(f"Fallback attempt {fallback_attempts}: No 'not started' task found within retry limit.")
        return None # Return None if no task found after all attempts

    async def _get_manager_instructions_with_fallback_async(self, manager_task, manager_prompt, ManagerInstructions):
        """Async version of getting manager instructions with fallback"""
        try:
            # First try structured output (OpenAI compatible)
            logging.info("Attempting structured output...")
            return await self._get_structured_response_async(manager_task, manager_prompt, ManagerInstructions)
        except Exception as e:
            logging.info(f"Structured output failed: {e}, falling back to JSON mode...")
            # Fallback to regular JSON mode
            try:
                # Generate JSON structure description from Pydantic model
                try:
                    schema = ManagerInstructions.model_json_schema()
                    props_desc = ", ".join([f'"{k}": <{v.get("type", "any")}>' for k, v in schema.get('properties', {}).items()])
                    required_props = schema.get('required', [])
                    required_props_str = ', '.join(f'"{p}"' for p in required_props)
                    required_desc = f" (required: {required_props_str})" if required_props else ""
                    json_structure_desc = "{" + props_desc + "}"
                    enhanced_prompt = manager_prompt + f"\n\nIMPORTANT: Respond with valid JSON only, using this exact structure: {json_structure_desc}{required_desc}"
                except Exception as schema_error:
                    logging.warning(f"Could not generate schema for ManagerInstructions: {schema_error}. Using hardcoded prompt.")
                    # Fallback to hardcoded prompt if schema generation fails
                    enhanced_prompt = manager_prompt + "\n\nIMPORTANT: Respond with valid JSON only, using this exact structure: {\"task_id\": <int>, \"agent_name\": \"<string>\", \"action\": \"<execute or stop>\"}"
                
                return await self._get_json_response_async(manager_task, enhanced_prompt, ManagerInstructions)
            except Exception as fallback_error:
                error_msg = f"Both structured output and JSON fallback failed: {fallback_error}"
                logging.error(error_msg, exc_info=True)
                raise Exception(error_msg) from fallback_error

    def _get_manager_instructions_with_fallback(self, manager_task, manager_prompt, ManagerInstructions):
        """Sync version of getting manager instructions with fallback"""
        try:
            # First try structured output (OpenAI compatible)
            logging.info("Attempting structured output...")
            manager_response = client.beta.chat.completions.parse(
                model=self.manager_llm,
                messages=[
                    {"role": "system", "content": manager_task.description},
                    {"role": "user", "content": manager_prompt}
                ],
                temperature=0.7,
                response_format=ManagerInstructions
            )
            return manager_response.choices[0].message.parsed
        except Exception as e:
            logging.info(f"Structured output failed: {e}, falling back to JSON mode...")
            # Fallback to regular JSON mode
            try:
                # Generate JSON structure description from Pydantic model
                try:
                    schema = ManagerInstructions.model_json_schema()
                    props_desc = ", ".join([f'"{k}": <{v.get("type", "any")}>' for k, v in schema.get('properties', {}).items()])
                    required_props = schema.get('required', [])
                    required_props_str = ', '.join(f'"{p}"' for p in required_props)
                    required_desc = f" (required: {required_props_str})" if required_props else ""
                    json_structure_desc = "{" + props_desc + "}"
                    enhanced_prompt = manager_prompt + f"\n\nIMPORTANT: Respond with valid JSON only, using this exact structure: {json_structure_desc}{required_desc}"
                except Exception as schema_error:
                    logging.warning(f"Could not generate schema for ManagerInstructions: {schema_error}. Using hardcoded prompt.")
                    # Fallback to hardcoded prompt if schema generation fails
                    enhanced_prompt = manager_prompt + "\n\nIMPORTANT: Respond with valid JSON only, using this exact structure: {\"task_id\": <int>, \"agent_name\": \"<string>\", \"action\": \"<execute or stop>\"}"
                
                manager_response = client.chat.completions.create(
                    model=self.manager_llm,
                    messages=[
                        {"role": "system", "content": manager_task.description},
                        {"role": "user", "content": enhanced_prompt}
                    ],
                    temperature=0.7,
                    response_format={"type": "json_object"}
                )
                
                # Parse JSON and validate with Pydantic
                try:
                    json_content = manager_response.choices[0].message.content
                    parsed_json = json.loads(json_content)
                    return ManagerInstructions(**parsed_json)
                except (json.JSONDecodeError, ValueError) as e:
                    raise Exception(f"Failed to parse JSON response: {json_content}") from e
            except Exception as fallback_error:
                error_msg = f"Both structured output and JSON fallback failed: {fallback_error}"
                logging.error(error_msg, exc_info=True)
                raise Exception(error_msg) from fallback_error

    async def _get_structured_response_async(self, manager_task, manager_prompt, ManagerInstructions):
        """Async version of structured response"""
        # Create an async client instance for this async method
        async_client = AsyncOpenAI()
        manager_response = await async_client.beta.chat.completions.parse(
            model=self.manager_llm,
            messages=[
                {"role": "system", "content": manager_task.description},
                {"role": "user", "content": manager_prompt}
            ],
            temperature=0.7,
            response_format=ManagerInstructions
        )
        return manager_response.choices[0].message.parsed

    async def _get_json_response_async(self, manager_task, enhanced_prompt, ManagerInstructions):
        """Async version of JSON fallback response"""
        # Create an async client instance for this async method
        async_client = AsyncOpenAI()
        manager_response = await async_client.chat.completions.create(
            model=self.manager_llm,
            messages=[
                {"role": "system", "content": manager_task.description},
                {"role": "user", "content": enhanced_prompt}
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        
        # Parse JSON and validate with Pydantic
        try:
            json_content = manager_response.choices[0].message.content
            parsed_json = json.loads(json_content)
            return ManagerInstructions(**parsed_json)
        except (json.JSONDecodeError, ValueError) as e:
            raise Exception(f"Failed to parse JSON response: {json_content}") from e


    async def aworkflow(self) -> AsyncGenerator[str, None]:
        """Async version of workflow method"""
        logging.debug("=== Starting Async Workflow ===")
        current_iter = 0  # Track how many times we've looped
        # Build workflow relationships first
        logging.debug("Building workflow relationships...")
        for task in self.tasks.values():
            if task.next_tasks:
                for next_task_name in task.next_tasks:
                    next_task = next((t for t in self.tasks.values() if t.name == next_task_name), None)
                    if next_task:
                        next_task.previous_tasks.append(task.name)
                        logging.debug(f"Added {task.name} as previous task for {next_task_name}")

        # Find start task
        logging.debug("Finding start task...")
        start_task = None
        for task_id, task in self.tasks.items():
            if task.is_start:
                start_task = task
                logging.debug(f"Found marked start task: {task.name} (id: {task_id})")
                break

        if not start_task:
            start_task = list(self.tasks.values())[0]
            logging.debug(f"No start task marked, using first task: {start_task.name}")

        current_task = start_task
        visited_tasks = set()
        loop_data = {}  # Store loop-specific data

        # TODO: start task with loop feature is not available in aworkflow method

        while current_task:
            current_iter += 1
            if current_iter > self.max_iter:
                logging.info(f"Max iteration limit {self.max_iter} reached, ending workflow.")
                break

            # ADDED: Check workflow finished flag at the start of each cycle
            if self.workflow_finished:
                logging.info("Workflow finished early as all tasks are completed.")
                break

            # Add task summary at start of each cycle
            logging.debug(f"""
=== Workflow Cycle {current_iter} Summary ===
Total tasks: {len(self.tasks)}
Outstanding tasks: {sum(1 for t in self.tasks.values() if t.status != "completed")}
Completed tasks: {sum(1 for t in self.tasks.values() if t.status == "completed")}
Tasks by status:
- Not started: {sum(1 for t in self.tasks.values() if t.status == "not started")}
- In progress: {sum(1 for t in self.tasks.values() if t.status == "in_progress")}
- Completed: {sum(1 for t in self.tasks.values() if t.status == "completed")}
Tasks by type:
- Loop tasks: {sum(1 for t in self.tasks.values() if t.task_type == "loop")}
- Decision tasks: {sum(1 for t in self.tasks.values() if t.task_type == "decision")}
- Regular tasks: {sum(1 for t in self.tasks.values() if t.task_type not in ["loop", "decision"])}
            """)

            # ADDED: Check if all tasks are completed and set workflow_finished flag
            if all(task.status == "completed" for task in self.tasks.values()):
                logging.info("All tasks are completed.")
                self.workflow_finished = True
                # The next iteration loop check will break the workflow

            task_id = current_task.id
            logging.debug(f"""
=== Task Execution Details ===
Current task: {current_task.name}
Type: {current_task.task_type}
Status: {current_task.status}
Previous tasks: {current_task.previous_tasks}
Next tasks: {current_task.next_tasks}
Context tasks: {[t.name for t in current_task.context] if current_task.context else []}
Description length: {len(current_task.description)}
            """)

            # Add context from previous tasks to description
            context = self._build_task_context(current_task)
            if context:
                # Update task description with context
                current_task.description = current_task.description + context

            # Skip execution for loop tasks, only process their subtasks
            if current_task.task_type == "loop":
                logging.debug(f"""
=== Loop Task Details ===
Name: {current_task.name}
ID: {current_task.id}
Status: {current_task.status}
Next tasks: {current_task.next_tasks}
Condition: {current_task.condition}
Subtasks created: {getattr(current_task, '_subtasks_created', False)}
Input file: {getattr(current_task, 'input_file', None)}
                """)

                # Check if subtasks are created and completed
                if getattr(current_task, "_subtasks_created", False):
                    subtasks = [
                        t for t in self.tasks.values()
                        if t.name.startswith(current_task.name + "_")
                    ]
                    logging.debug(f"""
=== Subtask Status Check ===
Total subtasks: {len(subtasks)}
Completed: {sum(1 for st in subtasks if st.status == "completed")}
Pending: {sum(1 for st in subtasks if st.status != "completed")}
                    """)

                    # Log detailed subtask info
                    for st in subtasks:
                        logging.debug(f"""
Subtask: {st.name}
- Status: {st.status}
- Next tasks: {st.next_tasks}
- Condition: {st.condition}
                        """)

                    if subtasks and all(st.status == "completed" for st in subtasks):
                        logging.debug(f"=== All {len(subtasks)} subtasks completed for {current_task.name} ===")

                        # Mark loop task completed and move to next task
                        current_task.status = "completed"
                        logging.debug(f"Loop {current_task.name} marked as completed")

                        # Set result for loop task when all subtasks complete
                        if not current_task.result:
                            # Get result from last completed subtask
                            last_subtask = next((t for t in reversed(subtasks) if t.status == "completed"), None)
                            if last_subtask and last_subtask.result:
                                current_task.result = last_subtask.result
                        
                        # Route to next task based on condition
                        if current_task.condition:
                            # Get decision from result if available
                            decision_str = None
                            if current_task.result:
                                if current_task.result.pydantic and hasattr(current_task.result.pydantic, "decision"):
                                    decision_str = current_task.result.pydantic.decision.lower()
                                elif current_task.result.raw:
                                    decision_str = current_task.result.raw.lower()
                            
                            # For loop tasks, use "done" to follow condition path
                            if current_task.task_type == "loop" and all(t.status == "completed" for t in subtasks):
                                decision_str = "done"
                            
                            target_tasks = current_task.condition.get(decision_str, []) if decision_str else []
                            task_value = target_tasks[0] if isinstance(target_tasks, list) else target_tasks
                            next_task = next((t for t in self.tasks.values() if t.name == task_value), None)
                            if next_task:
                                next_task.status = "not started"  # Reset status to allow execution
                                logging.debug(f"Routing to {next_task.name} based on decision: {decision_str}")
                                self.workflow_finished = False
                                current_task = next_task
                                # Ensure the task is yielded for execution
                                if current_task.id not in visited_tasks:
                                    yield current_task.id
                                    visited_tasks.add(current_task.id)
                            else:
                                # End workflow if no valid next task found
                                logging.info(f"No valid next task found for decision: {decision_str}")
                                self.workflow_finished = True
                                current_task = None
                                break
                else:
                    logging.debug(f"No subtasks created yet for {current_task.name}")
                    # Create subtasks if needed
                    if current_task.input_file:
                        self._create_loop_subtasks(current_task)
                        current_task._subtasks_created = True
                        logging.debug(f"Created subtasks from {current_task.input_file}")
                    else:
                        # No input file, mark as done
                        current_task.status = "completed"
                        logging.debug(f"No input file, marking {current_task.name} as completed")
                        if current_task.next_tasks:
                            next_task_name = current_task.next_tasks[0]
                            next_task = next((t for t in self.tasks.values() if t.name == next_task_name), None)
                            current_task = next_task
                        else:
                            current_task = None
            else:
                # Execute non-loop task
                logging.debug(f"=== Executing non-loop task: {current_task.name} (id: {task_id}) ===")
                logging.debug(f"Task status: {current_task.status}")
                logging.debug(f"Task next_tasks: {current_task.next_tasks}")
                yield task_id
                visited_tasks.add(task_id)

                # Only end workflow if no next_tasks AND no conditions
                if not current_task.next_tasks and not current_task.condition and not any(
                    t.task_type == "loop" and current_task.name.startswith(t.name + "_")
                    for t in self.tasks.values()
                ):
                    logging.info(f"Task {current_task.name} has no next tasks, ending workflow")
                    self.workflow_finished = True
                    current_task = None
                    break

            # Reset completed task to "not started" so it can run again
            if self.tasks[task_id].status == "completed":
                # Never reset loop tasks, decision tasks, or their subtasks if rerun is False
                subtask_name = self.tasks[task_id].name
                task_to_check = self.tasks[task_id]
                logging.debug(f"=== Checking reset for completed task: {subtask_name} ===")
                logging.debug(f"Task type: {task_to_check.task_type}")
                logging.debug(f"Task status before reset check: {task_to_check.status}")
                logging.debug(f"Task rerun: {getattr(task_to_check, 'rerun', True)}") # default to True if not set

                if (getattr(task_to_check, 'rerun', True) and # Corrected condition - reset only if rerun is True (or default True)
                    task_to_check.task_type != "loop" and # Removed "decision" from exclusion
                    not any(t.task_type == "loop" and subtask_name.startswith(t.name + "_")
                           for t in self.tasks.values())):
                    logging.debug(f"=== Resetting non-loop, non-decision task {subtask_name} to 'not started' ===")
                    self.tasks[task_id].status = "not started"
                    logging.debug(f"Task status after reset: {self.tasks[task_id].status}")
                else:
                    logging.debug(f"=== Skipping reset for loop/decision/subtask or rerun=False: {subtask_name} ===")
                    logging.debug(f"Keeping status as: {self.tasks[task_id].status}")

            # Handle loop progression
            if current_task.task_type == "loop":
                loop_key = f"loop_{current_task.name}"
                if loop_key in loop_data:
                    loop_info = loop_data[loop_key]
                    loop_info["index"] += 1
                    has_more = loop_info["remaining"] > 0

                    # Update result to trigger correct condition
                    if current_task.result:
                        result = current_task.result.raw
                        if has_more:
                            result += "\nmore"
                        else:
                            result += "\ndone"
                        current_task.result.raw = result

            # Determine next task based on result
            next_task = None
            if current_task and current_task.result:
                if current_task.task_type in ["decision", "loop"]:
                    # Get decision from pydantic or raw response
                    decision_str = current_task.result.raw.lower()
                    if current_task.result.pydantic and hasattr(current_task.result.pydantic, "decision"):
                        decision_str = current_task.result.pydantic.decision.lower()

                    # Check if task has conditions and next_tasks
                    if current_task.condition:
                        # Get target task based on decision
                        target_tasks = current_task.condition.get(decision_str, [])
                        # Handle all forms of exit conditions
                        if not target_tasks or target_tasks == "exit" or (isinstance(target_tasks, list) and (not target_tasks or target_tasks[0] == "exit")):
                            logging.info(f"Workflow exit condition met on decision: {decision_str}")
                            self.workflow_finished = True
                            current_task = None
                            break
                        else:
                            # Find the target task by name
                            task_value = target_tasks[0] if isinstance(target_tasks, list) else target_tasks
                            next_task = next((t for t in self.tasks.values() if t.name == task_value), None)
                            if next_task:
                                next_task.status = "not started"  # Reset status to allow execution
                                logging.debug(f"Routing to {next_task.name} based on decision: {decision_str}")
                                # Don't mark workflow as finished when following condition path
                                self.workflow_finished = False

            # If no condition-based routing, use next_tasks
            if not next_task and current_task and current_task.next_tasks:
                next_task_name = current_task.next_tasks[0]
                next_task = next((t for t in self.tasks.values() if t.name == next_task_name), None)
                if next_task:
                    # Reset the next task to allow re-execution
                    next_task.status = "not started"
                    # Don't mark workflow as finished if we're in a task loop
                    if (next_task.previous_tasks and current_task.name in next_task.previous_tasks and 
                        next_task.next_tasks and 
                        next_task.next_tasks[0] in self.tasks and 
                        next_task.name in self.tasks[next_task.next_tasks[0]].previous_tasks):
                        self.workflow_finished = False
                    logging.debug(f"Following next_tasks to {next_task.name}")

            current_task = next_task
            if not current_task:
                current_task = self._find_next_not_started_task() # General fallback if no next task in workflow


            if not current_task:
                # Add final workflow summary
                logging.debug(f"""
=== Final Workflow Summary ===
Total tasks processed: {len(self.tasks)}
Final status:
- Completed tasks: {sum(1 for t in self.tasks.values() if t.status == "completed")}
- Outstanding tasks: {sum(1 for t in self.tasks.values() if t.status != "completed")}
Tasks by status:
- Not started: {sum(1 for t in self.tasks.values() if t.status == "not started")}
- In progress: {sum(1 for t in self.tasks.values() if t.status == "in_progress")}
- Completed: {sum(1 for t in self.tasks.values() if t.status == "completed")}
- Failed: {sum(1 for t in self.tasks.values() if t.status == "failed")}
Tasks by type:
- Loop tasks: {sum(1 for t in self.tasks.values() if t.task_type == "loop")}
- Decision tasks: {sum(1 for t in self.tasks.values() if t.task_type == "decision")}
- Regular tasks: {sum(1 for t in self.tasks.values() if t.task_type not in ["loop", "decision"])}
Total iterations: {current_iter}
Workflow Finished: {self.workflow_finished} # ADDED: Workflow Finished Status
                """)

                logging.info("Workflow execution completed")
                break

            # Add completion logging
            logging.debug(f"""
=== Task Completion ===
Task: {current_task.name}
Final status: {current_task.status}
Next task: {next_task.name if next_task else None}
Iteration: {current_iter}/{self.max_iter}
Workflow Finished: {self.workflow_finished} # ADDED: Workflow Finished Status
            """)

    async def asequential(self) -> AsyncGenerator[str, None]:
        """Async version of sequential method"""
        for task_id in self.tasks:
            if self.tasks[task_id].status != "completed":
                yield task_id

    async def ahierarchical(self) -> AsyncGenerator[str, None]:
        """Async version of hierarchical method"""
        logging.debug(f"Starting hierarchical task execution with {len(self.tasks)} tasks")
        manager_agent = Agent(
            name="Manager",
            role="Project manager",
            goal="Manage the entire flow of tasks and delegate them to the right agent",
            backstory="Expert project manager to coordinate tasks among agents",
            llm=self.manager_llm,
            verbose=self.verbose,
            markdown=True,
            self_reflect=False
        )

        class ManagerInstructions(BaseModel):
            task_id: int
            agent_name: str
            action: str

        manager_task = Task(
            name="manager_task",
            description="Decide the order of tasks and which agent executes them",
            expected_output="All tasks completed successfully",
            agent=manager_agent
        )
        manager_task_id = yield manager_task
        logging.info(f"Created manager task with ID {manager_task_id}")

        completed_count = 0
        total_tasks = len(self.tasks) - 1
        logging.info(f"Need to complete {total_tasks} tasks (excluding manager task)")

        while completed_count < total_tasks:
            tasks_summary = []
            for tid, tk in self.tasks.items():
                if tk.name == "manager_task":
                    continue
                task_info = {
                    "task_id": tid,
                    "name": tk.name,
                    "description": tk.description,
                    "status": tk.status if tk.status else "not started",
                    "agent": tk.agent.name if tk.agent else "No agent"
                }
                tasks_summary.append(task_info)
                logging.info(f"Task {tid} status: {task_info}")

            manager_prompt = f"""
Here is the current status of all tasks except yours (manager_task):
{tasks_summary}

Provide a JSON with the structure:
{{
   "task_id": <int>,
   "agent_name": "<string>",
   "action": "<execute or stop>"
}}
"""

            try:
                logging.info("Requesting manager instructions...")
                if manager_task.async_execution:
                    parsed_instructions = await self._get_manager_instructions_with_fallback_async(
                        manager_task, manager_prompt, ManagerInstructions
                    )
                else:
                    parsed_instructions = self._get_manager_instructions_with_fallback(
                        manager_task, manager_prompt, ManagerInstructions
                    )
                logging.info(f"Manager instructions: {parsed_instructions}")
            except Exception as e:
                display_error(f"Manager parse error: {e}")
                logging.error(f"Manager parse error: {str(e)}", exc_info=True)
                break

            selected_task_id = parsed_instructions.task_id
            selected_agent_name = parsed_instructions.agent_name
            action = parsed_instructions.action

            logging.info(f"Manager selected task_id={selected_task_id}, agent={selected_agent_name}, action={action}")

            if action.lower() == "stop":
                logging.info("Manager decided to stop task execution")
                break

            if selected_task_id not in self.tasks:
                error_msg = f"Manager selected invalid task id {selected_task_id}"
                display_error(error_msg)
                logging.error(error_msg)
                break

            original_agent = self.tasks[selected_task_id].agent.name if self.tasks[selected_task_id].agent else "None"
            for a in self.agents:
                if a.name == selected_agent_name:
                    self.tasks[selected_task_id].agent = a
                    logging.info(f"Changed agent for task {selected_task_id} from {original_agent} to {selected_agent_name}")
                    break

            if self.tasks[selected_task_id].status != "completed":
                logging.info(f"Starting execution of task {selected_task_id}")
                yield selected_task_id
                logging.info(f"Finished execution of task {selected_task_id}, status: {self.tasks[selected_task_id].status}")

            if self.tasks[selected_task_id].status == "completed":
                completed_count += 1
                logging.info(f"Task {selected_task_id} completed. Total completed: {completed_count}/{total_tasks}")

        self.tasks[manager_task.id].status = "completed"
        if self.verbose >= 1:
            logging.info("All tasks completed under manager supervision.")
        logging.info("Hierarchical task execution finished")

    def workflow(self):
        """Synchronous version of workflow method"""
        current_iter = 0  # Track how many times we've looped
        # Build workflow relationships first
        for task in self.tasks.values():
            if task.next_tasks:
                for next_task_name in task.next_tasks:
                    next_task = next((t for t in self.tasks.values() if t.name == next_task_name), None)
                    if next_task:
                        next_task.previous_tasks.append(task.name)

        # Find start task
        start_task = None
        for task_id, task in self.tasks.items():
            if task.is_start:
                start_task = task
                break

        if not start_task:
            start_task = list(self.tasks.values())[0]
            logging.info("No start task marked, using first task")

        # If loop type and no input_file, default to tasks.csv
        if start_task and start_task.task_type == "loop" and not start_task.input_file:
            start_task.input_file = "tasks.csv"

        # --- If loop + input_file, read file & create tasks
        if start_task and start_task.task_type == "loop" and getattr(start_task, "input_file", None):
            try:
                file_ext = os.path.splitext(start_task.input_file)[1].lower()
                new_tasks = []

                if file_ext == ".csv":
                    with open(start_task.input_file, "r", encoding="utf-8") as f:
                        reader = csv.reader(f, quotechar='"', escapechar='\\')  # Handle quoted/escaped fields
                        previous_task = None
                        task_count = 0

                        for i, row in enumerate(reader):
                            if not row:  # Skip truly empty rows
                                continue

                            # Properly handle Q&A pairs with potential commas
                            task_desc = row[0].strip() if row else ""
                            if len(row) > 1:
                                # Preserve all fields in case of multiple commas
                                question = row[0].strip()
                                answer = ",".join(field.strip() for field in row[1:])
                                task_desc = f"Question: {question}\nAnswer: {answer}"

                            if not task_desc:  # Skip rows with empty content
                                continue

                            task_count += 1
                            logging.debug(f"Processing CSV row {i+1}: {task_desc}")

                            # Inherit next_tasks from parent loop task
                            inherited_next_tasks = start_task.next_tasks if start_task.next_tasks else []

                            row_task = Task(
                                description=f"{start_task.description}\n{task_desc}" if start_task.description else task_desc,
                                agent=start_task.agent,
                                name=f"{start_task.name}_{task_count}" if start_task.name else task_desc,
                                expected_output=getattr(start_task, 'expected_output', None),
                                is_start=(task_count == 1),
                                task_type="decision",  # Change to decision type
                                next_tasks=inherited_next_tasks,  # Inherit parent's next tasks
                                condition={
                                    "done": inherited_next_tasks if inherited_next_tasks else ["next"],  # Use full inherited_next_tasks
                                    "retry": ["current"],
                                    "exit": []  # Empty list for exit condition
                                }
                            )
                            self.tasks[row_task.id] = row_task
                            new_tasks.append(row_task)

                            if previous_task:
                                previous_task.next_tasks = [row_task.name]
                                previous_task.condition["done"] = [row_task.name]  # Use "done" consistently
                            previous_task = row_task

                            # For the last task in the loop, ensure it points to parent's next tasks
                            if task_count > 0 and not row_task.next_tasks:
                                row_task.next_tasks = inherited_next_tasks

                        logging.info(f"Processed {task_count} rows from CSV file")
                else:
                    # If not CSV, read lines
                    with open(start_task.input_file, "r", encoding="utf-8") as f:
                        lines = f.read().splitlines()
                        previous_task = None
                        for i, line in enumerate(lines):
                            row_task = Task(
                                description=f"{start_task.description}\n{line.strip()}" if start_task.description else line.strip(),
                                agent=start_task.agent,
                                name=f"{start_task.name}_{i+1}" if start_task.name else line.strip(),
                                expected_output=getattr(start_task, 'expected_output', None),
                                is_start=(i == 0),
                                task_type="task",
                                condition={
                                    "complete": ["next"],
                                    "retry": ["current"]
                                }
                            )
                            self.tasks[row_task.id] = row_task
                            new_tasks.append(row_task)

                            if previous_task:
                                previous_task.next_tasks = [row_task.name]
                                previous_task.condition["complete"] = [row_task.name]
                            previous_task = row_task

                if new_tasks:
                    start_task = new_tasks[0]
                    logging.info(f"Created {len(new_tasks)} tasks from: {start_task.input_file}")
            except Exception as e:
                logging.error(f"Failed to read file tasks: {e}")

        # end of start task handling
        current_task = start_task
        visited_tasks = set()
        loop_data = {}  # Store loop-specific data

        while current_task:
            current_iter += 1
            if current_iter > self.max_iter:
                logging.info(f"Max iteration limit {self.max_iter} reached, ending workflow.")
                break

            # ADDED: Check workflow finished flag at the start of each cycle
            if self.workflow_finished:
                logging.info("Workflow finished early as all tasks are completed.")
                break

            # Add task summary at start of each cycle
            logging.debug(f"""
=== Workflow Cycle {current_iter} Summary ===
Total tasks: {len(self.tasks)}
Outstanding tasks: {sum(1 for t in self.tasks.values() if t.status != "completed")}
Completed tasks: {sum(1 for t in self.tasks.values() if t.status == "completed")}
Tasks by status:
- Not started: {sum(1 for t in self.tasks.values() if t.status == "not started")}
- In progress: {sum(1 for t in self.tasks.values() if t.status == "in_progress")}
- Completed: {sum(1 for t in self.tasks.values() if t.status == "completed")}
Tasks by type:
- Loop tasks: {sum(1 for t in self.tasks.values() if t.task_type == "loop")}
- Decision tasks: {sum(1 for t in self.tasks.values() if t.task_type == "decision")}
- Regular tasks: {sum(1 for t in self.tasks.values() if t.task_type not in ["loop", "decision"])}
            """)

            # ADDED: Check if all tasks are completed and set workflow_finished flag
            if all(task.status == "completed" for task in self.tasks.values()):
                logging.info("All tasks are completed.")
                self.workflow_finished = True
                # The next iteration loop check will break the workflow


            # Handle loop task file reading at runtime
            if (current_task.task_type == "loop" and
                current_task is not start_task and
                getattr(current_task, "_subtasks_created", False) is not True):

                if not current_task.input_file:
                    current_task.input_file = "tasks.csv"

                if getattr(current_task, "input_file", None):
                    try:
                        file_ext = os.path.splitext(current_task.input_file)[1].lower()
                        new_tasks = []

                        if file_ext == ".csv":
                            with open(current_task.input_file, "r", encoding="utf-8") as f:
                                reader = csv.reader(f)
                                previous_task = None
                                for i, row in enumerate(reader):
                                    if row:  # Skip empty rows
                                        task_desc = row[0]  # Take first column
                                        row_task = Task(
                                            description=f"{current_task.description}\n{task_desc}" if current_task.description else task_desc,
                                            agent=current_task.agent,
                                            name=f"{current_task.name}_{i+1}" if current_task.name else task_desc,
                                            expected_output=getattr(current_task, 'expected_output', None),
                                            is_start=(i == 0),
                                            task_type="task",
                                            condition={
                                                "complete": ["next"],
                                                "retry": ["current"]
                                            }
                                        )
                                        self.tasks[row_task.id] = row_task
                                        new_tasks.append(row_task)

                                        if previous_task:
                                            previous_task.next_tasks = [row_task.name]
                                            previous_task.condition["complete"] = [row_task.name]
                                        previous_task = row_task
                        else:
                            with open(current_task.input_file, "r", encoding="utf-8") as f:
                                lines = f.read().splitlines()
                                previous_task = None
                                for i, line in enumerate(lines):
                                    row_task = Task(
                                        description=f"{current_task.description}\n{line.strip()}" if current_task.description else line.strip(),
                                        agent=current_task.agent,
                                        name=f"{current_task.name}_{i+1}" if current_task.name else line.strip(),
                                        expected_output=getattr(current_task, 'expected_output', None),
                                        is_start=(i == 0),
                                        task_type="task",
                                        condition={
                                            "complete": ["next"],
                                            "retry": ["current"]
                                        }
                                    )
                                    self.tasks[row_task.id] = row_task
                                    new_tasks.append(row_task)

                                    if previous_task:
                                        previous_task.next_tasks = [row_task.name]
                                        previous_task.condition["complete"] = [row_task.name]
                                    previous_task = row_task

                        if new_tasks:
                            current_task.next_tasks = [new_tasks[0].name]
                            current_task._subtasks_created = True
                            logging.info(f"Created {len(new_tasks)} tasks from: {current_task.input_file} for loop task {current_task.name}")
                    except Exception as e:
                        logging.error(f"Failed to read file tasks for loop task {current_task.name}: {e}")

            task_id = current_task.id
            logging.debug(f"""
=== Task Execution Details ===
Current task: {current_task.name}
Type: {current_task.task_type}
Status: {current_task.status}
Previous tasks: {current_task.previous_tasks}
Next tasks: {current_task.next_tasks}
Context tasks: {[t.name for t in current_task.context] if current_task.context else []}
Description length: {len(current_task.description)}
            """)

            # Add context from previous tasks to description
            context = self._build_task_context(current_task)
            if context:
                # Update task description with context
                current_task.description = current_task.description + context

            # Skip execution for loop tasks, only process their subtasks
            if current_task.task_type == "loop":
                logging.debug(f"""
=== Loop Task Details ===
Name: {current_task.name}
ID: {current_task.id}
Status: {current_task.status}
Next tasks: {current_task.next_tasks}
Condition: {current_task.condition}
Subtasks created: {getattr(current_task, '_subtasks_created', False)}
Input file: {getattr(current_task, 'input_file', None)}
                """)

                # Check if subtasks are created and completed
                if getattr(current_task, "_subtasks_created", False):
                    subtasks = [
                        t for t in self.tasks.values()
                        if t.name.startswith(current_task.name + "_")
                    ]

                    logging.debug(f"""
=== Subtask Status Check ===
Total subtasks: {len(subtasks)}
Completed: {sum(1 for st in subtasks if st.status == "completed")}
Pending: {sum(1 for st in subtasks if st.status != "completed")}
                    """)

                    for st in subtasks:
                        logging.debug(f"""
Subtask: {st.name}
- Status: {st.status}
- Next tasks: {st.next_tasks}
- Condition: {st.condition}
                        """)

                    if subtasks and all(st.status == "completed" for st in subtasks):
                        logging.debug(f"=== All {len(subtasks)} subtasks completed for {current_task.name} ===")

                        # Mark loop task completed and move to next task
                        current_task.status = "completed"
                        logging.debug(f"Loop {current_task.name} marked as completed")

                        # Set result for loop task when all subtasks complete
                        if not current_task.result:
                            # Get result from last completed subtask
                            last_subtask = next((t for t in reversed(subtasks) if t.status == "completed"), None)
                            if last_subtask and last_subtask.result:
                                current_task.result = last_subtask.result
                        
                        # Route to next task based on condition
                        if current_task.condition:
                            # Get decision from result if available
                            decision_str = None
                            if current_task.result:
                                if current_task.result.pydantic and hasattr(current_task.result.pydantic, "decision"):
                                    decision_str = current_task.result.pydantic.decision.lower()
                                elif current_task.result.raw:
                                    decision_str = current_task.result.raw.lower()
                            
                            # For loop tasks, use "done" to follow condition path
                            if current_task.task_type == "loop" and all(t.status == "completed" for t in subtasks):
                                decision_str = "done"
                            
                            target_tasks = current_task.condition.get(decision_str, []) if decision_str else []
                            task_value = target_tasks[0] if isinstance(target_tasks, list) else target_tasks
                            next_task = next((t for t in self.tasks.values() if t.name == task_value), None)
                            if next_task:
                                next_task.status = "not started"  # Reset status to allow execution
                                logging.debug(f"Routing to {next_task.name} based on decision: {decision_str}")
                                self.workflow_finished = False
                                current_task = next_task
                                # Ensure the task is yielded for execution
                                if current_task.id not in visited_tasks:
                                    yield current_task.id
                                    visited_tasks.add(current_task.id)
                            else:
                                # End workflow if no valid next task found
                                logging.info(f"No valid next task found for decision: {decision_str}")
                                self.workflow_finished = True
                                current_task = None
                                break
                else:
                    logging.debug(f"No subtasks created yet for {current_task.name}")
                    # Create subtasks if needed
                    if current_task.input_file:
                        self._create_loop_subtasks(current_task)
                        current_task._subtasks_created = True
                        logging.debug(f"Created subtasks from {current_task.input_file}")
                    else:
                        # No input file, mark as done
                        current_task.status = "completed"
                        logging.debug(f"No input file, marking {current_task.name} as completed")
                        if current_task.next_tasks:
                            next_task_name = current_task.next_tasks[0]
                            next_task = next((t for t in self.tasks.values() if t.name == next_task_name), None)
                            current_task = next_task
                        else:
                            current_task = None
            else:
                # Execute non-loop task
                logging.debug(f"=== Executing non-loop task: {current_task.name} (id: {task_id}) ===")
                logging.debug(f"Task status: {current_task.status}")
                logging.debug(f"Task next_tasks: {current_task.next_tasks}")
                yield task_id
                visited_tasks.add(task_id)

                # Only end workflow if no next_tasks AND no conditions
                if not current_task.next_tasks and not current_task.condition and not any(
                    t.task_type == "loop" and current_task.name.startswith(t.name + "_")
                    for t in self.tasks.values()
                ):
                    logging.info(f"Task {current_task.name} has no next tasks, ending workflow")
                    self.workflow_finished = True
                    current_task = None
                    break

            # Reset completed task to "not started" so it can run again
            if self.tasks[task_id].status == "completed":
                # Never reset loop tasks, decision tasks, or their subtasks if rerun is False
                subtask_name = self.tasks[task_id].name
                task_to_check = self.tasks[task_id]
                logging.debug(f"=== Checking reset for completed task: {subtask_name} ===")
                logging.debug(f"Task type: {task_to_check.task_type}")
                logging.debug(f"Task status before reset check: {task_to_check.status}")
                logging.debug(f"Task rerun: {getattr(task_to_check, 'rerun', True)}") # default to True if not set

                if (getattr(task_to_check, 'rerun', True) and # Corrected condition - reset only if rerun is True (or default True)
                    task_to_check.task_type != "loop" and # Removed "decision" from exclusion
                    not any(t.task_type == "loop" and subtask_name.startswith(t.name + "_")
                           for t in self.tasks.values())):
                    logging.debug(f"=== Resetting non-loop, non-decision task {subtask_name} to 'not started' ===")
                    self.tasks[task_id].status = "not started"
                    logging.debug(f"Task status after reset: {self.tasks[task_id].status}")
                else:
                    logging.debug(f"=== Skipping reset for loop/decision/subtask or rerun=False: {subtask_name} ===")
                    logging.debug(f"Keeping status as: {self.tasks[task_id].status}")


            # Handle loop progression
            if current_task.task_type == "loop":
                loop_key = f"loop_{current_task.name}"
                if loop_key in loop_data:
                    loop_info = loop_data[loop_key]
                    loop_info["index"] += 1
                    has_more = loop_info["remaining"] > 0

                    # Update result to trigger correct condition
                    if current_task.result:
                        result = current_task.result.raw
                        if has_more:
                            result += "\nmore"
                        else:
                            result += "\ndone"
                        current_task.result.raw = result

            # Determine next task based on result
            next_task = None
            if current_task and current_task.result:
                if current_task.task_type in ["decision", "loop"]:
                    # Get decision from pydantic or raw response
                    decision_str = current_task.result.raw.lower()
                    if current_task.result.pydantic and hasattr(current_task.result.pydantic, "decision"):
                        decision_str = current_task.result.pydantic.decision.lower()

                    # Check if task has conditions and next_tasks
                    if current_task.condition:
                        # Get target task based on decision
                        target_tasks = current_task.condition.get(decision_str, [])
                        # Handle all forms of exit conditions
                        if not target_tasks or target_tasks == "exit" or (isinstance(target_tasks, list) and (not target_tasks or target_tasks[0] == "exit")):
                            logging.info(f"Workflow exit condition met on decision: {decision_str}")
                            self.workflow_finished = True
                            current_task = None
                            break
                        else:
                            # Find the target task by name
                            task_value = target_tasks[0] if isinstance(target_tasks, list) else target_tasks
                            next_task = next((t for t in self.tasks.values() if t.name == task_value), None)
                            if next_task:
                                next_task.status = "not started"  # Reset status to allow execution
                                logging.debug(f"Routing to {next_task.name} based on decision: {decision_str}")
                                # Don't mark workflow as finished when following condition path
                                self.workflow_finished = False

            # If no condition-based routing, use next_tasks
            if not next_task and current_task and current_task.next_tasks:
                next_task_name = current_task.next_tasks[0]
                next_task = next((t for t in self.tasks.values() if t.name == next_task_name), None)
                if next_task:
                    # Reset the next task to allow re-execution
                    next_task.status = "not started"
                    # Don't mark workflow as finished if we're in a task loop
                    if (next_task.previous_tasks and current_task.name in next_task.previous_tasks and 
                        next_task.next_tasks and 
                        next_task.next_tasks[0] in self.tasks and 
                        next_task.name in self.tasks[next_task.next_tasks[0]].previous_tasks):
                        self.workflow_finished = False
                    logging.debug(f"Following next_tasks to {next_task.name}")

            current_task = next_task
            if not current_task:
                current_task = self._find_next_not_started_task() # General fallback if no next task in workflow


            if not current_task:
                # Add final workflow summary
                logging.debug(f"""
=== Final Workflow Summary ===
Total tasks processed: {len(self.tasks)}
Final status:
- Completed tasks: {sum(1 for t in self.tasks.values() if t.status == "completed")}
- Outstanding tasks: {sum(1 for t in self.tasks.values() if t.status != "completed")}
Tasks by status:
- Not started: {sum(1 for t in self.tasks.values() if t.status == "not started")}
- In progress: {sum(1 for t in self.tasks.values() if t.status == "in_progress")}
- Completed: {sum(1 for t in self.tasks.values() if t.status == "completed")}
- Failed: {sum(1 for t in self.tasks.values() if t.status == "failed")}
Tasks by type:
- Loop tasks: {sum(1 for t in self.tasks.values() if t.task_type == "loop")}
- Decision tasks: {sum(1 for t in self.tasks.values() if t.task_type == "decision")}
- Regular tasks: {sum(1 for t in self.tasks.values() if t.task_type not in ["loop", "decision"])}
Total iterations: {current_iter}
Workflow Finished: {self.workflow_finished} # ADDED: Workflow Finished Status
                """)

                logging.info("Workflow execution completed")
                break

            # Add completion logging
            logging.debug(f"""
=== Task Completion ===
Task: {current_task.name}
Final status: {current_task.status}
Next task: {next_task.name if next_task else None}
Iteration: {current_iter}/{self.max_iter}
Workflow Finished: {self.workflow_finished} # ADDED: Workflow Finished Status
            """)

    def sequential(self):
        """Synchronous version of sequential method"""
        for task_id in self.tasks:
            if self.tasks[task_id].status != "completed":
                yield task_id

    def hierarchical(self):
        """Synchronous version of hierarchical method"""
        logging.debug(f"Starting hierarchical task execution with {len(self.tasks)} tasks")
        manager_agent = Agent(
            name="Manager",
            role="Project manager",
            goal="Manage the entire flow of tasks and delegate them to the right agent",
            backstory="Expert project manager to coordinate tasks among agents",
            llm=self.manager_llm,
            verbose=self.verbose,
            markdown=True,
            self_reflect=False
        )

        class ManagerInstructions(BaseModel):
            task_id: int
            agent_name: str
            action: str

        manager_task = Task(
            name="manager_task",
            description="Decide the order of tasks and which agent executes them",
            expected_output="All tasks completed successfully",
            agent=manager_agent
        )
        manager_task_id = yield manager_task
        logging.info(f"Created manager task with ID {manager_task_id}")

        completed_count = 0
        total_tasks = len(self.tasks) - 1
        logging.info(f"Need to complete {total_tasks} tasks (excluding manager task)")

        while completed_count < total_tasks:
            tasks_summary = []
            for tid, tk in self.tasks.items():
                if tk.name == "manager_task":
                    continue
                task_info = {
                    "task_id": tid,
                    "name": tk.name,
                    "description": tk.description,
                    "status": tk.status if tk.status else "not started",
                    "agent": tk.agent.name if tk.agent else "No agent"
                }
                tasks_summary.append(task_info)
                logging.info(f"Task {tid} status: {task_info}")

            manager_prompt = f"""
Here is the current status of all tasks except yours (manager_task):
{tasks_summary}

Provide a JSON with the structure:
{{
   "task_id": <int>,
   "agent_name": "<string>",
   "action": "<execute or stop>"
}}
"""

            try:
                logging.info("Requesting manager instructions...")
                parsed_instructions = self._get_manager_instructions_with_fallback(
                    manager_task, manager_prompt, ManagerInstructions
                )
                logging.info(f"Manager instructions: {parsed_instructions}")
            except Exception as e:
                display_error(f"Manager parse error: {e}")
                logging.error(f"Manager parse error: {str(e)}", exc_info=True)
                break

            selected_task_id = parsed_instructions.task_id
            selected_agent_name = parsed_instructions.agent_name
            action = parsed_instructions.action

            logging.info(f"Manager selected task_id={selected_task_id}, agent={selected_agent_name}, action={action}")

            if action.lower() == "stop":
                logging.info("Manager decided to stop task execution")
                break

            if selected_task_id not in self.tasks:
                error_msg = f"Manager selected invalid task id {selected_task_id}"
                display_error(error_msg)
                logging.error(error_msg)
                break

            original_agent = self.tasks[selected_task_id].agent.name if self.tasks[selected_task_id].agent else "None"
            for a in self.agents:
                if a.name == selected_agent_name:
                    self.tasks[selected_task_id].agent = a
                    logging.info(f"Changed agent for task {selected_task_id} from {original_agent} to {selected_agent_name}")
                    break

            if self.tasks[selected_task_id].status != "completed":
                logging.info(f"Starting execution of task {selected_task_id}")
                yield selected_task_id
                logging.info(f"Finished execution of task {selected_task_id}, status: {self.tasks[selected_task_id].status}")

            if self.tasks[selected_task_id].status == "completed":
                completed_count += 1
                logging.info(f"Task {selected_task_id} completed. Total completed: {completed_count}/{total_tasks}")

        self.tasks[manager_task.id].status = "completed"
        if self.verbose >= 1:
            logging.info("All tasks completed under manager supervision.")
        logging.info("Hierarchical task execution finished")