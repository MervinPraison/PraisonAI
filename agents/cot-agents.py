from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import cot_save, cot_upload_to_huggingface, write_csv

# Keep existing agents with minimal changes
qa_generator = Agent(
    name="Generator",
    role="Question Creator",
    goal="Create challenging math and logic questions",
    backstory="Expert in educational content creation",
    llm="gpt-4o-mini",
    tools=[write_csv]
)

cot_generator = Agent(
    name="COTGenerator",
    role="Chain of Thought Specialist",
    goal="Generate and manage chain of thought solutions for Q&A pairs",
    backstory="Expert in breaking down problems and generating detailed solution steps",
    tools=[cot_save],
    llm="gpt-4o-mini"
)

upload_to_huggingface = Agent(
    name="UploadToHuggingface",
    role="Upload to Huggingface",
    goal="Upload the generated chain of thought solutions to a Huggingface dataset",
    backstory="Expert in saving data to Huggingface",
    tools=[cot_upload_to_huggingface],
    llm="gpt-4o-mini"
)

# Define tasks with workflow improvements
generate_task = Task(
    description="Generate math questions in csv format without headers: question, answer and append to qa_pairs.csv file",
    expected_output="append to qa_pairs.csv file with questions and answers",
    agent=qa_generator,
    is_start=True,
    next_tasks=["generate_cot"]
)

generate_cot_task = Task(
    name="generate_cot",
    description="Generate chain of thought solutions for the qa pair",
    expected_output="Chain of thought solutions",
    agent=cot_generator,
    context=[generate_task],
    condition={
        "more": ["generate_cot"],
        "done": ["upload_to_huggingface"]
    }
)

upload_to_huggingface_task = Task(
    name="upload_to_huggingface",
    description="""Upload to Huggingface:
    1. Save to cot_dataset.csv
    2. Upload to mervinpraison/cot-dataset""",
    expected_output="Dataset published successfully",
    agent=upload_to_huggingface,
    tools=[cot_upload_to_huggingface]
)

# Initialize workflow
agents = PraisonAIAgents(
    agents=[qa_generator, cot_generator, upload_to_huggingface],
    tasks=[generate_task, generate_cot_task, upload_to_huggingface_task],
    process="workflow",
    verbose=True
)

results = agents.start()

# Print results
print("\nGenerated QA Pairs:")
for task_id, result in results["task_results"].items():
    if result and task_id == "generate":
        print(result.raw)
