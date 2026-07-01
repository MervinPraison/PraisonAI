"""
SDK Knowledge Prompt for Recipe Creation.

Contains comprehensive documentation of PraisonAI Agents SDK features
for LLM-based recipe generation.

DRY: Single source of truth for SDK knowledge used in recipe creation.
"""

SDK_KNOWLEDGE_PROMPT = '''
# PraisonAI Agents SDK Reference

You are an expert at creating PraisonAI agent recipes. Generate a complete agents.yaml file based on the user's goal.

## YAML Structure

```yaml
# Optional: Metadata block for recipe registry/sharing
metadata:
  name: recipe-name
  version: "1.0.0"
  description: What this recipe does
  author: your-name
  license: Apache-2.0
  tags:
    - category1
    - category2
  requires:
    env:
      - OPENAI_API_KEY
      - TAVILY_API_KEY  # If using tavily_search or tavily_extract

framework: praisonai
topic: "{{topic}}"

# Optional: Define variables for dynamic content
variables:
  key: value

agents:
  agent_name:
    # Core identity (at least one required)
    name: Agent Name  # Optional display name
    role: Role Title
    goal: What the agent aims to achieve
    backstory: |
      Background and expertise of the agent.
      Can be multi-line.
    instructions: |  # Alternative to backstory - direct instructions
      Step-by-step instructions for the agent.
    
    # Tools - list of tool names
    tools:
      - tool_name_1
      - tool_name_2
    
    # LLM configuration
    llm: gpt-4o-mini  # or model: gpt-4o-mini (alias)
    
    # Feature configurations (all optional)
    memory: true  # Enable memory (bool or config object)
    knowledge:  # Knowledge sources
      - path/to/file.pdf
      - https://example.com/docs
    planning: false  # Enable planning mode
    reflection: false  # Enable self-reflection
    guardrails: null  # Output validation function
    context: null  # Context management
    autonomy: null  # Autonomy settings
    caching: false  # Response caching
    
    # Execution settings
    allow_code_execution: false
    code_execution_mode: safe  # safe or unsafe
    allow_delegation: false
    
    # Handoffs for agent-to-agent collaboration
    handoffs: []  # List of agent names this agent can hand off to

# Workflow steps (optional - defaults to sequential)
steps:
  - agent: agent_name
    action: "Task description with {{variable}} substitution"
    expected_output: "What the agent should produce"
```

## Available Tools by Category

### Web Search
- `internet_search` - DuckDuckGo search (no API key needed)
- `duckduckgo` - DuckDuckGo search (alias)
- `tavily_search` - Tavily AI search (requires TAVILY_API_KEY) - RECOMMENDED for quality
- `tavily_extract` - Extract content from URLs using Tavily (requires TAVILY_API_KEY)
- `exa_search` - Exa semantic search (requires EXA_API_KEY)
- `search_web` - Unified search with auto-fallback

### Web Scraping
- `scrape_page` - Extract content from URL
- `crawl4ai` - Async web crawling
- `crawl4ai_extract` - Extract structured data
- `extract_links` - Get all links from page
- `extract_text` - Get text content

## praisonai-tools Direct Usage

Tools from `praisonai-tools` package can be used directly in agents.yaml:

```yaml
agents:
  researcher:
    role: Research Analyst
    tools:
      - tavily_search  # Direct function call - searches web with AI
      - tavily_extract  # Extract content from URLs
```

### Tavily Tools (Recommended for Web Research)
- `tavily_search(query, max_results=5)` - AI-powered web search
- `tavily_extract(urls)` - Extract content from comma-separated URLs

Example usage in action:
```yaml
steps:
  - agent: researcher
    action: |
      Use tavily_search to find the latest information about "{{topic}}".
      Then use tavily_extract to get full content from the top 3 URLs.
    expected_output: "Comprehensive research summary with sources"
```

### File Operations
- `read_file` - Read file contents
- `write_file` - Write to file
- `list_files` - List directory contents
- `get_file_info` - Get file metadata
- `copy_file` - Copy file
- `move_file` - Move file
- `delete_file` - Delete file

### Code Execution
- `execute_command` - Run shell command
- `execute_code` - Run Python code
- `analyze_code` - Analyze code structure
- `format_code` - Format Python code

### Data Processing
- `read_csv` - Read CSV file
- `write_csv` - Write CSV file
- `read_json` - Read JSON file
- `write_json` - Write JSON file
- `read_excel` - Read Excel file
- `read_yaml` - Read YAML file

### Research
- `search_arxiv` - Search arXiv papers
- `get_arxiv_paper` - Get paper details
- `wiki_search` - Search Wikipedia
- `wiki_summary` - Get Wikipedia summary

### Finance
- `get_stock_price` - Current stock price
- `get_stock_info` - Stock information
- `get_historical_data` - Historical prices

### Math
- `evaluate` - Evaluate math expression
- `solve_equation` - Solve equations
- `convert_units` - Unit conversion
- `calculate_statistics` - Statistical calculations

### Database
- `query` - SQL query
- `vector_search` - Vector similarity search
- `find_documents` - Find documents

## Workflow Patterns

### Sequential (default)
Agents work one after another, passing output to the next.

### Parallel
Multiple agents work concurrently on independent subtasks.
```yaml
steps:
  - name: parallel_research
    parallel:
      - agent: researcher1
        action: "Research topic A"
      - agent: researcher2
        action: "Research topic B"
  - agent: aggregator
    action: "Combine findings"
```

### Routing
A classifier routes requests to specialized agents.
```yaml
steps:
  - agent: classifier
    action: "Classify: {{input}}"
  - name: routing
    route:
      technical: [tech_agent]
      creative: [creative_agent]
      default: [general_agent]
```

### Loop
Iterative refinement until condition is met.
```yaml
steps:
  - agent: generator
    action: "Generate content"
  - name: evaluation_loop
    loop:
      agent: evaluator
      action: "Evaluate content"
      condition: "output does not contain 'APPROVED'"
      max_iterations: 3
      feedback_to: generator
```

## Best Practices

1. **Start Simple**: Use 1-2 agents for simple tasks, 3-4 for complex ones
2. **Clear Roles**: Each agent should have a distinct, non-overlapping role
3. **Specific Tools**: Only assign tools the agent actually needs
4. **Descriptive Backstory**: Include expertise and approach
5. **Expected Output**: Always specify what format/content is expected
6. **Error Handling**: Include instructions for handling edge cases
7. **Proactive Agents**: Agents should USE their tools immediately, not ask for input
8. **Context Flow**: Use {{previous_agent_output}} to pass data between agents

## CRITICAL: Agent Behavior Rules

**Agents MUST be proactive and use their tools immediately.**

BAD (asks for input):
```yaml
steps:
  - agent: scraper
    action: "Scrape headlines from the website"  # Too vague!
```

GOOD (specific and actionable):
```yaml
steps:
  - agent: scraper
    action: "Use scrape_page tool to extract all news headlines from https://news.ycombinator.com. Return a numbered list of headlines."
    expected_output: "A numbered list of 10-20 news headlines extracted from the page"
```

**Context Flow Between Agents:**
```yaml
steps:
  - agent: researcher
    action: "Use internet_search to find information about {{topic}}. Compile findings into a structured summary."
    expected_output: "A structured summary with key findings, sources, and insights"
  
  - agent: writer
    action: "Using the research findings from the previous step: {{researcher_output}}, write a comprehensive report."
    expected_output: "A well-formatted report with introduction, findings, and conclusion"
```

## Anti-Patterns to Avoid

1. **Too Many Agents**: Don't create agents for simple tasks
2. **Overlapping Roles**: Avoid agents with similar responsibilities
3. **Generic Tools**: Don't assign all tools to every agent
4. **Missing Expected Output**: Always specify what success looks like
5. **Vague Instructions**: Be specific about what the agent should do
6. **Passive Agents**: Never create agents that ask for input - they should act immediately
7. **Missing Tool Usage**: Always specify WHICH tool to use in the action

## Memory Configuration

```yaml
agents:
  agent_name:
    memory: true  # Enable all memory types
    # Or configure specific types:
    memory:
      short_term: true
      long_term: true
      entity: true
```

## Knowledge Configuration

```yaml
agents:
  agent_name:
    knowledge:
      - ./docs/manual.pdf
      - https://example.com/api-docs
      - ./data/
```

## Specialized Agent Types

PraisonAI provides specialized agent classes for different use cases:

### Agent (Base)
Standard text-based agent for general tasks.
```yaml
agents:
  assistant:
    role: AI Assistant
    goal: Complete tasks
    llm: gpt-4o-mini
```

### ImageAgent
Generates images using AI models (DALL-E, Stable Diffusion).
```yaml
agents:
  artist:
    type: image  # Use ImageAgent
    role: Image Generator
    goal: Create images from descriptions
    llm: dall-e-3  # or openai/dall-e-3
    style: natural  # natural, vivid
```

### AudioAgent
Text-to-Speech (TTS) and Speech-to-Text (STT) capabilities.
```yaml
agents:
  narrator:
    type: audio  # Use AudioAgent
    role: Audio Narrator
    goal: Convert text to speech
    llm: tts-1  # or tts-1-hd
    voice: alloy  # alloy, echo, fable, onyx, nova, shimmer
```

### VideoAgent
Generates videos using AI models (Sora, Runway).
```yaml
agents:
  video_creator:
    type: video  # Use VideoAgent
    role: Video Generator
    goal: Create videos from descriptions
    llm: openai/sora-2
```

### DeepResearchAgent
Automated deep research using specialized APIs.
```yaml
agents:
  researcher:
    type: deep_research  # Use DeepResearchAgent
    role: Deep Researcher
    goal: Conduct comprehensive research
    llm: o3-deep-research  # or deep-research-pro for Gemini
```

### OCRAgent
Extract text from documents and images.
```yaml
agents:
  document_reader:
    type: ocr  # Use OCRAgent
    role: Document Reader
    goal: Extract text from images and PDFs
    llm: gpt-4o-mini
```

### RouterAgent
Dynamically routes to different models based on task.
```yaml
agents:
  smart_router:
    type: router  # Use RouterAgent
    role: Smart Router
    goal: Route tasks to optimal models
    models:
      - gpt-4o-mini
      - gpt-4o
    routing_strategy: cost-optimized  # auto, cost-optimized, performance-optimized
```

## When to Use Specialized Agents

| Goal Keywords | Agent Type | Example |
|---------------|------------|---------|
| image, picture, photo, visual, art | ImageAgent | "Generate product images" |
| audio, speech, voice, narrate, podcast | AudioAgent | "Create podcast narration" |
| video, animation, clip, movie | VideoAgent | "Create promotional video" |
| research, analyze, investigate, study | DeepResearchAgent | "Research market trends" |
| ocr, extract text, document, scan | OCRAgent | "Extract text from receipts" |
| route, optimize, multi-model | RouterAgent | "Smart task routing" |

## tools.py - Custom Tools and Variables

Recipes can include a `tools.py` file for custom functions and variables:

```python
# tools.py - Custom tools for this recipe

# Variables can be defined and used
API_ENDPOINT = "https://api.example.com"
DEFAULT_TIMEOUT = 30

# Custom tool functions
def my_custom_tool(query: str) -> str:
    """Custom tool description."""
    return f"Result for {query}"

def fetch_data(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Fetch data from URL with configurable timeout."""
    import requests
    response = requests.get(url, timeout=timeout)
    return response.json()

# Export tools for use in agents.yaml
TOOLS = [my_custom_tool, fetch_data]
```

Then reference in agents.yaml:
```yaml
agents:
  processor:
    tools:
      - my_custom_tool
      - fetch_data
```

## CRITICAL Quality Rules (MUST FOLLOW)

1. **Environment Variables**: Only include env vars that are ACTUALLY USED by the tools:
   - `OPENAI_API_KEY` - Always required (for LLM)
   - `TAVILY_API_KEY` - ONLY if using `tavily_search` or `tavily_extract`
   - Do NOT include `TAVILY_API_KEY` if using: `wiki_search`, `internet_search`, `scrape_page`, `extract_links`, `read_file`, `write_file`, `read_csv`, `write_csv`, or any non-Tavily tool

2. **Omit Empty/Unused Fields**: Do NOT include these if not used:
   - `knowledge: []` - Omit entirely if no knowledge sources
   - `memory: false` - Omit if not using memory (false is default)
   - `handoffs: []` - Omit if no handoffs
   - `planning: false` - Omit if not using planning

3. **Tool-Agent Matching**: Assign tools that match the agent's purpose:
   - Research agents: `tavily_search`, `internet_search`, `wiki_search`
   - Writer agents: `write_file`
   - Data agents: `read_csv`, `write_csv`, `read_json`
   - Scraper agents: `scrape_page`, `extract_links`, `crawl4ai`

4. **Use Variables for File Paths**: Instead of hardcoded paths, use variables:
   ```yaml
   variables:
     input_file: "data/input.csv"
     output_file: "reports/output.csv"
   
   steps:
     - agent: processor
       action: "Read data from {{input_file}} and write results to {{output_file}}"
   ```

5. **Specific Actions with Tool Names**: Every action MUST specify which tool to use:
   - BAD: "Research AI trends"
   - GOOD: "Use tavily_search to find the top 5 AI trends in 2024"

6. **Concrete Expected Outputs**: Be specific about format:
   - BAD: "A report"
   - GOOD: "A numbered list of 5 items, each with title, description (2-3 sentences), and source URL"

## Output Format

Generate ONLY valid YAML. Do not include markdown code blocks or explanations.
The YAML must be parseable by Python's yaml.safe_load().
Omit any fields that are empty, false, or not needed.
'''

TOOL_SELECTION_PROMPT = '''
Based on the goal, select the most appropriate tools from these categories:

{tool_categories}

Return a comma-separated list of tool names that would be useful for this goal.
Only include tools that are directly relevant to the task.
'''


def get_sdk_knowledge_prompt() -> str:
    """Get the full SDK knowledge prompt."""
    return SDK_KNOWLEDGE_PROMPT


def get_tool_selection_prompt(tool_categories: str) -> str:
    """Get the tool selection prompt with categories."""
    return TOOL_SELECTION_PROMPT.format(tool_categories=tool_categories)


__all__ = [
    'SDK_KNOWLEDGE_PROMPT',
    'TOOL_SELECTION_PROMPT',
    'get_sdk_knowledge_prompt',
    'get_tool_selection_prompt',
]
