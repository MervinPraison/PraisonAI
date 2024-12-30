import os
import time
import json
import logging
from typing import Any, Dict, Optional
from pydantic import BaseModel
from rich.text import Text
from rich.panel import Panel
from rich.console import Console
from ..main import display_error, TaskOutput, error_logs, client
from ..agent.agent import Agent
from ..task.task import Task

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
    def __init__(self, agents, tasks, verbose=0, completion_checker=None, max_retries=5, process="sequential", manager_llm=None):
        self.agents = agents
        self.tasks = {}
        if max_retries < 3:
            max_retries = 3
        self.completion_checker = completion_checker if completion_checker else self.default_completion_checker
        self.task_id_counter = 0
        self.verbose = verbose
        self.max_retries = max_retries
        self.process = process
        if not manager_llm:
            logging.debug("No manager_llm provided. Using OPENAI_MODEL_NAME environment variable or defaulting to 'gpt-4o'")
        self.manager_llm = manager_llm if manager_llm else os.getenv('OPENAI_MODEL_NAME', 'gpt-4o')
        for task in tasks:
            self.add_task(task)
            task.status = "not started"

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

    def execute_task(self, task_id):
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

        task_prompt = f"""
You need to do the following task: {task.description}.
Expected Output: {task.expected_output}.
        """
        if task.context:
            context_results = ""
            for context_task in task.context:
                if context_task.result:
                    context_results += f"Result of previous task {context_task.name if context_task.name else context_task.description}: {context_task.result.raw}\n"
                else:
                    context_results += f"Previous task {context_task.name if context_task.name else context_task.description} had no result.\n"
            task_prompt += f"""
            Here are the results of previous tasks that might be useful:\n
            {context_results}
            """
        task_prompt += "Please provide only the final result of your work. Do not add any conversation or extra explanation."

        if self.verbose >= 2:
            logging.info(f"Executing task {task_id}: {task.description} using {executor_agent.name}")
        logging.debug(f"Starting execution of task {task_id} with prompt:\n{task_prompt}")

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
                tools=task.tools
            )
        else:
            agent_output = executor_agent.chat(task_prompt, tools=task.tools)

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
                    logging.warning(f"Warning: Could not parse output of task {task_id} as JSON")
                    logging.debug(f"Output that failed JSON parsing: {agent_output}")

            if task.output_pydantic:
                cleaned = self.clean_json_output(agent_output)
                try:
                    parsed = json.loads(cleaned)
                    pyd_obj = task.output_pydantic(**parsed)
                    task_output.pydantic = pyd_obj
                    task_output.output_format = "Pydantic"
                except:
                    logging.warning(f"Warning: Could not parse output of task {task_id} as Pydantic Model")
                    logging.debug(f"Output that failed Pydantic parsing: {agent_output}")

            task.result = task_output
            return task_output
        else:
            task.status = "failed"
            return None

    def save_output_to_file(self, task, task_output):
        if task.output_file:
            try:
                if task.create_directory:
                    os.makedirs(os.path.dirname(task.output_file), exist_ok=True)
                with open(task.output_file, "w") as f:
                    f.write(str(task_output))
                if self.verbose >= 1:
                    logging.info(f"Task output saved to {task.output_file}")
            except Exception as e:
                display_error(f"Error saving task output to file: {e}")

    def run_task(self, task_id):
        if task_id not in self.tasks:
            display_error(f"Error: Task with ID {task_id} does not exist")
            return
        task = self.tasks[task_id]
        if task.status == "completed":
            logging.info(f"Task with ID {task_id} is already completed")
            return

        retries = 0
        while task.status != "completed" and retries < self.max_retries:
            logging.debug(f"Attempt {retries+1} for task {task_id}")
            if task.status in ["not started", "in progress"]:
                task_output = self.execute_task(task_id)
                if task_output and self.completion_checker(task, task_output.raw):
                    task.status = "completed"
                    if task.callback:
                        task.callback(task_output)
                    self.save_output_to_file(task, task_output)
                    if self.verbose >= 1:
                        logging.info(f"Task {task_id} completed successfully.")
                else:
                    task.status = "in progress"
                    if self.verbose >= 1:
                        logging.info(f"Task {task_id} not completed, retrying")
                    time.sleep(1)
                    retries += 1
            else:
                if task.status == "failed":
                    logging.info("Task is failed, resetting to in-progress for another try...")
                    task.status = "in progress"
                else:
                    logging.info("Invalid Task status")
                    break

        if retries == self.max_retries and task.status != "completed":
            logging.info(f"Task {task_id} failed after {self.max_retries} retries.")

    def run_all_tasks(self):
        if self.process == "sequential":
            for task_id in self.tasks:
                if self.tasks[task_id].status != "completed":
                    self.run_task(task_id)
        elif self.process == "hierarchical":
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
            manager_task_id = self.add_task(manager_task)
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
                    self.run_task(selected_task_id)
                    logging.info(f"Finished execution of task {selected_task_id}, status: {self.tasks[selected_task_id].status}")

                if self.tasks[selected_task_id].status == "completed":
                    completed_count += 1
                    logging.info(f"Task {selected_task_id} completed. Total completed: {completed_count}/{total_tasks}")

            self.tasks[manager_task.id].status = "completed"
            if self.verbose >= 1:
                logging.info("All tasks completed under manager supervision.")
            logging.info("Hierarchical task execution finished")

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

    def start(self):
        self.run_all_tasks()
        return {
            "task_status": self.get_all_tasks_status(),
            "task_results": {task_id: self.get_task_result(task_id) for task_id in self.tasks}
        } 