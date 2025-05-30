"""
CSV Processing with PraisonAI Agents

This example demonstrates multiple ways to process CSV files with agents:
1. Simple CSV Loop Processing (easiest)
2. Manual CSV Processing with read_csv tools
3. URL Processing from CSV files
4. Custom CSV Processing with validation

Author: Generated for GitHub Issue #23
"""

import os
from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import read_csv, write_csv

def create_sample_urls_csv():
    """Create a sample CSV file with URLs for testing"""
    urls_data = [
        {"id": 1, "url": "https://example.com", "description": "Example website"},
        {"id": 2, "url": "https://github.com", "description": "GitHub platform"},
        {"id": 3, "url": "https://stackoverflow.com", "description": "Stack Overflow Q&A"},
        {"id": 4, "url": "https://python.org", "description": "Python official site"},
        {"id": 5, "url": "https://docs.python.org", "description": "Python documentation"}
    ]
    
    # Ensure the CSV file exists
    write_csv("sample_urls.csv", urls_data)
    print("✅ Created sample_urls.csv with 5 URLs")
    return "sample_urls.csv"

def create_sample_tasks_csv():
    """Create a sample CSV file with tasks for loop processing"""
    tasks_data = [
        {"task": "Analyze the homepage of example.com and summarize its content"},
        {"task": "Check if github.com is accessible and describe its main features"},
        {"task": "Research what Stack Overflow is used for"},
        {"task": "Summarize the key features of Python programming language"},
        {"task": "Describe what you can find in Python documentation"}
    ]
    
    write_csv("sample_tasks.csv", tasks_data)
    print("✅ Created sample_tasks.csv with 5 tasks")
    return "sample_tasks.csv"

# ==============================================================================
# METHOD 1: SIMPLE CSV LOOP PROCESSING (RECOMMENDED FOR BEGINNERS)
# ==============================================================================

def method_1_simple_loop():
    """
    The easiest way to process CSV files with PraisonAI agents.
    
    This method automatically loops through each row in your CSV file.
    Each row becomes input for the agent to process.
    """
    print("\n" + "="*60)
    print("METHOD 1: Simple CSV Loop Processing")
    print("="*60)
    
    # Create sample CSV file
    csv_file = create_sample_tasks_csv()
    
    # Create an agent that will process each row
    loop_agent = Agent(
        name="CSVLoopProcessor",
        role="CSV Task Processor",
        goal="Process each task from the CSV file efficiently",
        backstory="Expert at handling repetitive tasks from CSV data",
        instructions="Process each task thoroughly and provide detailed output",
        llm="gpt-4o-mini"
    )
    
    # Create a loop task that will automatically process each CSV row
    loop_task = Task(
        description="Process each task from the CSV file",
        expected_output="Completed task with detailed results",
        agent=loop_agent,
        task_type="loop",           # This enables CSV loop processing
        input_file=csv_file         # The CSV file to process
    )
    
    # Initialize the agents system
    agents = PraisonAIAgents(
        agents=[loop_agent],
        tasks=[loop_task],
        process="workflow",
        max_iter=10                 # Maximum iterations to prevent infinite loops
    )
    
    print(f"🚀 Starting loop processing of {csv_file}")
    print("Each row will be processed as a separate task...")
    
    # Start processing
    agents.start()

# ==============================================================================
# METHOD 2: MANUAL CSV PROCESSING WITH TOOLS
# ==============================================================================

def method_2_manual_csv():
    """
    Manual CSV processing using built-in CSV tools.
    
    This gives you more control over how the CSV is processed,
    including validation, filtering, and custom logic.
    """
    print("\n" + "="*60)
    print("METHOD 2: Manual CSV Processing with Tools")
    print("="*60)
    
    # Create sample CSV file
    csv_file = create_sample_urls_csv()
    
    # Create an agent with CSV tools
    csv_agent = Agent(
        name="CSVAnalyzer",
        role="CSV Data Processor",
        goal="Read, validate, and process CSV data manually",
        backstory="Specialist in data validation and processing",
        tools=[read_csv, write_csv],
        instructions="""
        You are an expert at processing CSV files. When given a CSV file:
        1. Read the CSV file using read_csv tool
        2. Validate the data structure
        3. Process each row according to the requirements
        4. Create a summary of the processing results
        5. Save results to a new CSV file if needed
        """,
        llm="gpt-4o-mini"
    )
    
    # Create a task for manual CSV processing
    csv_task = Task(
        description=f"""
        Process the CSV file '{csv_file}' manually:
        1. Read the CSV file using the read_csv tool
        2. Validate that it contains 'url' and 'description' columns
        3. For each URL, describe what type of website it is
        4. Create a summary report of all URLs processed
        5. Save the results to 'processed_urls.csv'
        """,
        expected_output="A detailed report of CSV processing with validation results",
        agent=csv_agent
    )
    
    # Initialize and run
    agents = PraisonAIAgents(
        agents=[csv_agent],
        tasks=[csv_task],
        process="sequential"
    )
    
    print(f"🚀 Starting manual processing of {csv_file}")
    agents.start()

# ==============================================================================
# METHOD 3: URL PROCESSING FROM CSV (SPECIFIC TO ISSUE REQUEST)
# ==============================================================================

def method_3_url_processing():
    """
    Specific example for processing URLs from CSV files.
    
    This addresses the original question about processing a CSV list of URLs
    where agents work through the list sequentially.
    """
    print("\n" + "="*60)
    print("METHOD 3: URL Processing from CSV Files")
    print("="*60)
    
    # Create sample CSV file with URLs
    csv_file = create_sample_urls_csv()
    
    # Create a URL processing agent
    url_agent = Agent(
        name="URLProcessor",
        role="Website Analyzer",
        goal="Analyze websites from CSV URL list",
        backstory="Expert web analyst who can evaluate websites",
        tools=[read_csv, write_csv],
        instructions="""
        You are a website analysis expert. When given a CSV with URLs:
        1. Read the CSV file to get the list of URLs
        2. For each URL, analyze what kind of website it is
        3. Determine the purpose and main features of each site
        4. Create a detailed analysis report
        5. Save results with analysis data
        """,
        llm="gpt-4o-mini"
    )
    
    # Create the URL processing task
    url_task = Task(
        description=f"""
        Process URLs from '{csv_file}':
        1. Read the CSV file containing URLs and descriptions
        2. For each URL in the list, provide an analysis of:
           - What type of website it is
           - Its main purpose and features
           - Target audience
           - Key characteristics
        3. Work through the URLs sequentially (one by one)
        4. Create a comprehensive report with all analyses
        5. Save the results to 'url_analysis_results.csv'
        
        Make sure to process each URL individually and thoroughly.
        """,
        expected_output="Detailed analysis of each URL with comprehensive results saved to CSV",
        agent=url_agent
    )
    
    # Initialize and run
    agents = PraisonAIAgents(
        agents=[url_agent],
        tasks=[url_task],
        process="sequential"
    )
    
    print(f"🚀 Starting URL processing from {csv_file}")
    print("URLs will be processed sequentially...")
    agents.start()

# ==============================================================================
# METHOD 4: ADVANCED CSV PROCESSING WITH VALIDATION
# ==============================================================================

def method_4_advanced_processing():
    """
    Advanced CSV processing with data validation and error handling.
    
    This method shows how to handle complex CSV processing scenarios
    with validation, error handling, and structured outputs.
    """
    print("\n" + "="*60)
    print("METHOD 4: Advanced CSV Processing with Validation")
    print("="*60)
    
    # Create a more complex CSV file
    complex_data = [
        {"id": 1, "url": "https://example.com", "priority": "high", "category": "test"},
        {"id": 2, "url": "https://github.com", "priority": "medium", "category": "development"},
        {"id": 3, "url": "invalid-url", "priority": "low", "category": "test"},  # Invalid URL for testing
        {"id": 4, "url": "https://stackoverflow.com", "priority": "high", "category": "development"},
        {"id": 5, "url": "", "priority": "medium", "category": "empty"}  # Empty URL for testing
    ]
    
    csv_file = "complex_urls.csv"
    write_csv(csv_file, complex_data)
    print(f"✅ Created {csv_file} with complex data including invalid entries")
    
    # Create a validation agent
    validator_agent = Agent(
        name="DataValidator",
        role="Data Quality Specialist", 
        goal="Validate and clean CSV data before processing",
        backstory="Expert in data validation and quality assurance",
        tools=[read_csv, write_csv],
        instructions="""
        You are a data validation expert. Your job is to:
        1. Read CSV files and validate data quality
        2. Identify invalid or problematic entries
        3. Clean and standardize data where possible
        4. Create separate files for valid and invalid data
        5. Provide detailed validation reports
        """,
        llm="gpt-4o-mini"
    )
    
    # Create a processing agent
    processor_agent = Agent(
        name="ValidatedProcessor",
        role="Validated Data Processor",
        goal="Process only validated and clean data",
        backstory="Specialist in processing pre-validated data efficiently",
        tools=[read_csv, write_csv],
        instructions="""
        You process validated data efficiently:
        1. Read validated CSV data
        2. Process each valid entry according to requirements
        3. Generate comprehensive results
        4. Create detailed output reports
        """,
        llm="gpt-4o-mini"
    )
    
    # Create validation task
    validation_task = Task(
        description=f"""
        Validate the data in '{csv_file}':
        1. Read the CSV file
        2. Check each row for:
           - Valid URL format (must start with http:// or https://)
           - Non-empty required fields
           - Valid priority values (high, medium, low)
           - Valid category values
        3. Separate valid and invalid entries
        4. Save valid entries to 'valid_urls.csv'
        5. Save invalid entries to 'invalid_urls.csv' with error descriptions
        6. Create a validation summary report
        """,
        expected_output="Validation complete with separate files for valid/invalid data and summary report",
        agent=validator_agent
    )
    
    # Create processing task (depends on validation)
    processing_task = Task(
        description="""
        Process the validated data from 'valid_urls.csv':
        1. Read the validated CSV file
        2. For each valid URL, provide analysis based on priority and category
        3. High priority items get detailed analysis
        4. Medium priority items get standard analysis  
        5. Low priority items get basic analysis
        6. Save results to 'final_results.csv'
        """,
        expected_output="Processed results for all valid entries saved to final CSV",
        agent=processor_agent
    )
    
    # Initialize and run with sequential processing
    agents = PraisonAIAgents(
        agents=[validator_agent, processor_agent],
        tasks=[validation_task, processing_task],
        process="sequential"  # Validation must complete before processing
    )
    
    print(f"🚀 Starting advanced processing with validation")
    agents.start()

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

if __name__ == "__main__":
    print("CSV Processing with PraisonAI Agents - Multiple Methods Demo")
    print("=" * 70)
    
    print("\nThis demo shows 4 different ways to process CSV files with agents:")
    print("1. Simple CSV Loop Processing (easiest)")
    print("2. Manual CSV Processing with tools") 
    print("3. URL Processing from CSV (addresses the GitHub issue)")
    print("4. Advanced processing with validation")
    
    # You can run all methods or comment out ones you don't need
    try:
        # Method 1: Simple loop processing
        method_1_simple_loop()
        
        # Method 2: Manual CSV processing  
        method_2_manual_csv()
        
        # Method 3: URL processing (specific to the GitHub issue)
        method_3_url_processing()
        
        # Method 4: Advanced processing with validation
        method_4_advanced_processing()
        
        print("\n" + "="*70)
        print("✅ All CSV processing methods completed!")
        print("Check the generated CSV files for results.")
        print("="*70)
        
    except Exception as e:
        print(f"❌ Error during processing: {e}")
        print("Make sure you have:")
        print("- OpenAI API key set (export OPENAI_API_KEY=your_key)")
        print("- praisonaiagents package installed (pip install praisonaiagents)")
        print("- pandas package installed (pip install pandas)")