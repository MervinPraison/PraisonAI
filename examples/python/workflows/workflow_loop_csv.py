"""
Agentic Loop with CSV Workflow Example

Demonstrates iterating over a CSV file with an agent processing each row.
"""

from praisonaiagents import Agent, Workflow
from praisonaiagents.workflows import loop
import tempfile
import os

# Create sample CSV file content
csv_content = """topic,description
AI Ethics,Ethical considerations in artificial intelligence
Machine Learning,Algorithms that learn from data
Neural Networks,Computing systems inspired by biological neural networks
Natural Language Processing,AI understanding human language"""

# Create processor agent
processor = Agent(
    name="TopicProcessor",
    role="Topic Analyst",
    goal="Analyze and explain topics",
    instructions="Provide a brief, insightful analysis of the given topic."
)

# Create summarizer agent
summarizer = Agent(
    name="Summarizer",
    role="Results Summarizer",
    goal="Summarize all processed results",
    instructions="Create a comprehensive summary of all the analyzed topics."
)

if __name__ == "__main__":
    # Create temp CSV file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(csv_content)
        csv_path = f.name
    
    try:
        print("=== Testing Agentic Loop with CSV ===\n")
        print(f"Processing CSV: {csv_path}\n")
        
        # Create workflow with loop over CSV
        workflow = Workflow(
            name="CSV Topic Processor",
            steps=[
                loop(processor, from_csv=csv_path),
                summarizer
            ]
        )
        
        result = workflow.start("Analyze these AI topics", verbose=True)
        
        print(f"\nFinal Summary:\n{result['output']}")
        
    finally:
        os.unlink(csv_path)
