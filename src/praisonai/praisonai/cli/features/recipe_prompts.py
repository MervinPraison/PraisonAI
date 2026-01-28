"""
Shared prompt constants for recipe creation and optimization.

DRY: This module extracts common prompts used by both recipe_creator.py
and recipe_optimizer.py to avoid duplication.
"""

# Common issue patterns and their fixes - comprehensive patterns
COMMON_ISSUE_FIXES = {
    "tool_not_called": {
        "pattern": r"(failed to call|did not call|without calling|tool.*not.*used|did not use)",
        "fix": "Add explicit tool call instruction: 'You MUST call the {tool} tool. Do NOT respond without calling {tool} first. Return [format] from the tool results.'",
        "severity": "critical",
    },
    "missing_output_format": {
        "pattern": r"(output.*format|expected.*format|format.*missing|unstructured|no format)",
        "fix": "Add explicit expected_output format: 'Return a structured response with: 1) [section1], 2) [section2], 3) [section3]'",
        "severity": "high",
    },
    "hallucination": {
        "pattern": r"(hallucin|fabricat|made up|incorrect.*fact|invented|false information)",
        "fix": "Add grounding instruction: 'Only use information from the provided context or tool results. Do NOT make up facts, statistics, or sources.'",
        "severity": "critical",
    },
    "truncation": {
        "pattern": r"(truncat|incomplete|cut off|partial|missing.*content)",
        "fix": "Add completeness instruction: 'Ensure your response is COMPLETE. Include ALL required sections. Do not stop mid-response.'",
        "severity": "high",
    },
    "context_not_used": {
        "pattern": r"(context.*not.*used|ignored.*context|failed.*utilize|did not reference)",
        "fix": "Add context reference: 'Use the information from {{previous_agent}}_output. Extract specific data points and reference them in your response.'",
        "severity": "high",
    },
    "missing_goal": {
        "pattern": r"(missing.*goal|no.*goal|goal.*empty|unclear.*objective)",
        "fix": "Add clear goal: 'Your goal is to [specific objective]. Success means [measurable outcome].'",
        "severity": "critical",
    },
    "vague_action": {
        "pattern": r"(vague|unclear|ambiguous|not specific|too general)",
        "fix": "Make action specific: Replace vague verbs with concrete instructions. Include exact tool names, expected counts, and output format.",
        "severity": "high",
    },
    "missing_verification": {
        "pattern": r"(no verification|unverified|not validated|needs.*check)",
        "fix": "Add verification step: 'Verify your output contains all required elements before responding.'",
        "severity": "medium",
    },
    "manager_rejected": {
        "pattern": r"(manager rejected|hierarchical.*failed|validation.*failed|step.*rejected)",
        "fix": "Make tool calls explicit and mandatory. Add: 'You MUST call [tool]. Do NOT respond without calling [tool] first. Return [format] from the tool results.'",
        "severity": "critical",
    },
    "hierarchical_failure": {
        "pattern": r"(status.*failed|failure_reason|workflow.*stopped)",
        "fix": "Strengthen action instructions: explicit tool calls, specific output format, grounding against hallucination.",
        "severity": "critical",
    },
}

# Comprehensive tool documentation
TOOL_DOCUMENTATION = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AVAILABLE TOOLS (Use exact names)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## WEB SEARCH (Safe - No approval required):
- `search_web` - ⭐ RECOMMENDED - Unified search with auto-fallback
- `internet_search` - DuckDuckGo search (FREE, no API key)
- `tavily_search` - High-quality AI search (needs TAVILY_API_KEY)
- `exa_search` - Exa AI search (needs EXA_API_KEY)

## WEB SCRAPING (Safe):
- `scrape_page` - Scrape web page content
- `extract_links` - Extract links from URL
- `crawl4ai` - Advanced web crawling

## FILE TOOLS - READ (Safe):
- `read_file` - Read local files
- `list_files` - List directory contents

## FILE TOOLS - WRITE (⚠️ APPROVAL REQUIRED):
- `write_file` - Write to files
- `delete_file` - Delete files

## CODE EXECUTION (⚠️ APPROVAL REQUIRED):
- `execute_command` - Run shell commands
- `execute_code` - Execute Python code

## DATA PROCESSING (Safe):
- `read_csv`, `read_json`, `read_yaml`, `read_excel`
"""

# Hierarchical process documentation
HIERARCHICAL_PROCESS_DOC = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HIERARCHICAL PROCESS (CRITICAL - MUST PRESERVE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## What is Hierarchical Process?
In hierarchical mode, a MANAGER agent validates each step's output before
proceeding to the next step. If the manager rejects a step, the workflow
stops with status='failed' and includes a failure_reason.

## MANDATORY YAML Fields (NEVER REMOVE):
```yaml
process: hierarchical
manager_llm: gpt-4o-mini
```

## Why Hierarchical Matters:
1. **Quality Control**: Manager validates each step's output
2. **Tool Call Enforcement**: Manager rejects steps where tools weren't called
3. **Prevents Cascading Errors**: Bad outputs don't propagate to next steps
4. **Hallucination Detection**: Manager catches fabricated data

## Hierarchical-Specific Optimization Rules:
1. **Tool calls are MANDATORY** - Manager will reject if tools aren't called
2. **Output must match expected_output** - Manager validates format
3. **Context must be used** - Manager checks if previous output was utilized
4. **No hallucination** - Manager rejects fabricated data

## Common Manager Rejection Reasons:
- "Agent did not call the required tool"
- "Output does not match expected format"
- "Agent did not use context from previous step"
- "Output contains fabricated/unverified information"

## How to Fix Manager Rejections:
1. Make tool calls EXPLICIT: "You MUST call search_web. Do NOT respond without calling it."
2. Specify exact output format in expected_output
3. Reference previous output: "Using {{agent}}_output, extract..."
4. Add grounding: "Only use information from tool results. Do NOT fabricate."
"""

# Specialized agent documentation
SPECIALIZED_AGENTS_DOC = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SPECIALIZED AGENT TYPES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## AudioAgent - Text-to-Speech / Speech-to-Text
- Use `agent: AudioAgent` in agent definition
- TTS: llm: openai/tts-1 or openai/tts-1-hd
- STT: llm: openai/whisper-1 or groq/whisper-large-v3

## ImageAgent - Image Generation
- Use `agent: ImageAgent` in agent definition
- llm: openai/dall-e-3 or openai/dall-e-2

## VideoAgent - Video Generation
- Use `agent: VideoAgent` in agent definition
- llm: openai/sora-2 or gemini/veo-3.0-generate-preview

## OCRAgent - Text Extraction from Documents
- Use `agent: OCRAgent` in agent definition
- llm: mistral/mistral-ocr-latest (needs MISTRAL_API_KEY)

## DeepResearchAgent - Comprehensive Research
- Use `agent: DeepResearchAgent` in agent definition
"""

# Tool call reliability instructions
TOOL_CALL_RELIABILITY_DOC = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOL CALL RELIABILITY (CRITICAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For agents with tools, the action MUST:
1. **Name the tool explicitly**: "You MUST call the search_web tool"
2. **Forbid responding without tool**: "Do NOT respond without calling search_web first"
3. **Require using results**: "Return [format] from the tool results"

## Example Action for Tool-Using Agent:
```
You MUST call the search_web tool to search for [TOPIC].
Do NOT respond without calling search_web first.
Return at least 5 key findings with: title, description, and source URL from the search results.
```

## YAML Field for Forcing Tool Usage:
```yaml
tool_choice: required  # Forces LLM to call a tool before responding
```
"""

# Anti-hallucination instructions
ANTI_HALLUCINATION_DOC = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANTI-HALLUCINATION RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For tool-using agents, add these grounding instructions:
- "Your response MUST be based ONLY on actual tool results"
- "Do NOT make up information, use training data, or respond if tool fails"
- "Only use information from the provided context or tool results"
- "Do NOT fabricate facts, statistics, or sources"
"""


def get_all_documentation() -> str:
    """
    Get all documentation sections combined.
    
    Returns:
        Combined documentation string
    """
    return "\n\n".join([
        TOOL_DOCUMENTATION,
        HIERARCHICAL_PROCESS_DOC,
        SPECIALIZED_AGENTS_DOC,
        TOOL_CALL_RELIABILITY_DOC,
        ANTI_HALLUCINATION_DOC,
    ])


__all__ = [
    'COMMON_ISSUE_FIXES',
    'TOOL_DOCUMENTATION',
    'HIERARCHICAL_PROCESS_DOC',
    'SPECIALIZED_AGENTS_DOC',
    'TOOL_CALL_RELIABILITY_DOC',
    'ANTI_HALLUCINATION_DOC',
    'get_all_documentation',
]
