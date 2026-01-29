"""
Recipe Creator for PraisonAI.

Automatically generates recipe folders with agents.yaml, TEMPLATE.yaml, and tools.py
based on a natural language goal description.

DRY: Reuses AutoGenerator patterns and SDK knowledge prompt.
     Imports TOOL_CATEGORIES and TASK_KEYWORD_TO_TOOLS from auto.py to avoid duplication.
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from .sdk_knowledge import get_sdk_knowledge_prompt

# DRY: Import tool categories from auto.py instead of duplicating
from praisonai.auto import TOOL_CATEGORIES, TASK_KEYWORD_TO_TOOLS

logger = logging.getLogger(__name__)


class RecipeCreator:
    """
    Creates optimized recipes from natural language goals.
    
    Usage:
        creator = RecipeCreator()
        path = creator.create("Build a web scraper for news articles")
    """
    
    # DRY: Use imported TOOL_CATEGORIES and TASK_KEYWORD_TO_TOOLS from auto.py
    TOOL_CATEGORIES = TOOL_CATEGORIES
    TASK_KEYWORD_TO_TOOLS = TASK_KEYWORD_TO_TOOLS
    
    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.7,
    ):
        """
        Initialize the recipe creator.
        
        Args:
            model: LLM model for generation (default: gpt-4o-mini)
            temperature: LLM temperature for creativity
        """
        self.model = model or os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
        self.temperature = temperature
    
    def _get_litellm(self):
        """Lazy import litellm."""
        try:
            import litellm
            return litellm
        except ImportError:
            raise ImportError(
                "litellm is required for recipe creation. "
                "Install with: pip install litellm"
            )
    
    def generate_folder_name(self, goal: str) -> str:
        """
        Generate a kebab-case folder name from the goal.
        
        Args:
            goal: Natural language goal description
            
        Returns:
            Kebab-case folder name (max 50 chars)
        """
        # Remove special characters
        clean = re.sub(r'[^a-zA-Z0-9\s]', '', goal)
        
        # Convert to lowercase and split into words
        words = clean.lower().split()
        
        # Take first few meaningful words
        meaningful_words = []
        skip_words = {'a', 'an', 'the', 'for', 'to', 'and', 'or', 'of', 'in', 'on', 'with'}
        
        for word in words:
            if word not in skip_words and len(word) > 1:
                meaningful_words.append(word)
            if len('-'.join(meaningful_words)) >= 40:
                break
        
        # Join with hyphens
        name = '-'.join(meaningful_words[:6])
        
        # Ensure max length
        if len(name) > 50:
            name = name[:50].rsplit('-', 1)[0]
        
        return name or 'recipe'
    
    def get_tools_for_task(self, goal: str) -> List[str]:
        """
        Analyze goal and return appropriate tools.
        
        Args:
            goal: Natural language goal description
            
        Returns:
            List of tool names
        """
        goal_lower = goal.lower()
        matched_categories = set()
        
        # Match keywords to categories
        for keyword, category in self.TASK_KEYWORD_TO_TOOLS.items():
            if keyword in goal_lower:
                matched_categories.add(category)
        
        # Collect tools from matched categories
        tools = []
        for category in matched_categories:
            if category in self.TOOL_CATEGORIES:
                # Add first 2-3 tools from each category
                tools.extend(self.TOOL_CATEGORIES[category][:3])
        
        # Always include core tools for flexibility
        core_tools = ['read_file', 'write_file']
        for tool in core_tools:
            if tool not in tools:
                tools.append(tool)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_tools = []
        for tool in tools:
            if tool not in seen:
                seen.add(tool)
                unique_tools.append(tool)
        
        return unique_tools[:10]  # Max 10 tools
    
    def generate_agents_yaml(
        self,
        goal: str,
        agents: Optional[Dict[str, Dict[str, Any]]] = None,
        tools: Optional[Dict[str, List[str]]] = None,
        agent_types: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Generate agents.yaml content using LLM with SDK knowledge.
        
        Args:
            goal: Natural language goal description
            agents: Optional custom agent definitions
            tools: Optional custom tool assignments per agent
            agent_types: Optional agent type specifications
            
        Returns:
            YAML content string
        """
        # If custom agents are provided, generate YAML directly without LLM
        if agents:
            return self._generate_custom_agents_yaml(goal, agents, tools, agent_types)
        
        litellm = self._get_litellm()
        
        # Get recommended tools
        task_tools = self.get_tools_for_task(goal)
        tools_str = ', '.join(task_tools) if task_tools else 'read_file, write_file'
        
        # Build prompt with SDK knowledge
        sdk_knowledge = get_sdk_knowledge_prompt()
        
        # Add customization hints to prompt
        customization_hints = ""
        if tools:
            tools_hint = ", ".join([f"{k}: {','.join(v)}" for k, v in tools.items()])
            customization_hints += f"\nUser-specified tools per agent: {tools_hint}"
        if agent_types:
            types_hint = ", ".join([f"{k}: {v}" for k, v in agent_types.items()])
            customization_hints += f"\nUser-specified agent types: {types_hint}"
        
        # Define approval-required tools for auto-approve detection
        approval_required_tools = [
            'write_file', 'copy_file', 'move_file', 'delete_file',
            'download_file', 'execute_command', 'execute_code', 'kill_process'
        ]
        
        prompt = f"""{sdk_knowledge}

## Your Task

Create an agents.yaml file for this goal:
"{goal}"

Recommended tools based on the goal: {tools_str}
{customization_hints}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMPLETE LIST OF AVAILABLE TOOLS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### WEB SEARCH TOOLS (Safe - No approval required):
- `search_web` - ⭐ RECOMMENDED - Unified search with auto-fallback (tries Tavily→Exa→You.com→DuckDuckGo)
- `internet_search` - DuckDuckGo search (FREE, no API key needed, fallback option)
- `tavily_search` - High-quality AI search (REQUIRES TAVILY_API_KEY)
- `exa_search` - Exa AI search (REQUIRES EXA_API_KEY)
- `ydc_search` - You.com search (REQUIRES YDC_API_KEY)
- `searxng_search` - SearXNG meta-search

### WEB SCRAPING TOOLS (Safe):
- `scrape_page` - Scrape web page content
- `extract_links` - Extract links from a URL
- `crawl4ai` - Advanced web crawling
- `crawl4ai_extract` - Extract structured data from web pages
- `get_article` - Get article content

### FILE TOOLS - READ (Safe):
- `read_file` - Read local files
- `list_files` - List files in a directory
- `get_file_info` - Get file metadata

### FILE TOOLS - WRITE (⚠️ APPROVAL REQUIRED - add to 'approve' field):
- `write_file` - Write content to files
- `copy_file` - Copy files
- `move_file` - Move files
- `delete_file` - Delete files
- `download_file` - Download from URL

### CODE EXECUTION (⚠️ APPROVAL REQUIRED - add to 'approve' field):
- `execute_command` - Run shell commands
- `execute_code` - Execute Python code
- `kill_process` - Kill a process

### CODE ANALYSIS (Safe):
- `analyze_code` - Analyze Python code structure
- `format_code` - Format Python code

### DATA PROCESSING (Safe):
- `read_csv`, `read_json`, `read_yaml`, `read_xml`, `read_excel`

### DATA WRITING (⚠️ APPROVAL REQUIRED):
- `write_csv`, `write_json`, `write_yaml`, `write_excel`

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SPECIALIZED AGENT TYPES (Use `agent:` field to specify type)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### AudioAgent - Text-to-Speech (TTS) and Speech-to-Text (STT)
Keywords: "audio", "speech", "voice", "tts", "stt", "transcribe", "speak", "narrate", "read aloud"
- TTS models: openai/tts-1, openai/tts-1-hd, elevenlabs/eleven_multilingual_v2
- STT models: openai/whisper-1, groq/whisper-large-v3, deepgram/nova-2
- Use `agent: AudioAgent` in the agent definition
- Action for TTS: "Convert the text to speech and save as audio file"
- Action for STT: "Transcribe the audio file to text"

### VideoAgent - Video Generation
Keywords: "video", "generate video", "create video", "animation", "sora"
- Models: openai/sora-2, gemini/veo-3.0-generate-preview, runway/gen-3
- Use `agent: VideoAgent` in the agent definition
- Action: "Generate a video based on the prompt"

### ImageAgent - Image Generation
Keywords: "generate image", "create image", "dall-e", "illustration", "draw"
- Models: openai/dall-e-3, openai/dall-e-2, stability/stable-diffusion
- Use `agent: ImageAgent` in the agent definition
- Action: "Generate an image based on the description"
- YAML supports `output:` field to save image to a file path
- Generated image URL is stored in `_last_image_url` variable for next steps

### Image Analysis (Vision) - Analyzing/Understanding Images
Keywords: "analyze image", "describe image", "understand image", "what's in the image", "image analysis"
- Use a regular agent with `llm: gpt-4o-mini` (vision-capable model)
- MUST define `variables:` section with `image_path:` for the input image
- The image is passed via the `attachments` parameter automatically
- Action: "Analyze the image at {{image_path}} and describe..."
- Example YAML structure:
```yaml
variables:
  image_path: ""  # Will be provided at runtime via --var image_path="/path/to/image.jpg"

agents:
  analyst:
    role: Image Analyst
    goal: Analyze the provided image
    backstory: Expert at interpreting visual content
    tools: []
    llm: gpt-4o-mini

steps:
  - agent: analyst
    action: "Analyze the image and describe the main elements, colors, and composition."
    expected_output: "Detailed image analysis"
```

### OCRAgent - Text Extraction from Documents/Images
Keywords: "ocr", "extract text", "read document", "pdf", "scan", "document extraction"
- Models: mistral/mistral-ocr-latest
- Use `agent: OCRAgent` in the agent definition
- Requires: MISTRAL_API_KEY
- Action: "Extract text from the document/image"

### DeepResearchAgent - In-depth Research
Keywords: "deep research", "comprehensive research", "thorough investigation"
- Use `agent: DeepResearchAgent` in the agent definition
- Action: "Conduct deep research on the topic"

### URL Content Analysis - Analyzing Web Pages
Keywords: "analyze url", "analyze webpage", "read url", "extract from url", "url to blog", "webpage analysis"
- Use `web_crawl` or `crawl_web` tool to fetch URL content
- MUST define `variables:` section with `url:` for the input URL
- Example YAML structure:
```yaml
variables:
  url: ""  # Will be provided at runtime via --var url="https://example.com"

agents:
  crawler:
    role: Web Content Extractor
    goal: Extract content from the provided URL
    backstory: Expert at extracting and parsing web content
    tools:
      - web_crawl
    llm: gpt-4o-mini

steps:
  - agent: crawler
    action: "Use web_crawl to extract content from {{url}}. Return the main content, title, and key information."
    expected_output: "Extracted web content with title and main text"
```

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANDATORY RULES - YOU MUST FOLLOW ALL OF THESE WITHOUT EXCEPTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## RULE 1: TOOL SELECTION (CRITICAL)

**DEFAULT SEARCH TOOL**: Use `search_web` for web searches - it automatically detects available API keys and uses the best provider:
- If TAVILY_API_KEY is set → uses Tavily (highest quality)
- If EXA_API_KEY is set → uses Exa
- If YDC_API_KEY is set → uses You.com
- Otherwise → falls back to DuckDuckGo (no API key needed)

**APPROVAL-REQUIRED TOOLS**: If you use ANY of these tools, you MUST add an 'approve' field at the root level:
- write_file, copy_file, move_file, delete_file, download_file
- execute_command, execute_code, kill_process
- write_csv, write_json, write_yaml, write_excel

Example with approval:
```yaml
approve:
  - write_file
  - execute_command

agents:
  ...
```

IMPORTANT: For complex tasks involving research, analysis, or report creation, use 3 AGENTS:
1. **researcher** - Gathers raw information/data
2. **analyst** - Analyzes and compares findings
3. **writer** - Creates final output/report

Only use 1 agent for very simple tasks like "calculate X" or "explain Y in one sentence".

## RULE 2: ENVIRONMENT VARIABLES (CRITICAL)
- ALWAYS include: OPENAI_API_KEY
- Do NOT include TAVILY_API_KEY unless user explicitly asks for web search
- Do NOT include any approve field unless user explicitly asks to save files

## RULE 3: ACTION FORMAT (CRITICAL)
Every action MUST:
1. Contain CONCRETE values, NOT variables
2. Specify exact expected format
3. If agent has tools=[], use verbs like "Research", "Analyze", "Create", "Compare"
4. If agent has tools assigned, start with "Use [tool_name] to..."

GOOD (no tools): "Research the top 5 benefits of microservices. List each with title and description."
GOOD (with tools): "Use search_web to find the top 5 developments in quantum computing."
BAD: "Use search_web to find {{{{topic}}}}" (variables don't work in actions!)

## RULE 4: AGENT STRUCTURE (CRITICAL)
- Use 3 agents for complex tasks (research→analyze→write pattern)
- Use 1 agent only for trivial tasks (single calculation, simple lookup)
- Each agent needs: role, goal, backstory, tools, llm
- **ALL agents should have `tools: []` by default** - LLMs have knowledge and don't need external tools
- Only add tools if user EXPLICITLY asks to "save to file", "search the web", or "execute code"
- **CRITICAL: If an agent has tools assigned, ALWAYS add `tool_choice: required`** to force tool usage
- llm should be: gpt-4o-mini (default)
- Agents should have DISTINCT roles - don't duplicate responsibilities

## RULE 5: STEPS FORMAT (CRITICAL)
- Each step needs: agent, action, expected_output
- Use {{{{agent_name}}}}_output to pass data between agents (DOUBLE curly braces!)
- Use {{{{variable_name}}}} to reference variables from the variables section (DOUBLE curly braces!)
- expected_output must describe exact format (list, report, JSON, etc.)

**CRITICAL: Variable References MUST use DOUBLE curly braces:**
- ✅ CORRECT: {{{{image_path}}}} or {{{{url}}}} or {{{{analyst}}}}_output
- ❌ WRONG: {{image_path}} or {{url}} or {{analyst}}_output (single braces don't work!)

## RULE 6: NO EMPTY FIELDS
- Do NOT include: knowledge: [], memory: false, handoffs: []
- Omit any field that would be empty

## RULE 7: OUTPUT FORMAT
- Output ONLY valid YAML
- No markdown code blocks
- No explanations before or after

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SEQUENTIAL PROCESS (DEFAULT - Use for all multi-agent recipes)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**ALWAYS include this field at the root level:**
```yaml
process: sequential
```

**What sequential process does:**
- Executes steps in order, passing output from one step to the next
- Each step can reference previous step outputs via {{agent_name}}_output
- Simple and reliable for most workflows

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE: SEARCH TASK (sequential workflow)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

metadata:
  name: latest-trends-research
  requires:
    env:
      - OPENAI_API_KEY

process: sequential

agents:
  researcher:
    role: Research Specialist
    goal: Find the latest information on the topic
    backstory: Expert at finding current, accurate information from web sources.
    tools:
      - search_web
    tool_choice: required
    llm: gpt-4o-mini

  analyst:
    role: Data Analyst
    goal: Analyze and synthesize research findings
    backstory: Expert at identifying patterns, trends, and key insights from raw data.
    tools: []
    llm: gpt-4o-mini

  writer:
    role: Technical Writer
    goal: Create clear, well-structured reports
    backstory: Expert at transforming complex information into readable, actionable content.
    tools: []
    llm: gpt-4o-mini

steps:
  - agent: researcher
    action: "You MUST call the search_web tool to search for the latest developments in [TOPIC]. Do NOT respond without calling search_web first. Return at least 5 key findings with titles, descriptions, and source URLs from the search results."
    expected_output: "Raw research data with 5+ findings, each containing: title, description, source URL"

  - agent: analyst
    action: "IMPORTANT: You MUST use ONLY the information from {{researcher_output}} below. Do NOT use your training data or prior knowledge. Read the research findings carefully, then: 1) Quote specific findings from the input, 2) Compare and identify the most significant insights, 3) Explain why each is important with references to the source URLs."
    expected_output: "Analysis with key insights. Each insight MUST: 1) Quote the original finding, 2) Explain significance, 3) Reference the source URL from the research"

  - agent: writer
    action: "IMPORTANT: You MUST use ONLY the information from {{analyst_output}} below. Do NOT use your training data or prior knowledge. Read the analysis carefully, then create a professional report that: 1) Summarizes the key insights from the analysis, 2) Includes the source URLs from the analysis, 3) Provides recommendations based on the findings."
    expected_output: "Professional report with: executive summary (referencing the analysis), key findings (with source URLs), recommendations (based on the findings)"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL: TOOL USAGE RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**WHEN TO USE TOOLS:**

1. **SEARCH TASKS** → Use `search_web` tool for the researcher agent
   Keywords: "search", "find", "latest", "current", "news", "trending", "recent", "2024", "2025", "2026"
   - search_web auto-detects API keys (Tavily→Exa→You.com→DuckDuckGo fallback)
   - Action format: "You MUST call the search_web tool to search for [query]. Do NOT respond without calling search_web first. Return [format] from the search results."
   - CRITICAL: The action MUST explicitly instruct the agent to call the tool and use its results

2. **FILE TASKS** → Use file tools + approve field
   Keywords: "save", "write", "create file", "export"
   - Add `approve: [write_file]` at root level
   - Action format: "Use write_file to save [content] to [filename]."

3. **ANALYSIS/COMPARISON TASKS** → Use `tools: []`
   Keywords: "analyze", "compare", "evaluate", "summarize"
   - LLM knowledge is sufficient
   - Action format: "Analyze...", "Compare...", "Evaluate..."

**MULTI-AGENT PATTERN:**
- **researcher**: Gets `search_web` if task involves finding current/latest information
- **analyst**: Gets `tools: []` - uses LLM to analyze data
- **writer**: Gets `tools: []` - uses LLM to create reports

4. **SPECIALIZED AGENT TASKS** → Use specialized agent types
   - Audio/Speech tasks → Use `agent: AudioAgent` with llm: openai/tts-1 or openai/whisper-1
   - Image generation → Use `agent: ImageAgent` with llm: openai/dall-e-3
   - Video generation → Use `agent: VideoAgent` with llm: openai/sora-2
   - OCR/Document extraction → Use `agent: OCRAgent` with llm: mistral/mistral-ocr-latest (needs MISTRAL_API_KEY)

**TOOL CALL RELIABILITY (CRITICAL):**
When an agent has tools assigned, the action MUST:
1. Explicitly name the tool: "You MUST call the search_web tool..."
2. Forbid responding without tool: "Do NOT respond without calling search_web first."
3. Require using results: "Return [specific format] from the search results."
4. Be specific about output: "Return at least 5 items with titles, descriptions, and URLs."
5. Add grounding instruction: "Only use information from the tool results. Do NOT fabricate or use prior knowledge."

**ANTI-HALLUCINATION PATTERN (MANDATORY for tool-using agents):**
For any agent with tools, add this to the action:
"IMPORTANT: Your response MUST be based ONLY on the actual tool results. Do NOT:
- Make up information not in the results
- Use your training data instead of tool results  
- Respond if the tool call fails - report the error instead"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE: SPECIALIZED AGENT (OCR + Analysis with hierarchical)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

metadata:
  name: document-extraction-analysis
  requires:
    env:
      - OPENAI_API_KEY
      - MISTRAL_API_KEY

process: hierarchical
manager_llm: gpt-4o-mini

agents:
  extractor:
    agent: OCRAgent
    role: Document Extractor
    goal: Extract text from documents and images
    backstory: Expert at extracting text from PDFs and images using OCR.
    llm: mistral/mistral-ocr-latest
    tools: []

  analyst:
    role: Content Analyst
    goal: Analyze extracted document content
    backstory: Expert at analyzing and summarizing document content.
    tools: []
    llm: gpt-4o-mini

steps:
  - agent: extractor
    action: "Extract all text from the provided document URL using OCR."
    expected_output: "Complete extracted text from the document"

  - agent: analyst
    action: "Analyze the extracted text from {{extractor_output}}. Identify key information, summarize main points."
    expected_output: "Analysis with: summary, key points, important details"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOW GENERATE THE RECIPE FOR: "{goal}"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ FINAL CHECKLIST:
1. **HIERARCHICAL PROCESS (MANDATORY)**: For multi-agent workflows, ALWAYS include at root level:
   - `process: hierarchical`
   - `manager_llm: gpt-4o-mini`
2. Does the goal involve searching/finding current information? YES → researcher gets search_web
3. Does the goal mention "save to file"? NO → Do NOT add write_file, approve field, or TAVILY_API_KEY
4. Do NOT include version, description, author, license fields
5. Only include: metadata.name, metadata.requires.env (just OPENAI_API_KEY), process, manager_llm, agents, steps
6. Writer should NOT save to file unless explicitly requested - just return the report as output
7. Does the goal involve audio/speech? YES → Use `agent: AudioAgent` with appropriate llm
8. Does the goal involve image generation? YES → Use `agent: ImageAgent` with llm: openai/dall-e-3
9. Does the goal involve video generation? YES → Use `agent: VideoAgent` with llm: openai/sora-2
10. Does the goal involve OCR/document extraction? YES → Use `agent: OCRAgent` with llm: mistral/mistral-ocr-latest and add MISTRAL_API_KEY
"""
        
        try:
            response = litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=2000,
            )
            
            yaml_content = response.choices[0].message.content or ""
            
            # Clean up any markdown code blocks
            yaml_content = yaml_content.strip()
            if yaml_content.startswith('```'):
                lines = yaml_content.split('\n')
                yaml_content = '\n'.join(lines[1:-1] if lines[-1].startswith('```') else lines[1:])
            
            # Apply custom tools and types if provided
            if tools or agent_types:
                yaml_content = self._apply_customizations(yaml_content, tools, agent_types)
            
            # Auto-add approve field for approval-required tools
            yaml_content = self._auto_add_approve_field(yaml_content, approval_required_tools)
            
            # Fix variable format: convert single braces to double braces
            yaml_content = self._fix_variable_format(yaml_content)
            
            # Validate YAML
            import yaml
            yaml.safe_load(yaml_content)
            
            return yaml_content
            
        except Exception as e:
            logger.warning(f"LLM generation failed: {e}, using fallback template")
            return self._get_fallback_yaml(goal, task_tools)
    
    def _generate_custom_agents_yaml(
        self,
        goal: str,
        agents: Dict[str, Dict[str, Any]],
        tools: Optional[Dict[str, List[str]]] = None,
        agent_types: Optional[Dict[str, str]] = None,
    ) -> str:
        """Generate agents.yaml from custom agent specifications."""
        import yaml
        
        # Build the YAML structure
        yaml_data = {
            'framework': 'praisonai',
            'topic': goal,
            'agents': {},
            'steps': []
        }
        
        # Get default tools based on goal if no tools specified
        default_tools = self.get_tools_for_task(goal) if not tools else []
        
        for agent_name, agent_config in agents.items():
            agent_def = {
                'role': agent_config.get('role', agent_name.replace('_', ' ').title()),
                'goal': agent_config.get('goal', goal),
                'backstory': agent_config.get('backstory', f'Expert {agent_name} specialized in completing tasks.'),
            }
            
            # Add tools if specified, otherwise assign default tools
            if tools and agent_name in tools:
                agent_def['tools'] = tools[agent_name]
            elif default_tools:
                # Assign default tools based on goal keywords
                agent_def['tools'] = default_tools[:3]  # Max 3 default tools per agent
            
            # Add type if specified
            if agent_types and agent_name in agent_types:
                agent_def['type'] = agent_types[agent_name]
            
            # Add LLM default
            agent_def['llm'] = 'gpt-4o-mini'
            
            yaml_data['agents'][agent_name] = agent_def
            
            # Add step for this agent
            yaml_data['steps'].append({
                'agent': agent_name,
                'action': agent_config.get('goal', goal),
                'expected_output': f"Completed output from {agent_name}"
            })
        
        return yaml.dump(yaml_data, default_flow_style=False, sort_keys=False)
    
    def _apply_customizations(
        self,
        yaml_content: str,
        tools: Optional[Dict[str, List[str]]] = None,
        agent_types: Optional[Dict[str, str]] = None,
    ) -> str:
        """Apply tool and type customizations to generated YAML."""
        import yaml
        
        try:
            data = yaml.safe_load(yaml_content)
            
            if 'agents' in data:
                for agent_name, agent_config in data['agents'].items():
                    # Apply custom tools
                    if tools and agent_name in tools:
                        agent_config['tools'] = tools[agent_name]
                    
                    # Apply custom types
                    if agent_types and agent_name in agent_types:
                        agent_config['type'] = agent_types[agent_name]
            
            return yaml.dump(data, default_flow_style=False, sort_keys=False)
            
        except Exception:
            # If parsing fails, return original
            return yaml_content
    
    def _auto_add_approve_field(
        self,
        yaml_content: str,
        approval_required_tools: List[str],
    ) -> str:
        """
        Auto-add approve field for approval-required tools.
        
        Scans the YAML for tools that require approval and adds them
        to the 'approve' field at the root level if not already present.
        """
        import yaml
        
        try:
            data = yaml.safe_load(yaml_content)
            if not data:
                return yaml_content
            
            # Collect all tools used across all agents
            used_tools = set()
            if 'agents' in data:
                for agent_config in data['agents'].values():
                    if 'tools' in agent_config:
                        used_tools.update(agent_config['tools'])
            
            # Find which approval-required tools are being used
            tools_needing_approval = [
                tool for tool in used_tools 
                if tool in approval_required_tools
            ]
            
            if not tools_needing_approval:
                return yaml_content
            
            # Get existing approve list or create new one
            existing_approve = set(data.get('approve', []) or [])
            
            # Add tools that need approval
            new_approve = existing_approve.union(set(tools_needing_approval))
            
            if new_approve:
                data['approve'] = sorted(list(new_approve))
                
                # Rebuild YAML with approve field at the top
                # Create ordered output
                ordered_data = {}
                
                # Put metadata first if exists
                if 'metadata' in data:
                    ordered_data['metadata'] = data.pop('metadata')
                
                # Put approve field next
                ordered_data['approve'] = data.pop('approve')
                
                # Add remaining keys
                ordered_data.update(data)
                
                return yaml.dump(ordered_data, default_flow_style=False, sort_keys=False)
            
            return yaml_content
            
        except Exception:
            # If parsing fails, return original
            return yaml_content
    
    def _fix_variable_format(self, yaml_content: str) -> str:
        """
        Fix variable format: convert single braces to double braces.
        
        The LLM sometimes generates {variable} instead of {{variable}}.
        This post-processor fixes common patterns:
        - {agent_name}_output -> {{agent_name}}_output
        - {image_path} -> {{image_path}}
        - {url} -> {{url}}
        """
        import re
        
        # Pattern to match single-brace variables that should be double-braced
        # Matches {word} or {word}_output but NOT {{word}} (already double-braced)
        # Also avoids matching YAML flow style like {key: value}
        
        # Common variable patterns that need double braces
        variable_patterns = [
            # CRITICAL FIX: {{agent}}_output -> {{agent_output}} (wrong format to correct format)
            # This is the most common LLM mistake - it generates {{researcher}}_output instead of {{researcher_output}}
            (r'\{\{(\w+)\}\}_output', r'{{\1_output}}'),
            # Agent output references: {agent}_output -> {{agent_output}}
            (r'\{(\w+)\}_output', r'{{\1_output}}'),
            # Common input variables (expanded list)
            (r'\{(image_path|image_url|image|url|source_url|webpage|document|source|input|query|topic|file_path|data|content|text)\}', r'{{\1}}'),
            # Agent name references in context: from {agent} -> from {{agent}}
            (r'from \{(\w+)\}', r'from {{\1}}'),
            # Using {agent} pattern
            (r'[Uu]sing (?:the )?(?:analysis |output |results? )?from \{(\w+)\}', r'Using the output from {{\1}}'),
        ]
        
        result = yaml_content
        for pattern, replacement in variable_patterns:
            # Apply pattern directly - the patterns themselves handle the matching correctly
            result = re.sub(pattern, replacement, result)
        
        return result
    
    def _get_fallback_yaml(self, goal: str, tools: List[str]) -> str:
        """Generate fallback YAML if LLM fails."""
        tools_yaml = '\n      - '.join(tools[:5]) if tools else 'read_file'
        return f'''framework: praisonai
topic: "{goal}"

process: hierarchical
manager_llm: gpt-4o-mini

agents:
  assistant:
    role: AI Assistant
    goal: {goal}
    backstory: |
      You are a helpful AI assistant specialized in completing tasks efficiently.
      You follow instructions carefully and produce high-quality output.
    tools:
      - {tools_yaml}

steps:
  - agent: assistant
    action: "{goal}"
    expected_output: "Completed task output"
'''
    
    def generate_tools_py(self, tools: List[str]) -> str:
        """
        Generate tools.py content with required tool imports.
        
        Args:
            tools: List of tool names to include
            
        Returns:
            Python code string
            
        Notes:
            - web_crawl: Uses full path import since lazy loading returns module
            - search_web: Works with standard import from praisonaiagents.tools
            - tavily_*: Imported from praisonaiagents.tools (not praisonai_tools)
        """
        # Map tools to their import sources
        tool_imports = []
        tool_exports = []
        
        for tool in tools:
            if tool in ['web_crawl', 'crawl_web']:
                # web_crawl needs full path import (lazy loading returns module otherwise)
                if 'web_crawl' not in str(tool_imports):
                    tool_imports.append("from praisonaiagents.tools.web_crawl import web_crawl")
                tool_exports.append('web_crawl')
            elif tool in ['search_web']:
                if 'search_web' not in str(tool_imports):
                    tool_imports.append("from praisonaiagents.tools import search_web")
                tool_exports.append('search_web')
            elif tool in ['tavily_search', 'tavily_extract']:
                if 'tavily' not in str(tool_imports):
                    tool_imports.append("from praisonaiagents.tools import tavily_search, tavily_extract")
                tool_exports.append(tool)
            elif tool in ['read_file', 'write_file', 'list_files']:
                if 'file_tools' not in str(tool_imports):
                    tool_imports.append("from praisonaiagents.tools import read_file, write_file, list_files")
                tool_exports.append(tool)
            elif tool in ['execute_command', 'execute_code']:
                if 'execute' not in str(tool_imports):
                    tool_imports.append("from praisonaiagents.tools import execute_command")
                tool_exports.append(tool)
            elif tool in ['internet_search', 'duckduckgo']:
                if 'duckduckgo' not in str(tool_imports):
                    tool_imports.append("from praisonaiagents.tools import internet_search")
                tool_exports.append('internet_search')
            elif tool in ['crawl4ai', 'crawl4ai_extract']:
                if 'crawl4ai' not in str(tool_imports):
                    tool_imports.append("from praisonaiagents.tools import crawl4ai")
                tool_exports.append(tool)
        
        # Build the tools.py content
        imports_str = '\n'.join(sorted(set(tool_imports))) if tool_imports else '# No specific tool imports needed'
        exports_str = ', '.join(sorted(set(tool_exports))) if tool_exports else ''
        
        return f'''"""
Tools for this recipe.

Auto-generated by praisonai recipe create.
"""

{imports_str}

# Export tools for use in agents.yaml
TOOLS = [{exports_str}] if '{exports_str}' else []


def get_all_tools():
    """Get all tools defined in this recipe."""
    return TOOLS
'''
    
    def generate_template_yaml(self, name: str, goal: str, tools: List[str]) -> str:
        """
        Generate TEMPLATE.yaml metadata file.
        
        Args:
            name: Recipe name
            goal: Goal description
            tools: List of tools used
            
        Returns:
            YAML content string
        """
        tools_yaml = '\n    - '.join(tools[:5]) if tools else 'llm_tool'
        
        return f'''schema_version: "1.0"
name: {name}
version: "1.0.0"
description: |
  {goal}
author: auto-generated
license: Apache-2.0
tags:
  - auto-generated

requires:
  env:
    - OPENAI_API_KEY
  tools:
    - {tools_yaml}

cli:
  command: praisonai recipe run {name}
  examples:
    - praisonai recipe run {name}
    - praisonai recipe run {name} --input "custom input"

safety:
  dry_run_default: false
  overwrites_files: false
'''
    
    def create(
        self,
        goal: str,
        output_dir: Optional[Path] = None,
        agents: Optional[Dict[str, Dict[str, Any]]] = None,
        tools: Optional[Dict[str, List[str]]] = None,
        agent_types: Optional[Dict[str, str]] = None,
    ) -> Path:
        """
        Create a complete recipe folder.
        
        Args:
            goal: Natural language goal description
            output_dir: Parent directory for recipe (default: current dir)
            agents: Optional dict of agent_name -> {role, goal, backstory}
            tools: Optional dict of agent_name -> [tool1, tool2, ...]
            agent_types: Optional dict of agent_name -> type (image, audio, video, etc.)
            
        Returns:
            Path to created recipe folder
        """
        output_dir = output_dir or Path.cwd()
        
        # Generate folder name
        folder_name = self.generate_folder_name(goal)
        recipe_path = output_dir / folder_name
        
        # Create folder
        recipe_path.mkdir(parents=True, exist_ok=True)
        
        # Get tools for this goal (use custom tools if provided)
        if tools:
            # Flatten all tools from custom specification
            all_tools = []
            for agent_tools in tools.values():
                all_tools.extend(agent_tools)
            task_tools = list(set(all_tools))
        else:
            task_tools = self.get_tools_for_task(goal)
        
        # Generate and write agents.yaml
        agents_yaml = self.generate_agents_yaml(
            goal,
            agents=agents,
            tools=tools,
            agent_types=agent_types,
        )
        (recipe_path / "agents.yaml").write_text(agents_yaml)
        
        # Generate and write tools.py
        tools_py = self.generate_tools_py(task_tools)
        (recipe_path / "tools.py").write_text(tools_py)
        
        # Note: TEMPLATE.yaml is no longer generated (simplified 2-file structure)
        # Metadata is now embedded in agents.yaml via the 'metadata' block
        
        logger.info(f"Created recipe at: {recipe_path}")
        
        return recipe_path


__all__ = ['RecipeCreator']
