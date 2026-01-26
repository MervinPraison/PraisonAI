"""
Recipe Creator for PraisonAI.

Automatically generates recipe folders with agents.yaml, TEMPLATE.yaml, and tools.py
based on a natural language goal description.

DRY: Reuses AutoGenerator patterns and SDK knowledge prompt.
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from .sdk_knowledge import get_sdk_knowledge_prompt

logger = logging.getLogger(__name__)


class RecipeCreator:
    """
    Creates optimized recipes from natural language goals.
    
    Usage:
        creator = RecipeCreator()
        path = creator.create("Build a web scraper for news articles")
    """
    
    # Tool categories for selection (from auto.py)
    TOOL_CATEGORIES = {
        'web_search': [
            'internet_search', 'duckduckgo', 'tavily_search', 'exa_search',
            'search_web', 'ydc_search', 'searxng_search'
        ],
        'web_scraping': [
            'scrape_page', 'extract_links', 'crawl', 'extract_text',
            'crawl4ai', 'crawl4ai_extract', 'get_article'
        ],
        'file_operations': [
            'read_file', 'write_file', 'list_files', 'get_file_info',
            'copy_file', 'move_file', 'delete_file'
        ],
        'code_execution': [
            'execute_command', 'execute_code', 'analyze_code', 'format_code'
        ],
        'data_processing': [
            'read_csv', 'write_csv', 'analyze_csv', 'read_json', 'write_json',
            'read_excel', 'write_excel', 'read_yaml', 'write_yaml', 'read_xml'
        ],
        'research': [
            'search_arxiv', 'get_arxiv_paper', 'wiki_search', 'wiki_summary',
            'get_news_sources', 'get_trending_topics'
        ],
        'finance': [
            'get_stock_price', 'get_stock_info', 'get_historical_data'
        ],
        'math': [
            'evaluate', 'solve_equation', 'convert_units', 'calculate_statistics'
        ],
        'database': [
            'query', 'create_table', 'load_data', 'find_documents', 'vector_search'
        ]
    }
    
    # Keywords that map to tool categories
    TASK_KEYWORD_TO_TOOLS = {
        'search': 'web_search',
        'find': 'web_search',
        'look up': 'web_search',
        'google': 'web_search',
        'scrape': 'web_scraping',
        'crawl': 'web_scraping',
        'extract': 'web_scraping',
        'website': 'web_scraping',
        'web page': 'web_scraping',
        'file': 'file_operations',
        'read': 'file_operations',
        'write': 'file_operations',
        'save': 'file_operations',
        'code': 'code_execution',
        'run': 'code_execution',
        'execute': 'code_execution',
        'script': 'code_execution',
        'csv': 'data_processing',
        'json': 'data_processing',
        'excel': 'data_processing',
        'data': 'data_processing',
        'research': 'research',
        'paper': 'research',
        'arxiv': 'research',
        'wikipedia': 'research',
        'stock': 'finance',
        'price': 'finance',
        'market': 'finance',
        'calculate': 'math',
        'math': 'math',
        'equation': 'math',
        'database': 'database',
        'sql': 'database',
        'query': 'database',
    }
    
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

CRITICAL Requirements:
1. Use 1-3 agents depending on task complexity
2. Assign only relevant tools from the recommended list
3. Include clear backstory and expected_output for each task
4. Use sequential workflow unless parallel is clearly needed
5. Output ONLY valid YAML - no markdown, no explanations

CRITICAL - Agent Behavior:
6. Each action MUST specify which tool to use (e.g., "Use internet_search to find...")
7. Actions must be SPECIFIC and ACTIONABLE - agents should act immediately, not ask for input
8. Include concrete examples or default values in actions (e.g., specific URLs, topics)
9. Use {{{{previous_agent}}}}_output to reference previous agent's output in subsequent steps
10. expected_output must describe the exact format expected (list, report, JSON, etc.)

Example of GOOD action:
  action: "Use internet_search to find the latest AI trends in 2024. Compile a list of top 5 trends with brief descriptions."
  expected_output: "A numbered list of 5 AI trends, each with a 2-3 sentence description and source URL"

Example of BAD action (DO NOT DO THIS):
  action: "Research AI trends"  # Too vague, agent will ask for clarification
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
                    tool_imports.append("from praisonaiagents.tools import tavily_search")
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
