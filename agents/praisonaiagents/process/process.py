import logging
import asyncio
from typing import Dict, Optional, List, Any, AsyncGenerator
from pydantic import BaseModel
from ..agent.agent import Agent
from ..task.task import Task
from ..main import display_error, client
import csv
import os

class LoopItems(BaseModel):
    items: List[Any]

class Process:
    def __init__(self, tasks: Dict[str, Task], agents: List[Agent], manager_llm: Optional[str] = None, verbose: bool = False, max_iter: int = 10):
        self.tasks = tasks
        self.agents = agents
        self.manager_llm = manager_llm
        self.verbose = verbose
        self.max_iter = max_iter

    async def aworkflow(self) -> AsyncGenerator[str, None]:
        """Async version of workflow method"""
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
        
        current_task = start_task
        visited_tasks = set()
        loop_data = {}  # Store loop-specific data
        
        while current_task:
            current_iter += 1
            if current_iter > self.max_iter:
                logging.info(f"Max iteration limit {self.max_iter} reached, ending workflow.")
                break

            task_id = current_task.id
            logging.info(f"Executing workflow task: {current_task.name if current_task.name else task_id}")
            
            # Add context from previous tasks to description
            if current_task.previous_tasks or current_task.context:
                context = "\nInput data from previous tasks:"
                
                # Add data from previous tasks in workflow
                for prev_name in current_task.previous_tasks:
                    prev_task = next((t for t in self.tasks.values() if t.name == prev_name), None)
                    if prev_task and prev_task.result:
                        # Handle loop data
                        if current_task.task_type == "loop":
#                             # create a loop manager Agent
#                             loop_manager = Agent(
#                                 name="Loop Manager",
#                                 role="Loop data processor",
#                                 goal="Process loop data and convert it to list format",
#                                 backstory="Expert at handling loop data and converting it to proper format",
#                                 llm=self.manager_llm,
#                                 verbose=self.verbose,
#                                 markdown=True
#                             )

#                             # get the loop data convert it to list using calling Agent class chat
#                             loop_prompt = f"""
# Process this data into a list format:
# {prev_task.result.raw}

# Return a JSON object with an 'items' array containing the items to process.
# """
#                             if current_task.async_execution:
#                                 loop_data_str = await loop_manager.achat(
#                                     prompt=loop_prompt,
#                                     output_json=LoopItems
#                                 )
#                             else:
#                                 loop_data_str = loop_manager.chat(
#                                     prompt=loop_prompt,
#                                     output_json=LoopItems
#                                 )
                            
#                             try:
#                                 # The response will already be parsed into LoopItems model
#                                 loop_data[f"loop_{current_task.name}"] = {
#                                     "items": loop_data_str.items,
#                                     "index": 0,
#                                     "remaining": len(loop_data_str.items)
#                                 }
#                                 context += f"\nCurrent loop item: {loop_data_str.items[0]}"
#                             except Exception as e:
#                                 display_error(f"Failed to process loop data: {e}")
#                                 context += f"\n{prev_name}: {prev_task.result.raw}"
                            context += f"\n{prev_name}: {prev_task.result.raw}"
                        else:
                            context += f"\n{prev_name}: {prev_task.result.raw}"
                
                # Add data from context tasks
                if current_task.context:
                    for ctx_task in current_task.context:
                        if ctx_task.result and ctx_task.name != current_task.name:
                            context += f"\n{ctx_task.name}: {ctx_task.result.raw}"
                
                # Update task description with context
                current_task.description = current_task.description + context
            
            # Execute task using existing run_task method
            yield task_id
            visited_tasks.add(task_id)
            
            # Reset completed task to "not started" so it can run again
            if self.tasks[task_id].status == "completed":
                logging.debug(f"Task {task_id} was completed, resetting to 'not started' for next iteration.")
                self.tasks[task_id].status = "not started"
            
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
                    # MINIMAL CHANGE: use pydantic decision if present
                    decision_str = current_task.result.raw.lower()
                    if current_task.result.pydantic and hasattr(current_task.result.pydantic, "decision"):
                        decision_str = current_task.result.pydantic.decision.lower()

                    # Check conditions
                    for condition, tasks in current_task.condition.items():
                        if condition.lower() == decision_str:
                            # Handle both list and direct string values
                            task_value = tasks[0] if isinstance(tasks, list) else tasks
                            if not task_value or task_value == "exit":
                                logging.info("Workflow exit condition met, ending workflow")
                                current_task = None
                                break
                            next_task_name = task_value
                            next_task = next((t for t in self.tasks.values() if t.name == next_task_name), None)
                            # For loops, allow revisiting the same task
                            if next_task and next_task.id == current_task.id:
                                visited_tasks.discard(current_task.id)
                            break
            
            if not next_task and current_task and current_task.next_tasks:
                next_task_name = current_task.next_tasks[0]
                next_task = next((t for t in self.tasks.values() if t.name == next_task_name), None)
            
            current_task = next_task
            if not current_task:
                logging.info("Workflow execution completed")
                break

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
                    manager_response = await client.beta.chat.completions.parse(
                        model=self.manager_llm,
                        messages=[
                            {"role": "system", "content": manager_task.description},
                            {"role": "user", "content": manager_prompt}
                        ],
                        temperature=0.7,
                        response_format=ManagerInstructions
                    )
                else:
                    manager_response = client.beta.chat.completions.parse(
                        model=self.manager_llm,
                        messages=[
                            {"role": "system", "content": manager_task.description},
                            {"role": "user", "content": manager_prompt}
                        ],
                        temperature=0.7,
                        response_format=ManagerInstructions
                    )
                parsed_instructions = manager_response.choices[0].message.parsed
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
                    # existing CSV reading logic
                    with open(start_task.input_file, "r", encoding="utf-8") as f:
                        # Try as simple CSV first
                        reader = csv.reader(f)
                        previous_task = None
                        for i, row in enumerate(reader):
                            if row:  # Skip empty rows
                                task_desc = row[0]  # Take first column
                                row_task = Task(
                                    description=task_desc,  # Keep full row as description
                                    agent=start_task.agent,
                                    name=task_desc,       # Use first column as name
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
                    # If not CSV, read lines
                    with open(start_task.input_file, "r", encoding="utf-8") as f:
                        lines = f.read().splitlines()
                        previous_task = None
                        for i, line in enumerate(lines):
                            row_task = Task(
                                description=line.strip(),
                                agent=start_task.agent,
                                name=line.strip(),
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

        # end of the new block
        current_task = start_task
        visited_tasks = set()
        loop_data = {}  # Store loop-specific data
        
        while current_task:
            current_iter += 1
            if current_iter > self.max_iter:
                logging.info(f"Max iteration limit {self.max_iter} reached, ending workflow.")
                break

            task_id = current_task.id
            logging.info(f"Executing workflow task: {current_task.name if current_task.name else task_id}")
            
            # Add context from previous tasks to description
            if current_task.previous_tasks or current_task.context:
                context = "\nInput data from previous tasks:"
                
                # Add data from previous tasks in workflow
                for prev_name in current_task.previous_tasks:
                    prev_task = next((t for t in self.tasks.values() if t.name == prev_name), None)
                    if prev_task and prev_task.result:
                        # Handle loop data
                        if current_task.task_type == "loop":
#                             # create a loop manager Agent
#                             loop_manager = Agent(
#                                 name="Loop Manager",
#                                 role="Loop data processor",
#                                 goal="Process loop data and convert it to list format",
#                                 backstory="Expert at handling loop data and converting it to proper format",
#                                 llm=self.manager_llm,
#                                 verbose=self.verbose,
#                                 markdown=True
#                             )

#                             # get the loop data convert it to list using calling Agent class chat
#                             loop_prompt = f"""
# Process this data into a list format:
# {prev_task.result.raw}

# Return a JSON object with an 'items' array containing the items to process.
# """
#                             loop_data_str = loop_manager.chat(
#                                 prompt=loop_prompt,
#                                 output_json=LoopItems
#                             )
                            
#                             try:
#                                 # The response will already be parsed into LoopItems model
#                                 loop_data[f"loop_{current_task.name}"] = {
#                                     "items": loop_data_str.items,
#                                     "index": 0,
#                                     "remaining": len(loop_data_str.items)
#                                 }
#                                 context += f"\nCurrent loop item: {loop_data_str.items[0]}"
#                             except Exception as e:
#                                 display_error(f"Failed to process loop data: {e}")
#                                 context += f"\n{prev_name}: {prev_task.result.raw}"
                            context += f"\n{prev_name}: {prev_task.result.raw}"
                        else:
                            context += f"\n{prev_name}: {prev_task.result.raw}"
                
                # Add data from context tasks
                if current_task.context:
                    for ctx_task in current_task.context:
                        if ctx_task.result and ctx_task.name != current_task.name:
                            context += f"\n{ctx_task.name}: {ctx_task.result.raw}"
                
                # Update task description with context
                current_task.description = current_task.description + context
            
            # Execute task using existing run_task method
            yield task_id
            visited_tasks.add(task_id)
            
            # Reset completed task to "not started" so it can run again: Only for workflow because some tasks may be revisited
            if self.tasks[task_id].status == "completed":
                logging.debug(f"Task {task_id} was completed, resetting to 'not started' for next iteration.")
                self.tasks[task_id].status = "not started"
            
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
                    # MINIMAL CHANGE: use pydantic decision if present
                    decision_str = current_task.result.raw.lower()
                    if current_task.result.pydantic and hasattr(current_task.result.pydantic, "decision"):
                        decision_str = current_task.result.pydantic.decision.lower()

                    # Check conditions
                    for condition, tasks in current_task.condition.items():
                        if condition.lower() == decision_str:
                            # Handle both list and direct string values
                            task_value = tasks[0] if isinstance(tasks, list) else tasks
                            if not task_value or task_value == "exit":
                                logging.info("Workflow exit condition met, ending workflow")
                                current_task = None
                                break
                            next_task_name = task_value
                            next_task = next((t for t in self.tasks.values() if t.name == next_task_name), None)
                            # For loops, allow revisiting the same task
                            if next_task and next_task.id == current_task.id:
                                visited_tasks.discard(current_task.id)
                            break
            
            if not next_task and current_task and current_task.next_tasks:
                next_task_name = current_task.next_tasks[0]
                next_task = next((t for t in self.tasks.values() if t.name == next_task_name), None)
            
            current_task = next_task
            if not current_task:
                logging.info("Workflow execution completed")
                break

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
                manager_response = client.beta.chat.completions.parse(
                    model=self.manager_llm,
                    messages=[
                        {"role": "system", "content": manager_task.description},
                        {"role": "user", "content": manager_prompt}
                    ],
                    temperature=0.7,
                    response_format=ManagerInstructions
                )
                parsed_instructions = manager_response.choices[0].message.parsed
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