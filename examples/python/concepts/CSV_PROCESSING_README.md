# CSV Processing with PraisonAI Agents

This document answers GitHub Issue #23: "How to pass in a CSV file" and provides multiple solutions for processing CSV files with PraisonAI agents.

## Quick Answer

**Yes, it's absolutely possible!** PraisonAI provides multiple ways to process CSV files with agents working through the list sequentially.

## The Simplest Solution

For the exact use case mentioned in the issue (CSV list of URLs processed sequentially):

```python
from praisonaiagents import Agent, Task, PraisonAIAgents

# Create your agent
agent = Agent(
    name="URLProcessor",
    instructions="Analyze each URL from the CSV file"
)

# Create a loop task
task = Task(
    description="Process each URL from the CSV",
    agent=agent,
    task_type="loop",           # Enable CSV loop processing
    input_file="your_urls.csv"  # Your CSV file
)

# Run the agents
agents = PraisonAIAgents(
    agents=[agent],
    tasks=[task],
    process="workflow"
)

agents.start()
```

## CSV File Format

Your CSV file should have a simple structure. For URLs:

```csv
url
https://example.com
https://github.com
https://stackoverflow.com
```

Or with additional columns:

```csv
url,description
https://example.com,Example website
https://github.com,GitHub platform
https://stackoverflow.com,Q&A site
```

## Available Methods

### Method 1: Simple Loop Processing (Recommended)
- **File**: `simple-csv-url-processor.py`
- **Best for**: Beginners, simple use cases
- **How it works**: Uses `task_type="loop"` to automatically process each CSV row

### Method 2: Manual CSV Processing
- **File**: `csv-processing-agents.py` (Method 2)
- **Best for**: When you need more control over validation and processing
- **How it works**: Uses CSV tools (`read_csv`, `write_csv`) for manual processing

### Method 3: URL-Specific Processing
- **File**: `csv-processing-agents.py` (Method 3)
- **Best for**: Specifically processing URLs with detailed analysis
- **How it works**: Combines CSV tools with URL analysis logic

### Method 4: Advanced Processing with Validation
- **File**: `csv-processing-agents.py` (Method 4)
- **Best for**: Production use cases requiring data validation
- **How it works**: Validates data before processing, handles errors gracefully

## Built-in CSV Tools

PraisonAI includes powerful CSV tools:

```python
from praisonaiagents.tools import read_csv, write_csv, merge_csv

# Read CSV files
data = read_csv("input.csv")

# Write CSV files  
write_csv("output.csv", data)

# Merge multiple CSV files
merge_csv(["file1.csv", "file2.csv"], "merged.csv")
```

## Examples for Different Use Cases

### Processing URLs from CSV
```python
# Your CSV: urls.csv
# url,priority
# https://example.com,high
# https://github.com,medium

agent = Agent(
    name="URLAnalyzer",
    tools=[read_csv, write_csv],
    instructions="Analyze URLs based on priority"
)
```

### Processing Any Text File
```python
# For text files, you can convert to CSV format first
# Or process line by line using file tools
```

### Batch Processing Tasks
```python
# Your CSV: tasks.csv  
# task
# "Analyze competitor website"
# "Research market trends"
# "Generate report summary"

task = Task(
    description="Complete each task from the CSV",
    task_type="loop",
    input_file="tasks.csv"
)
```

## Prerequisites

1. **Install PraisonAI Agents**:
   ```bash
   pip install praisonaiagents
   ```

2. **Set API Key**:
   ```bash
   export OPENAI_API_KEY=your_api_key_here
   ```

3. **Install pandas** (for advanced CSV operations):
   ```bash
   pip install pandas
   ```

## Running the Examples

1. **Simple URL Processing**:
   ```bash
   python simple-csv-url-processor.py
   ```

2. **Comprehensive Examples**:
   ```bash
   python csv-processing-agents.py
   ```

## Troubleshooting

### Common Issues:

1. **"CSV file not found"**
   - Make sure your CSV file is in the same directory as your script
   - Use absolute paths if needed: `/full/path/to/your/file.csv`

2. **"pandas not available"**
   - Install pandas: `pip install pandas`

3. **"API key not set"**
   - Set your OpenAI API key: `export OPENAI_API_KEY=your_key`

4. **Processing stops early**
   - Increase `max_iter` parameter in PraisonAIAgents
   - Check for errors in your CSV format

### CSV Format Tips:

- Use UTF-8 encoding
- Ensure consistent column headers
- Handle special characters properly
- Keep URLs properly formatted (http:// or https://)

## Related Documentation

- [CSV Tools Documentation](../../../docs/tools/csv_tools.mdx)
- [Repetitive Agents](../../../docs/features/repetitive.mdx)  
- [Agent Examples](../../README.md)

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review the example files for working implementations
3. Open an issue on the GitHub repository with your specific use case

---

*This solution was generated in response to GitHub Issue #23*