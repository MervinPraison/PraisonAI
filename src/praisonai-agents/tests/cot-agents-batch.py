from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import cot_save, cot_upload_to_huggingface

# Create a COT agent for generating and managing chain of thought solutions
cot_agent = Agent(
    name="COTGenerator",
    role="Chain of Thought Specialist",
    goal="Generate and manage chain of thought solutions for Q&A pairs",
    backstory="Expert in breaking down problems and generating detailed solution steps",
    tools=[cot_save],
    llm="gpt-4o-mini",  # Using recommended model
)

save_to_huggingface_agent = Agent(
    name="SaveToHuggingface",
    role="Save to Huggingface",
    goal="Save the generated chain of thought solutions to a Huggingface dataset",
    backstory="Expert in saving data to Huggingface",
    tools=[cot_upload_to_huggingface],
    llm="gpt-4o-mini",  # Using recommended model
)

# Define question-answer pairs to process in batches
qa_pairs = [
    {
        "question": "What is the sum of numbers from 1 to 10?",
        "answer": "55"
    },
    {
        "question": "Calculate the area of a circle with radius 5",
        "answer": "78.54"
    }
]

# Process qa_pairs in batches
batch_size = 2
for i in range(0, len(qa_pairs), batch_size):
    batch_qa = qa_pairs[i:i + batch_size]
    
    # Create task for current batch
    qa_text = "\n".join(
        f"- Q: {qa['question']}\n  A: {qa['answer']}" 
        for qa in batch_qa
    )
    
    cot_task = Task(
        description=(
            "For each Q&A pair:\n"
            "1. Use the tool cot_save to generate a chain of thought solution\n"
            "2. Save to CSV file with filename 'cot_dataset.csv'\n\n"
            f"Q&A Pairs:\n{qa_text}"
        ),
        expected_output="Chain of thought solutions saved to CSV",
        agent=cot_agent,
        name=f"generate_cot_solutions_batch_{i//batch_size + 1}"
    )

    save_to_huggingface_task = Task(
        description="Save to Huggingface dataset at mervinpraison/cot-dataset , cot_dataset.csv",
        expected_output="Chain of thought solutions saved to Huggingface",
        agent=save_to_huggingface_agent,
        name=f"save_to_huggingface_batch_{i//batch_size + 1}"
    )

    # Initialize and run the agent
    agents = PraisonAIAgents(
        agents=[cot_agent, save_to_huggingface_agent],
        tasks=[cot_task, save_to_huggingface_task]
    )

    # Execute current batch
    result = agents.start()
    print(f"\nBatch {i//batch_size + 1} completed. Solutions appended to CSV file.")
