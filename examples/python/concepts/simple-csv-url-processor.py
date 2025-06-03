"""
Simple CSV URL Processor

This example directly addresses the GitHub issue #23:
"Is it possible to pass in a CSV list of URLs and have agents work through the list each in turn?"

This is the simplest possible implementation for processing URLs from a CSV file.

Author: Generated for GitHub Issue #23
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import write_csv

def create_url_csv():
    """Create a CSV file with URLs to process"""
    # Example URLs - replace with your own
    urls = [
        {"url": "https://example.com"},
        {"url": "https://github.com"},
        {"url": "https://stackoverflow.com"},
        {"url": "https://python.org"}
    ]
    
    write_csv("urls_to_process.csv", urls)
    print("✅ Created urls_to_process.csv")
    return "urls_to_process.csv"

def main():
    """
    Simple CSV URL processing example
    
    This shows the easiest way to process a CSV list of URLs
    where agents work through the list sequentially.
    """
    print("Simple CSV URL Processor")
    print("=" * 40)
    
    # Step 1: Create the CSV file (or use your existing one)
    csv_file = create_url_csv()
    
    # Step 2: Create an agent to process URLs
    url_agent = Agent(
        name="URLProcessor", 
        role="URL Analyzer",
        goal="Analyze each URL from the CSV list",
        backstory="Expert at analyzing websites and URLs",
        instructions="Analyze each URL and provide insights about the website",
        llm="gpt-4o-mini"  # You can change this to any supported model
    )
    
    # Step 3: Create a task that will loop through the CSV
    url_task = Task(
        description="Analyze each URL from the CSV file and provide insights",
        expected_output="Analysis of the website at each URL",
        agent=url_agent,
        task_type="loop",        # This tells PraisonAI to loop through CSV rows
        input_file=csv_file      # Your CSV file with URLs
    )
    
    # Step 4: Run the agents
    agents = PraisonAIAgents(
        agents=[url_agent],
        tasks=[url_task],
        process="workflow",
        max_iter=10  # Adjust based on how many URLs you have
    )
    
    print(f"🚀 Processing URLs from {csv_file}")
    print("The agent will work through each URL in turn...")
    
    agents.start()
    
    print("✅ Finished processing all URLs!")

if __name__ == "__main__":
    main()