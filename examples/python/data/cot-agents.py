from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import cot_save, cot_upload_to_huggingface
from pydantic import BaseModel
import os

# Define Pydantic model for structured output
class DecisionModel(BaseModel):
    response: str
    decision: str

def write_csv(file_path, data):
    """Write data to CSV file."""
    if not os.path.exists(file_path):
        with open(file_path, 'w') as file:
            file.write(data + '\n')
    else:
        with open(file_path, 'a') as file:
            file.write(data + '\n')
    return f"Data appended to {file_path}"

def count_questions(file_path):
    """Count lines in file."""
    with open(file_path, 'r') as file:
        return sum(1 for _ in file)

# Keep existing agents with minimal changes
qa_generator = Agent(
    name="Generator",
    role="Question Creator",
    goal="Create challenging math and logic questions",
    backstory="Expert in educational content creation",
    llm="gpt-4o-mini",
    tools=[write_csv, count_questions]
)

total_questions_evaluator = Agent(
    name="TotalQuestionsEvaluator",
    role="Total Questions Evaluator",
    goal="Evaluate the total number of questions in qa_pairs.csv file",
    backstory="Expert in evaluating the total number of questions in a file",
    llm="gpt-4o-mini",
    tools=[count_questions],
    verbose=False
)

cot_generator = Agent(
    name="COTGenerator",
    role="Chain of Thought Specialist",
    goal="Generate and manage chain of thought solutions for Q&A pairs",
    backstory="Expert in breaking down problems and generating detailed solution steps",
    tools=[cot_save],
    llm="gpt-4o-mini",
    verbose=False
)

upload_to_huggingface = Agent(
    name="UploadToHuggingface",
    role="Upload to Huggingface",
    goal="Upload the generated chain of thought solutions to a Huggingface dataset",
    backstory="Expert in saving data to Huggingface",
    tools=[cot_upload_to_huggingface],
    llm="gpt-4o-mini",
    verbose=False
)

# Define tasks with workflow improvements
generate_task = Task(
    description="""Generate question and answer in csv format without headers: question, answer and append to qa_pairs.csv file
generate 10 unique questions and answers and don't repeat on the same question and answer. Reponse with 'done' when done
with append mode as 'a'
Example question and answer:
question, answer
What is the sum of numbers from 1 to 10?, 55
Number of r's in the word strawberry, 3
""",
    expected_output="append to qa_pairs.csv file with questions and answers and move to next task",
    agent=qa_generator,
    name="generate_task",
    is_start=True,
    next_tasks=["evaluate_total_questions"],
    task_type="decision",
    condition={
        "more": "generate_task",
        "done": "evaluate_total_questions"
    }
)

evaluate_total_questions_task = Task(
    description="Evaluate the total number of questions in qa_pairs.csv file is 1",
    expected_output="Total number of questions in qa_pairs.csv file",
    agent=total_questions_evaluator,
    task_type="decision",
    name="evaluate_total_questions",
    condition={
        "more": "generate_task",
        "done": "generate_cot"
    }
)

generate_cot_task = Task(
    name="generate_cot",
    description="""Generate chain of thought solutions for each question in the input file. 
Save to cot_solutions.csv file
Don't generate chain of thought solutions again after receiving the response from Tool Call
After calling the tool, respond with a JSON object:
{
    "response": "done",
    "decision": "done"
}
""",
    expected_output="done",
    agent=cot_generator,
    input_file="qa_pairs.csv",
    task_type="loop",
    next_tasks=["upload_to_huggingface"],
    condition={
        "done": ["upload_to_huggingface"],
        "exit": [],
    },
    output_pydantic=DecisionModel  # Use Pydantic model for output validation
)

upload_to_huggingface_task = Task(
    name="upload_to_huggingface",
    description="""Upload to Huggingface:
    1. Save to cot_solutions.csv
    2. Upload to mervinpraison/cot-dataset""",
    expected_output="Dataset published successfully",
    agent=upload_to_huggingface,
    tools=[cot_upload_to_huggingface]
)

# Initialize workflow
agents = PraisonAIAgents(
    agents=[qa_generator, total_questions_evaluator, cot_generator, upload_to_huggingface],
    tasks=[generate_task, evaluate_total_questions_task, generate_cot_task, upload_to_huggingface_task],
    process="workflow",
    max_iter=30,
    verbose=False
)

agents.start()