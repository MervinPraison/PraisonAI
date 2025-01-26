from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import cot_save

# Create a COT agent for generating and managing chain of thought solutions
cot_agent = Agent(
    name="COTGenerator",
    role="Chain of Thought Specialist",
    goal="Generate and manage chain of thought solutions for Q&A pairs",
    backstory="Expert in breaking down problems and generating detailed solution steps",
    tools=[cot_save],
    verbose=True,
    llm="gpt-4o-mini",  # Using recommended model
)

# Define question-answer pairs to process in batches
qa_pairs = [
    {
        "question": "What is the sum of numbers from 1 to 10?",
        "answer": "The sum is 55. Steps: 1+2+3+4+5+6+7+8+9+10 = 55"
    },
    {
        "question": "Calculate the area of a circle with radius 5",
        "answer": "Area = πr². With r=5, Area = π(5)² = 78.54 square units"
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
            "1. Generate chain of thought solution\n"
            "2. Create a dictionary with Q&A pair and solution\n"
            "3. Use this dictionary to append solutions to CSV\n\n"
            f"Q&A Pairs:\n{qa_text}"
        ),
        expected_output="Chain of thought solutions appended to CSV",
        agent=cot_agent,
        name=f"generate_cot_solutions_batch_{i//batch_size + 1}"
    )

    # Initialize and run the agent
    agents = PraisonAIAgents(
        agents=[cot_agent],
        tasks=[cot_task]
    )

    # Execute current batch
    result = agents.start()
    print(f"\nBatch {i//batch_size + 1} completed. Solutions appended to CSV file.")
