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
        
        prompt = f"""{sdk_knowledge}

## Your Task

Create an agents.yaml file for this goal:
"{goal}"

Recommended tools based on the goal: {tools_str}
{customization_hints}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANDATORY RULES - YOU MUST FOLLOW ALL OF THESE WITHOUT EXCEPTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## RULE 1: TOOL SELECTION (CRITICAL)
ONLY use these RELIABLE tools that are GUARANTEED to work:
- `internet_search` - General web search (NO API key needed beyond OPENAI)
- `tavily_search` - High-quality web search (REQUIRES TAVILY_API_KEY)
- `read_file` - Read local files (NO extra API key)
- `write_file` - Write local files (NO extra API key)

DO NOT USE these tools (they have loading/compatibility issues):
- scrape_page, crawl, extract_links, extract_text (spider_tools issues)
- crawl4ai, crawl4ai_extract (loading issues)
- wiki_search (not reliably available)

## RULE 2: ENVIRONMENT VARIABLES (CRITICAL)
- ALWAYS include: OPENAI_API_KEY
- ONLY include TAVILY_API_KEY if using tavily_search or tavily_extract
- NEVER include API keys for tools you're not using

## RULE 3: ACTION FORMAT (CRITICAL)
Every action MUST:
1. Start with "Use [tool_name] to..."
2. Contain CONCRETE values, NOT variables
3. Specify exact expected format

GOOD: "Use internet_search to find the top 5 developments in quantum computing. Return a numbered list."
BAD: "Use internet_search to find {{{{topic}}}}" (variables don't work in actions!)
BAD: "Research quantum computing" (doesn't specify which tool!)

## RULE 4: AGENT STRUCTURE (CRITICAL)
- Use 1-2 agents maximum for simple tasks
- Each agent needs: role, goal, backstory, tools, llm
- llm should be: gpt-4o-mini (default)

## RULE 5: STEPS FORMAT (CRITICAL)
- Each step needs: agent, action, expected_output
- Use {{{{agent_name}}}}_output to pass data between agents
- expected_output must describe exact format (list, report, JSON, etc.)

## RULE 6: NO EMPTY FIELDS
- Do NOT include: knowledge: [], memory: false, handoffs: []
- Omit any field that would be empty

## RULE 7: OUTPUT FORMAT
- Output ONLY valid YAML
- No markdown code blocks
- No explanations before or after

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE OF PERFECT RECIPE (COPY THIS STRUCTURE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

metadata:
  name: research-report
  requires:
    env:
      - OPENAI_API_KEY

agents:
  researcher:
    role: Research Analyst
    goal: Find comprehensive information on the requested topic
    backstory: Expert researcher skilled at finding and synthesizing information from multiple sources.
    tools:
      - internet_search
    llm: gpt-4o-mini

steps:
  - agent: researcher
    action: "Use internet_search to find the top 5 key facts about [CONCRETE TOPIC FROM GOAL]. Return a numbered list with each fact containing a title and 2-3 sentence explanation."
    expected_output: "A numbered list of 5 facts, each with: title, explanation (2-3 sentences)"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE WITH TAVILY (when high-quality search needed)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

metadata:
  name: ai-trends-research
  requires:
    env:
      - OPENAI_API_KEY
      - TAVILY_API_KEY

agents:
  researcher:
    role: Research Analyst
    goal: Find the latest AI trends and developments
    backstory: Expert in AI research with access to premium search tools.
    tools:
      - tavily_search
    llm: gpt-4o-mini

  writer:
    role: Report Writer
    goal: Compile research into a well-structured report
    backstory: Technical writer skilled at creating clear, informative reports.
    tools:
      - write_file
    llm: gpt-4o-mini

steps:
  - agent: researcher
    action: "Use tavily_search to find the top 5 AI trends in 2024. Return a numbered list with titles, descriptions, and source URLs."
    expected_output: "A numbered list of 5 trends, each with: title, 2-3 sentence description, source URL"

  - agent: writer
    action: "Using the research findings: {{{{researcher_output}}}}, write a comprehensive markdown report and save it to ai_trends_report.md using write_file."
    expected_output: "A markdown report saved to ai_trends_report.md with introduction, findings, and conclusion"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOW GENERATE THE RECIPE FOR: "{goal}"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
    
    def _get_fallback_yaml(self, goal: str, tools: List[str]) -> str:
        """Generate fallback YAML if LLM fails."""
        tools_yaml = '\n      - '.join(tools[:5]) if tools else 'read_file'
        return f'''framework: praisonai
topic: "{goal}"

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
        """
        # Map tools to their import sources
        tool_imports = []
        tool_exports = []
        
        for tool in tools:
            if tool in ['tavily_search', 'tavily_extract']:
                if 'tavily' not in str(tool_imports):
                    tool_imports.append("from praisonai_tools.tools import tavily_search, tavily_extract")
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
