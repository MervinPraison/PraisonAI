from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import read_csv, write_csv
import pandas as pd

def read_csv_smart(csv_path: str) -> pd.DataFrame:
    """Read CSV and use first column as task, handling both header/no-header cases"""
    # Try reading with headers first
    df = pd.read_csv(csv_path)
    
    # Check if first row looks like data
    if not any(col.lower() in ['task', 'description', 'status', 'state'] for col in df.columns):
        # If no header-like names found, read without headers
        df = pd.read_csv(csv_path, header=None)
        
    # Rename columns consistently
    df.columns = [*['task'], *[f'col_{i}' for i in range(1, len(df.columns))]]
    if 'status' not in df.columns:
        df['status'] = 'pending'
    if 'loop_id' not in df.columns:
        # Start loop_id from 1 instead of 0
        df['loop_id'] = (df.index + 1).astype(str)
    return df[['task', 'status', 'loop_id']]

def has_pending_tasks(df: pd.DataFrame) -> bool:
    """Check if there are any pending tasks in the DataFrame"""
    return not df[df['status'] == 'pending'].empty

def check_task_status(csv_path: str) -> dict:
    """Read task status from CSV file"""
    try:
        # Always read directly from CSV file
        df = pd.read_csv(csv_path, keep_default_na=False)
        
        # Get only pending tasks from original status
        pending_tasks = df[df['status'].str.lower() == 'pending']
        
        if not pending_tasks.empty:
            task_data = pending_tasks.iloc[0].to_dict()
            return {
                'has_pending': True,
                'next_task': task_data
            }
        return {'has_pending': False, 'next_task': None}
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return {'has_pending': False, 'next_task': None, 'error': str(e)}

def get_next_task() -> dict:
    """Get the next pending task from CSV"""
    status = check_task_status("tasks.csv")
    if status['has_pending'] and status['next_task']:
        task = status['next_task']
        if task['status'].lower() == 'pending':
            return {
                'loop_data': {
                    'task': task['task'],
                    'loop_id': task['loop_id'],
                    'status': task['status']
                }
            }
    return None

def update_task_status(loop_id: str, new_status: str) -> bool:
    """Update task status in CSV file using loop_id as identifier"""
    try:
        # Read directly from CSV file
        df = pd.read_csv("tasks.csv", keep_default_na=False)
        df['loop_id'] = df['loop_id'].astype(str)
        mask = df['loop_id'] == str(loop_id)
        if mask.any():
            df.loc[mask, 'status'] = new_status
            df.to_csv("tasks.csv", index=False)
            return True
        print(f"No task found with loop_id: {loop_id}")
        return False
    except Exception as e:
        print(f"Error updating status: {e}")
        return False

identify_agent = Agent(
    name="Identify Agent",
    role="Pending Task Identifier",
    goal="Identify the next pending task",
    tools=[get_next_task],
    llm="gpt-4o-mini"
)

# Create the repetitive agent
repetitive_agent = Agent(
    name="TaskProcessor",
    role="Task Processing Specialist",
    goal="Complete the task response",
    llm="gpt-4o-mini"
)

update_status_agent = Agent(
    name="UpdateStatusAgent",
    role="Status Updater",
    goal="Update the status of the task in CSV",
    tools=[update_task_status],
    llm="gpt-4o-mini"
)

# Define the repetitive task
identify_task = Task(
    name="identify_task",
    description="Identify the next pending task. If there are no pending tasks decision is completed.",
    agent=identify_agent,
    task_type="loop",
    condition={
        "pending": ["process_task"],
        "completed": "exit"
    }
)

process_task = Task(
    name="process_task",
    description="Complete the task mentioned in the response",
    agent=repetitive_agent,
    context=[identify_task],
    task_type="loop",
    next_tasks=["update_task"]
)

update_task = Task(
    name="update_task",
    description="Update the task status",
    agent=update_status_agent,
    next_tasks= ["identify_task"]
)

# Create and run agents manager
agents = PraisonAIAgents(
    agents=[identify_agent, repetitive_agent],
    tasks=[identify_task, process_task, update_task],
    process="workflow"
)

agents.start()