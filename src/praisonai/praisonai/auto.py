"""Auto-generation module for PraisonAI agents and workflows.

This module uses FULL LAZY LOADING for all heavy dependencies:
- crewai: Only loaded when framework='crewai' is used
- autogen: Only loaded when framework='autogen' is used  
- praisonaiagents: Only loaded when framework='praisonai' is used
- litellm: Only loaded when structured output is needed
- openai: Fallback for structured output when litellm unavailable
- praisonai_tools: Only loaded when tools are needed

This ensures minimal import-time overhead.
"""
from pydantic import BaseModel
from typing import Dict, List, Optional, Type, TypeVar
import os
import json
import yaml
from rich import print
import logging

# Type variable for Pydantic models
T = TypeVar('T', bound=BaseModel)

# =============================================================================
# LAZY LOADING INFRASTRUCTURE - All heavy imports are deferred
# =============================================================================

# Cached availability flags (None = not checked yet)
_crewai_available = None
_autogen_available = None
_autogen_v4_available = None
_praisonai_available = None
_praisonai_tools_available = None
_litellm_available = None
_openai_available = None

# Cached module/class references
_crewai_classes = None  # (Agent, Task, Crew)
_autogen_module = None
_autogen_v4_classes = None  # (AssistantAgent, OpenAIChatCompletionClient)
_praisonai_classes = None  # (PraisonAgent, PraisonTask, Agents)
_praisonai_tools = None  # dict of tool classes
_litellm = None
_openai_client = None


# --- CrewAI lazy loading ---
def _check_crewai_available() -> bool:
    """Check if crewai is available (cached)."""
    global _crewai_available
    if _crewai_available is None:
        try:
            import crewai  # noqa: F401
            _crewai_available = True
        except ImportError:
            _crewai_available = False
    return _crewai_available


def _get_crewai():
    """Lazy load crewai classes."""
    global _crewai_classes
    if _crewai_classes is None:
        from crewai import Agent, Task, Crew
        _crewai_classes = (Agent, Task, Crew)
    return _crewai_classes


# --- AutoGen lazy loading ---
def _check_autogen_available() -> bool:
    """Check if autogen v0.2 is available (cached)."""
    global _autogen_available
    if _autogen_available is None:
        try:
            import autogen  # noqa: F401
            _autogen_available = True
        except ImportError:
            _autogen_available = False
    return _autogen_available


def _check_autogen_v4_available() -> bool:
    """Check if autogen v0.4 is available (cached)."""
    global _autogen_v4_available
    if _autogen_v4_available is None:
        try:
            from autogen_agentchat.agents import AssistantAgent  # noqa: F401
            _autogen_v4_available = True
        except ImportError:
            _autogen_v4_available = False
    return _autogen_v4_available


def _get_autogen():
    """Lazy load autogen module."""
    global _autogen_module
    if _autogen_module is None:
        import autogen
        _autogen_module = autogen
    return _autogen_module


def _get_autogen_v4():
    """Lazy load autogen v0.4 classes."""
    global _autogen_v4_classes
    if _autogen_v4_classes is None:
        from autogen_agentchat.agents import AssistantAgent
        from autogen_ext.models.openai import OpenAIChatCompletionClient
        _autogen_v4_classes = (AssistantAgent, OpenAIChatCompletionClient)
    return _autogen_v4_classes


# --- PraisonAI Agents lazy loading ---
def _check_praisonai_available() -> bool:
    """Check if praisonaiagents is available (cached)."""
    global _praisonai_available
    if _praisonai_available is None:
        try:
            import praisonaiagents  # noqa: F401
            _praisonai_available = True
        except ImportError:
            _praisonai_available = False
    return _praisonai_available


def _get_praisonai():
    """Lazy load praisonaiagents classes."""
    global _praisonai_classes
    if _praisonai_classes is None:
        from praisonaiagents import Agent as PraisonAgent, Task as PraisonTask, Agents
        _praisonai_classes = (PraisonAgent, PraisonTask, Agents)
    return _praisonai_classes


# --- PraisonAI Tools lazy loading ---
def _check_praisonai_tools_available() -> bool:
    """Check if praisonai_tools is available (cached)."""
    global _praisonai_tools_available
    if _praisonai_tools_available is None:
        try:
            import praisonai_tools  # noqa: F401
            _praisonai_tools_available = True
        except ImportError:
            _praisonai_tools_available = False
    return _praisonai_tools_available


def _get_praisonai_tools():
    """Lazy load praisonai_tools classes."""
    global _praisonai_tools
    if _praisonai_tools is None:
        from praisonai_tools import (
            CodeDocsSearchTool, CSVSearchTool, DirectorySearchTool, DOCXSearchTool,
            DirectoryReadTool, FileReadTool, TXTSearchTool, JSONSearchTool,
            MDXSearchTool, PDFSearchTool, RagTool, ScrapeElementFromWebsiteTool,
            ScrapeWebsiteTool, WebsiteSearchTool, XMLSearchTool,
            YoutubeChannelSearchTool, YoutubeVideoSearchTool
        )
        _praisonai_tools = {
            'CodeDocsSearchTool': CodeDocsSearchTool,
            'CSVSearchTool': CSVSearchTool,
            'DirectorySearchTool': DirectorySearchTool,
            'DOCXSearchTool': DOCXSearchTool,
            'DirectoryReadTool': DirectoryReadTool,
            'FileReadTool': FileReadTool,
            'TXTSearchTool': TXTSearchTool,
            'JSONSearchTool': JSONSearchTool,
            'MDXSearchTool': MDXSearchTool,
            'PDFSearchTool': PDFSearchTool,
            'RagTool': RagTool,
            'ScrapeElementFromWebsiteTool': ScrapeElementFromWebsiteTool,
            'ScrapeWebsiteTool': ScrapeWebsiteTool,
            'WebsiteSearchTool': WebsiteSearchTool,
            'XMLSearchTool': XMLSearchTool,
            'YoutubeChannelSearchTool': YoutubeChannelSearchTool,
            'YoutubeVideoSearchTool': YoutubeVideoSearchTool,
        }
    return _praisonai_tools


# --- LiteLLM lazy loading ---
def _check_litellm_available() -> bool:
    """Check if litellm is available (cached)."""
    global _litellm_available
    if _litellm_available is None:
        try:
            import litellm  # noqa: F401
            _litellm_available = True
        except ImportError:
            _litellm_available = False
    return _litellm_available


def _get_litellm():
    """Lazy load litellm module."""
    global _litellm
    if _litellm is None:
        import litellm as _litellm_module
        _litellm = _litellm_module
    return _litellm


# --- OpenAI lazy loading ---
def _check_openai_available() -> bool:
    """Check if openai is available (cached)."""
    global _openai_available
    if _openai_available is None:
        try:
            import openai  # noqa: F401
            _openai_available = True
        except ImportError:
            _openai_available = False
    return _openai_available


def _get_openai_client(api_key: str = None, base_url: str = None):
    """Lazy load OpenAI client."""
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url
        )
    return _openai_client


_loglevel = os.environ.get('LOGLEVEL', 'INFO').strip().upper() or 'INFO'
logging.basicConfig(level=_loglevel, format='%(asctime)s - %(levelname)s - %(message)s')

# =============================================================================
# Available Tools List (shared between generators) - Legacy for praisonai_tools
# =============================================================================
AVAILABLE_TOOLS = [
    "CodeDocsSearchTool", "CSVSearchTool", "DirectorySearchTool", "DOCXSearchTool",
    "DirectoryReadTool", "FileReadTool", "TXTSearchTool", "JSONSearchTool",
    "MDXSearchTool", "PDFSearchTool", "RagTool", "ScrapeElementFromWebsiteTool",
    "ScrapeWebsiteTool", "WebsiteSearchTool", "XMLSearchTool",
    "YoutubeChannelSearchTool", "YoutubeVideoSearchTool"
]

# =============================================================================
# Enhanced Tool Discovery from praisonaiagents.tools
# =============================================================================

# Tool categories with their tools from praisonaiagents.tools
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
    # Web search keywords
    'search': 'web_search',
    'find': 'web_search',
    'look up': 'web_search',
    'google': 'web_search',
    'internet': 'web_search',
    'online': 'web_search',
    'web': 'web_search',
    
    # Web scraping keywords
    'scrape': 'web_scraping',
    'crawl': 'web_scraping',
    'extract from website': 'web_scraping',
    'get from url': 'web_scraping',
    'fetch page': 'web_scraping',
    
    # File operation keywords
    'read file': 'file_operations',
    'write file': 'file_operations',
    'save': 'file_operations',
    'load': 'file_operations',
    'open file': 'file_operations',
    'create file': 'file_operations',
    
    # Code execution keywords
    'execute': 'code_execution',
    'run code': 'code_execution',
    'python': 'code_execution',
    'script': 'code_execution',
    'command': 'code_execution',
    'shell': 'code_execution',
    
    # Data processing keywords
    'csv': 'data_processing',
    'excel': 'data_processing',
    'json': 'data_processing',
    'yaml': 'data_processing',
    'xml': 'data_processing',
    'data': 'data_processing',
    'spreadsheet': 'data_processing',
    
    # Research keywords
    'research': 'research',
    'paper': 'research',
    'arxiv': 'research',
    'wikipedia': 'research',
    'academic': 'research',
    'news': 'research',
    
    # Finance keywords
    'stock': 'finance',
    'price': 'finance',
    'market': 'finance',
    'financial': 'finance',
    'trading': 'finance',
    
    # Math keywords
    'calculate': 'math',
    'math': 'math',
    'equation': 'math',
    'compute': 'math',
    'statistics': 'math',
    
    # Database keywords
    'database': 'database',
    'sql': 'database',
    'query': 'database',
    'mongodb': 'database',
    'vector': 'database'
}


def get_all_available_tools() -> Dict[str, List[str]]:
    """
    Get all available tools organized by category.
    
    Returns:
        Dict mapping category names to lists of tool names
    """
    return TOOL_CATEGORIES.copy()


def get_tools_for_task(task_description: str) -> List[str]:
    """
    Analyze a task description and return appropriate tools.
    
    Args:
        task_description: The task to analyze
        
    Returns:
        List of tool names appropriate for the task
    """
    task_lower = task_description.lower()
    matched_categories = set()
    
    # Match keywords to categories
    for keyword, category in TASK_KEYWORD_TO_TOOLS.items():
        if keyword in task_lower:
            matched_categories.add(category)
    
    # Collect tools from matched categories
    tools = []
    for category in matched_categories:
        if category in TOOL_CATEGORIES:
            tools.extend(TOOL_CATEGORIES[category])
    
    # Always include core tools for flexibility
    core_tools = ['read_file', 'write_file', 'execute_command']
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
    
    return unique_tools


def recommend_agent_count(task_description: str) -> int:
    """
    Recommend the optimal number of agents based on task complexity.
    
    Args:
        task_description: The task to analyze
        
    Returns:
        Recommended number of agents (1-4)
    """
    complexity = BaseAutoGenerator.analyze_complexity(task_description)
    
    if complexity == 'simple':
        return 1
    elif complexity == 'moderate':
        return 2
    else:  # complex
        # Count distinct aspects of the task
        task_lower = task_description.lower()
        aspects = 0
        
        aspect_keywords = [
            ['research', 'search', 'find', 'gather'],
            ['analyze', 'evaluate', 'assess', 'review'],
            ['write', 'create', 'generate', 'produce'],
            ['edit', 'refine', 'improve', 'polish'],
            ['coordinate', 'manage', 'orchestrate', 'delegate']
        ]
        
        for keyword_group in aspect_keywords:
            if any(kw in task_lower for kw in keyword_group):
                aspects += 1
        
        return min(max(aspects, 2), 4)  # Between 2 and 4 agents

# =============================================================================
# Base Generator Class (DRY - shared functionality)
# =============================================================================
class BaseAutoGenerator:
    """
    Base class for auto-generators with shared functionality.
    
    Provides:
    - LiteLLM-based structured output (replaces instructor for less dependencies)
    - Environment variable handling for model/API configuration
    - Config list management
    """
    
    def __init__(self, config_list: Optional[List[Dict]] = None):
        """
        Initialize base generator with LLM configuration.
        
        Args:
            config_list: Optional LLM configuration list
        """
        # Support multiple environment variable patterns for better compatibility
        model_name = os.environ.get("MODEL_NAME") or os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini")
        base_url = (
            os.environ.get("OPENAI_BASE_URL") or 
            os.environ.get("OPENAI_API_BASE") or
            os.environ.get("OLLAMA_API_BASE", "https://api.openai.com/v1")
        )
        
        self.config_list = config_list or [
            {
                'model': model_name,
                'base_url': base_url,
                'api_key': os.environ.get("OPENAI_API_KEY")
            }
        ]
    
    def _structured_completion(self, response_model: Type[T], messages: List[Dict], **kwargs) -> T:
        """
        Make a structured LLM completion with provider fallback.
        
        Priority:
        1. LiteLLM (if available) - supports 100+ LLM providers
        2. OpenAI SDK (fallback) - uses beta.chat.completions.parse
        
        Args:
            response_model: Pydantic model class for structured output
            messages: List of message dicts for the LLM
            **kwargs: Additional arguments passed to the LLM
            
        Returns:
            Instance of response_model with parsed response
            
        Raises:
            ImportError: If neither litellm nor openai is installed
        """
        model_name = self.config_list[0]['model']
        
        # Try LiteLLM first (preferred - supports 100+ providers)
        if _check_litellm_available():
            litellm = _get_litellm()
            response = litellm.completion(
                model=model_name,
                messages=messages,
                response_format=response_model,
                **kwargs
            )
            content = response.choices[0].message.content
            return response_model.model_validate_json(content)
        
        # Fallback to OpenAI SDK (uses beta.chat.completions.parse)
        if _check_openai_available():
            client = _get_openai_client(
                api_key=self.config_list[0].get('api_key'),
                base_url=self.config_list[0].get('base_url')
            )
            response = client.beta.chat.completions.parse(
                model=model_name,
                messages=messages,
                response_format=response_model,
                **kwargs
            )
            return response.choices[0].message.parsed
        
        # Neither available - raise helpful error
        raise ImportError(
            "Structured output requires either litellm or openai. "
            "Install with: pip install litellm  OR  pip install openai"
        )
    
    @staticmethod
    def get_available_tools() -> List[str]:
        """Return list of available tools for agent assignment."""
        return AVAILABLE_TOOLS.copy()
    
    @staticmethod
    def analyze_complexity(topic: str) -> str:
        """
        Analyze task complexity based on keywords.
        
        Args:
            topic: The task description
            
        Returns:
            str: Complexity level - 'simple', 'moderate', or 'complex'
        """
        topic_lower = topic.lower()
        
        # Complex task indicators
        complex_keywords = [
            'comprehensive', 'multi-step', 'analyze and', 'research and write',
            'multiple', 'coordinate', 'complex', 'detailed analysis',
            'full report', 'in-depth', 'thorough'
        ]
        
        # Simple task indicators
        simple_keywords = [
            'write a', 'create a', 'simple', 'quick', 'brief',
            'haiku', 'poem', 'summary', 'list', 'single'
        ]
        
        if any(kw in topic_lower for kw in complex_keywords):
            return 'complex'
        elif any(kw in topic_lower for kw in simple_keywords):
            return 'simple'
        else:
            return 'moderate'


# =============================================================================
# Pydantic Models for Structured Output
# =============================================================================

class TaskDetails(BaseModel):
    """Details for a single task."""
    description: str
    expected_output: str

class RoleDetails(BaseModel):
    """Details for a single role/agent."""
    role: str
    goal: str
    backstory: str
    tasks: Dict[str, TaskDetails]
    tools: List[str]

class TeamStructure(BaseModel):
    """Structure for multi-agent team."""
    roles: Dict[str, RoleDetails]

class SingleAgentStructure(BaseModel):
    """Structure for single-agent generation (Anthropic's 'start simple' principle)."""
    name: str
    role: str
    goal: str
    backstory: str
    instructions: str
    tools: List[str] = []
    task_description: str
    expected_output: str

class PatternRecommendation(BaseModel):
    """LLM-based pattern recommendation with reasoning."""
    pattern: str  # sequential, parallel, routing, orchestrator-workers, evaluator-optimizer
    reasoning: str  # Why this pattern was chosen
    confidence: float  # 0.0 to 1.0 confidence score

class ValidationGate(BaseModel):
    """Validation gate for prompt chaining workflows."""
    criteria: str  # What to validate
    pass_action: str  # Action if validation passes (e.g., "continue", "next_step")
    fail_action: str  # Action if validation fails (e.g., "retry", "escalate", "abort")

class AutoGenerator(BaseAutoGenerator):
    """
    Auto-generates agents.yaml files from a topic description.
    
    Inherits from BaseAutoGenerator for shared LLM client functionality.
    
    Usage:
        generator = AutoGenerator(framework="crewai", topic="Create a movie script")
        path = generator.generate()
    """
    
    def __init__(self, topic="Movie Story writing about AI", agent_file="test.yaml", 
                 framework="crewai", config_list: Optional[List[Dict]] = None,
                 pattern: str = "sequential", single_agent: bool = False):
        """
        Initialize the AutoGenerator class with the specified topic, agent file, and framework.
        
        Args:
            topic: The task/topic for agent generation
            agent_file: Output YAML file name
            framework: Framework to use (crewai, autogen, praisonai)
            config_list: Optional LLM configuration
            pattern: Workflow pattern (sequential, parallel, routing, orchestrator-workers, evaluator-optimizer)
            single_agent: If True, generate a single agent instead of a team
        
        Note: autogen framework is different from this AutoGenerator class.
        """
        # Initialize base class first (handles config_list and client)
        super().__init__(config_list=config_list)
        
        # Validate framework availability and show framework-specific messages
        if framework == "crewai" and not _check_crewai_available():
            raise ImportError("""
CrewAI is not installed. Please install with:
    pip install "praisonai[crewai]"
""")
        elif framework == "autogen" and not (_check_autogen_available() or _check_autogen_v4_available()):
            raise ImportError("""
AutoGen is not installed. Please install with:
    pip install "praisonai[autogen]" for v0.2
    pip install "praisonai[autogen-v4]" for v0.4
""")
        elif framework == "praisonai" and not _check_praisonai_available():
            raise ImportError("""
Praisonai is not installed. Please install with:
    pip install praisonaiagents
""")

        # Only show tools message if using a framework and tools are needed
        if (framework in ["crewai", "autogen"]) and not _check_praisonai_tools_available():
            if framework == "autogen":
                logging.warning("""
Tools are not available for autogen. To use tools, install:
    pip install "praisonai[autogen]" for v0.2
    pip install "praisonai[autogen-v4]" for v0.4
""")
            else:
                logging.warning(f"""
Tools are not available for {framework}. To use tools, install:
    pip install "praisonai[{framework}]"
""")

        self.topic = topic
        self.agent_file = agent_file
        self.framework = framework or "praisonai"
        self.pattern = pattern
        self.single_agent = single_agent
    
    def recommend_pattern(self, topic: str = None) -> str:
        """
        Recommend the best workflow pattern based on task characteristics.
        
        Args:
            topic: The task description (uses self.topic if not provided)
            
        Returns:
            str: Recommended pattern name
        """
        task = topic or self.topic
        task_lower = task.lower()
        
        # Keywords that suggest specific patterns
        parallel_keywords = ['multiple', 'concurrent', 'parallel', 'simultaneously', 'different sources', 'compare', 'various']
        routing_keywords = ['classify', 'categorize', 'route', 'different types', 'depending on', 'if...then']
        orchestrator_keywords = ['complex', 'comprehensive', 'multi-step', 'coordinate', 'delegate', 'break down', 'analyze and']
        evaluator_keywords = ['refine', 'improve', 'iterate', 'quality', 'review', 'feedback', 'polish', 'optimize']
        
        # Check for pattern indicators
        if any(kw in task_lower for kw in evaluator_keywords):
            return "evaluator-optimizer"
        elif any(kw in task_lower for kw in orchestrator_keywords):
            return "orchestrator-workers"
        elif any(kw in task_lower for kw in routing_keywords):
            return "routing"
        elif any(kw in task_lower for kw in parallel_keywords):
            return "parallel"
        else:
            return "sequential"

    def generate(self, merge=False):
        """
        Generates a team structure for the specified topic.

        Args:
            merge (bool): Whether to merge with existing agents.yaml file instead of overwriting.

        Returns:
            str: The full path of the YAML file containing the generated team structure.

        Raises:
            Exception: If the generation process fails.

        Usage:
            generator = AutoGenerator(framework="crewai", topic="Create a movie script about Cat in Mars")
            path = generator.generate()
            print(path)
        """
        response = self._structured_completion(
            response_model=TeamStructure,
            messages=[
                {"role": "system", "content": "You are a helpful assistant designed to output complex team structures."},
                {"role": "user", "content": self.get_user_content()}
            ]
        )
        json_data = json.loads(response.model_dump_json())
        self.convert_and_save(json_data, merge=merge)
        full_path = os.path.abspath(self.agent_file)
        return full_path

    def convert_and_save(self, json_data, merge=False):
        """Converts the provided JSON data into the desired YAML format and saves it to a file.

        Args:
            json_data (dict): The JSON data representing the team structure.
            merge (bool): Whether to merge with existing agents.yaml file instead of overwriting.
        """

        # Handle merge functionality
        if merge and os.path.exists(self.agent_file):
            yaml_data = self.merge_with_existing_agents(json_data)
        else:
            # Original behavior: create new yaml_data structure
            yaml_data = {
                "framework": self.framework,
                "topic": self.topic,
                "roles": {},
                "dependencies": []
            }

            for role_id, role_details in json_data['roles'].items():
                yaml_data['roles'][role_id] = {
                    "backstory": "" + role_details['backstory'],
                    "goal": role_details['goal'],
                    "role": role_details['role'],
                    "tasks": {},
                    "tools": role_details.get('tools', [])
                }

                for task_id, task_details in role_details['tasks'].items():
                    yaml_data['roles'][role_id]['tasks'][task_id] = {
                        "description": "" + task_details['description'],
                        "expected_output": "" + task_details['expected_output']
                    }

        # Save to YAML file, maintaining the order
        with open(self.agent_file, 'w') as f:
            yaml.dump(yaml_data, f, allow_unicode=True, sort_keys=False)

    def merge_with_existing_agents(self, new_json_data):
        """
        Merge existing agents.yaml with new auto-generated agents.
        
        Args:
            new_json_data (dict): The JSON data representing the new team structure.
            
        Returns:
            dict: The merged YAML data structure.
        """
        try:
            # Load existing agents.yaml
            with open(self.agent_file, 'r') as f:
                existing_data = yaml.safe_load(f)
            
            if not existing_data:
                # If existing file is empty, treat as new file
                existing_data = {"roles": {}, "dependencies": []}
        except (yaml.YAMLError, FileNotFoundError) as e:
            logging.warning(f"Could not load existing agents file {self.agent_file}: {e}")
            logging.warning("Creating new file instead of merging")
            existing_data = {"roles": {}, "dependencies": []}
        
        # Start with existing data structure
        merged_data = existing_data.copy()
        
        # Ensure required fields exist
        if 'roles' not in merged_data:
            merged_data['roles'] = {}
        if 'dependencies' not in merged_data:
            merged_data['dependencies'] = []
        if 'framework' not in merged_data:
            merged_data['framework'] = self.framework
        
        # Handle topic merging
        existing_topic = merged_data.get('topic', '')
        new_topic = self.topic
        if existing_topic and existing_topic != new_topic:
            merged_data['topic'] = f"{existing_topic} + {new_topic}"
        else:
            merged_data['topic'] = new_topic
        
        # Merge new roles with existing ones
        for role_id, role_details in new_json_data['roles'].items():
            # Check for conflicts and rename if necessary
            final_role_id = role_id
            counter = 1
            while final_role_id in merged_data['roles']:
                final_role_id = f"{role_id}_auto_{counter}"
                counter += 1
            
            # Add the new role
            merged_data['roles'][final_role_id] = {
                "backstory": "" + role_details['backstory'],
                "goal": role_details['goal'],
                "role": role_details['role'],
                "tasks": {},
                "tools": role_details.get('tools', [])
            }
            
            # Add tasks for this role
            for task_id, task_details in role_details['tasks'].items():
                merged_data['roles'][final_role_id]['tasks'][task_id] = {
                    "description": "" + task_details['description'],
                    "expected_output": "" + task_details['expected_output']
                }
        
        return merged_data

    def discover_tools_for_topic(self) -> List[str]:
        """
        Discover appropriate tools for the topic using intelligent matching.
        
        Returns:
            List of tool names appropriate for this topic
        """
        return get_tools_for_task(self.topic)
    
    def get_user_content(self):
        """
        Generates a prompt for the OpenAI API to generate a team structure.
        Uses intelligent tool discovery based on task analysis.

        Args:
            None

        Returns:
            str: The prompt for the OpenAI API.

        Usage:
            generator = AutoGenerator(framework="crewai", topic="Create a movie script about Cat in Mars")
            prompt = generator.get_user_content()
            print(prompt)
        """
        # Pattern-specific guidance
        pattern_guidance = {
            "sequential": "The team will work in sequence. Each role passes output to the next.",
            "parallel": "The team will work in parallel on independent subtasks, then combine results.",
            "routing": "A classifier agent will route requests to specialized agents based on input type.",
            "orchestrator-workers": "A central orchestrator will dynamically delegate tasks to specialized workers.",
            "evaluator-optimizer": "One agent generates content, another evaluates it in a loop until quality criteria are met."
        }
        
        workflow_guidance = pattern_guidance.get(self.pattern, pattern_guidance["sequential"])
        
        # Get recommended tools based on task analysis
        recommended_tools = self.discover_tools_for_topic()
        recommended_agent_count = recommend_agent_count(self.topic)
        complexity = self.analyze_complexity(self.topic)
        
        # Build comprehensive tool list with categories
        all_tools_by_category = []
        for category, tools in TOOL_CATEGORIES.items():
            all_tools_by_category.append(f"  {category}: {', '.join(tools)}")
        tools_reference = "\n".join(all_tools_by_category)
        
        # Also include legacy tools for backward compatibility
        legacy_tools = ", ".join(AVAILABLE_TOOLS)
        
        user_content = f"""Analyze and generate a team structure for: "{self.topic}"

TASK COMPLEXITY ANALYSIS (Pre-computed):
- Complexity: {complexity}
- Recommended agents: {recommended_agent_count}
- Recommended tools based on task keywords: {', '.join(recommended_tools)}

STEP 1: VALIDATE TASK ANALYSIS
Review the pre-computed analysis above. Adjust if needed based on your understanding.

STEP 2: DETERMINE OPTIMAL TEAM SIZE
Based on complexity analysis:
- Simple tasks: 1-2 agents (single focused agent or simple pair)
- Moderate tasks: 2-3 agents (researcher + executor pattern)
- Complex tasks: 3-4 agents (specialized team)

Recommended for this task: {recommended_agent_count} agent(s)

IMPORTANT: Avoid unnecessary complexity. Only add agents if there is meaningful specialization.
Each agent must have a distinct, non-overlapping responsibility.

STEP 3: DESIGN THE TEAM (Pattern: {self.pattern})
{workflow_guidance}

Each agent should have:
- A clear, distinct role with meaningful specialization
- A specific goal
- Relevant backstory
- 1 focused task with clear description and expected output
- Appropriate tools from the recommended list

AVAILABLE TOOLS BY CATEGORY:
{tools_reference}

LEGACY TOOLS (for backward compatibility):
{legacy_tools}

RECOMMENDED TOOLS FOR THIS TASK: {', '.join(recommended_tools)}
Prioritize using the recommended tools. Only add others if specifically needed.

Example structure (2 agents for a research + writing task):
{{
  "roles": {{
    "researcher": {{
      "role": "Research Analyst",
      "goal": "Gather comprehensive information on the topic",
      "backstory": "Expert researcher skilled at finding and synthesizing information.",
      "tools": ["internet_search", "read_file"],
      "tasks": {{
        "research_task": {{
          "description": "Research key information about the topic and compile findings.",
          "expected_output": "Comprehensive research notes with key facts and insights."
        }}
      }}
    }},
    "writer": {{
      "role": "Content Writer",
      "goal": "Create polished final content",
      "backstory": "Skilled writer who transforms research into engaging content.",
      "tools": ["write_file"],
      "tasks": {{
        "writing_task": {{
          "description": "Write the final content based on research findings.",
          "expected_output": "Polished, well-structured final document."
        }}
      }}
    }}
  }}
}}

Now generate the optimal team structure for: {self.topic}
Use the recommended tools: {', '.join(recommended_tools)}
"""
        return user_content

    
# generator = AutoGenerator(framework="crewai", topic="Create a movie script about Cat in Mars")
# print(generator.generate())


# =============================================================================
# Workflow Auto-Generation (Feature Parity)
# =============================================================================

class TaskDetails(BaseModel):
    """Details for a workflow step."""
    agent: str
    action: str
    expected_output: Optional[str] = None

class WorkflowRouteDetails(BaseModel):
    """Details for a route step."""
    name: str
    route: Dict[str, List[str]]

class WorkflowParallelDetails(BaseModel):
    """Details for a parallel step."""
    name: str
    parallel: List[TaskDetails]

class WorkflowAgentDetails(BaseModel):
    """Details for a workflow agent."""
    name: str
    role: str
    goal: str
    instructions: str
    tools: Optional[List[str]] = None

class WorkflowStructure(BaseModel):
    """Structure for auto-generated workflow."""
    name: str
    description: str
    agents: Dict[str, WorkflowAgentDetails]
    steps: List[Dict]  # Can be agent steps, route, parallel, etc.
    gates: Optional[List[ValidationGate]] = None  # Optional validation gates


class WorkflowAutoGenerator(BaseAutoGenerator):
    """
    Auto-generates workflow.yaml files from a topic description.
    
    Inherits from BaseAutoGenerator for shared LLM client functionality.
    
    Usage:
        generator = WorkflowAutoGenerator(topic="Research AI trends and write a report")
        path = generator.generate()
    """
    
    def __init__(self, topic: str = "Research and write about AI", 
                 workflow_file: str = "workflow.yaml",
                 config_list: Optional[List[Dict]] = None,
                 framework: str = "praisonai",
                 single_agent: bool = False):
        """
        Initialize the WorkflowAutoGenerator.
        
        Args:
            topic: The task/topic for the workflow
            workflow_file: Output file name
            config_list: Optional LLM configuration
            framework: Framework to use (praisonai, crewai, autogen)
            single_agent: If True, generate a single agent workflow
        """
        # Initialize base class (handles config_list and client)
        super().__init__(config_list=config_list)
        
        self.topic = topic
        self.workflow_file = workflow_file
        self.framework = framework
        self.single_agent = single_agent
    
    def recommend_pattern(self, topic: str = None) -> str:
        """
        Recommend the best workflow pattern based on task characteristics.
        
        Args:
            topic: The task description (uses self.topic if not provided)
            
        Returns:
            str: Recommended pattern name
            
        Pattern recommendations based on Anthropic's best practices:
        - sequential: Clear step-by-step dependencies
        - parallel: Independent subtasks that can run concurrently
        - routing: Different input types need different handling
        - orchestrator-workers: Complex tasks needing dynamic decomposition
        - evaluator-optimizer: Tasks requiring iterative refinement
        """
        task = topic or self.topic
        task_lower = task.lower()
        
        # Keywords that suggest specific patterns
        parallel_keywords = ['multiple', 'concurrent', 'parallel', 'simultaneously', 'different sources', 'compare', 'various']
        routing_keywords = ['classify', 'categorize', 'route', 'different types', 'depending on', 'if...then']
        orchestrator_keywords = ['complex', 'comprehensive', 'multi-step', 'coordinate', 'delegate', 'break down', 'analyze and']
        evaluator_keywords = ['refine', 'improve', 'iterate', 'quality', 'review', 'feedback', 'polish', 'optimize']
        
        # Check for pattern indicators
        if any(kw in task_lower for kw in evaluator_keywords):
            return "evaluator-optimizer"
        elif any(kw in task_lower for kw in orchestrator_keywords):
            return "orchestrator-workers"
        elif any(kw in task_lower for kw in routing_keywords):
            return "routing"
        elif any(kw in task_lower for kw in parallel_keywords):
            return "parallel"
        else:
            return "sequential"
    
    def recommend_pattern_llm(self, topic: str = None) -> PatternRecommendation:
        """
        Use LLM to recommend the best workflow pattern with reasoning.
        
        Args:
            topic: The task description (uses self.topic if not provided)
            
        Returns:
            PatternRecommendation: Pattern with reasoning and confidence score
        """
        task = topic or self.topic
        
        prompt = f"""Analyze this task and recommend the best workflow pattern:

Task: "{task}"

Available patterns:
1. sequential - Agents work one after another, passing output to the next
2. parallel - Multiple agents work concurrently on independent subtasks
3. routing - A classifier routes requests to specialized agents based on input type
4. orchestrator-workers - Central orchestrator dynamically delegates to specialized workers
5. evaluator-optimizer - Generator creates content, evaluator reviews in a loop until quality met

Respond with:
- pattern: The recommended pattern name
- reasoning: Why this pattern is best for this task
- confidence: Your confidence score (0.0 to 1.0)
"""
        
        response = self._structured_completion(
            response_model=PatternRecommendation,
            messages=[
                {"role": "system", "content": "You are an expert at designing AI agent workflows."},
                {"role": "user", "content": prompt}
            ]
        )
        
        return response
    
    def generate(self, pattern: str = "sequential", merge: bool = False) -> str:
        """
        Generate a workflow YAML file.
        
        Args:
            pattern: Workflow pattern - "sequential", "routing", "parallel", "loop",
                     "orchestrator-workers", "evaluator-optimizer"
            merge: If True, merge with existing workflow file instead of overwriting
            
        Returns:
            Path to the generated workflow file
        """
        response = self._structured_completion(
            response_model=WorkflowStructure,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that designs workflow structures."},
                {"role": "user", "content": self._get_prompt(pattern)}
            ]
        )
        
        json_data = json.loads(response.model_dump_json())
        
        if merge and os.path.exists(self.workflow_file):
            return self._save_workflow(self.merge_with_existing_workflow(json_data), pattern)
        return self._save_workflow(json_data, pattern)
    
    def merge_with_existing_workflow(self, new_data: Dict) -> Dict:
        """
        Merge new workflow data with existing workflow file.
        
        Args:
            new_data: The new workflow data to merge
            
        Returns:
            Dict: Merged workflow data
        """
        try:
            with open(self.workflow_file, 'r') as f:
                existing_data = yaml.safe_load(f)
            
            if not existing_data:
                return new_data
        except (yaml.YAMLError, FileNotFoundError) as e:
            logging.warning(f"Could not load existing workflow file {self.workflow_file}: {e}")
            return new_data
        
        # Merge agents (avoid duplicates)
        merged_agents = existing_data.get('agents', {}).copy()
        for agent_id, agent_data in new_data.get('agents', {}).items():
            # Rename if conflict
            final_id = agent_id
            counter = 1
            while final_id in merged_agents:
                final_id = f"{agent_id}_auto_{counter}"
                counter += 1
            merged_agents[final_id] = agent_data
        
        # Merge steps (append new steps)
        merged_steps = existing_data.get('steps', []) + new_data.get('steps', [])
        
        # Create merged structure
        merged = {
            'name': existing_data.get('name', new_data.get('name', 'Merged Workflow')),
            'description': f"{existing_data.get('description', '')} + {new_data.get('description', '')}",
            'agents': merged_agents,
            'steps': merged_steps
        }
        
        return merged
    
    def _get_prompt(self, pattern: str) -> str:
        """Generate the prompt based on the workflow pattern."""
        # Analyze complexity to determine agent count
        complexity = self.analyze_complexity(self.topic)
        if complexity == 'simple':
            agent_guidance = "Create 1-2 agents (simple task detected)."
        elif complexity == 'complex':
            agent_guidance = "Create 3-4 agents (complex task detected)."
        else:
            agent_guidance = "Create 2-3 agents (moderate task detected)."
        
        # Get available tools
        tools_list = ", ".join(self.get_available_tools())
        
        base_prompt = f"""Generate a workflow structure for: "{self.topic}"

STEP 1: ANALYZE TASK COMPLEXITY
- Is this a simple task (1-2 agents)?
- Does it require multiple specialists (2-3 agents)?
- Is it complex with many dependencies (3-4 agents)?

STEP 2: DESIGN WORKFLOW
The workflow should use the "{pattern}" pattern.
{agent_guidance}
Each agent should have clear roles and instructions.
Each step should have a clear action.

STEP 3: ASSIGN TOOLS (if needed)
Available Tools: {tools_list}
Only assign tools if the task requires them. Use empty list or null if no tools needed.

"""
        
        if pattern == "routing":
            base_prompt += """
Include a classifier agent that routes to different specialized agents.
The route step should have at least 2 routes plus a default.

Example structure:
{
  "name": "Routing Workflow",
  "description": "Routes requests to specialized agents",
  "agents": {
    "classifier": {"name": "Classifier", "role": "Request Classifier", "goal": "Classify requests", "instructions": "Respond with ONLY: technical, creative, or general"},
    "tech_agent": {"name": "TechExpert", "role": "Technical Expert", "goal": "Handle technical questions", "instructions": "Provide technical answers"}
  },
  "steps": [
    {"agent": "classifier", "action": "Classify: {{input}}"},
    {"name": "routing", "route": {"technical": ["tech_agent"], "default": ["tech_agent"]}}
  ]
}
"""
        elif pattern == "parallel":
            base_prompt += """
Include multiple agents that work in parallel, then an aggregator.

Example structure:
{
  "name": "Parallel Workflow",
  "description": "Multiple agents work concurrently",
  "agents": {
    "researcher1": {"name": "Researcher1", "role": "Market Analyst", "goal": "Research market", "instructions": "Provide market insights"},
    "researcher2": {"name": "Researcher2", "role": "Competitor Analyst", "goal": "Research competitors", "instructions": "Provide competitor insights"},
    "aggregator": {"name": "Aggregator", "role": "Synthesizer", "goal": "Combine findings", "instructions": "Synthesize all research"}
  },
  "steps": [
    {"name": "parallel_research", "parallel": [
      {"agent": "researcher1", "action": "Research market for {{input}}"},
      {"agent": "researcher2", "action": "Research competitors for {{input}}"}
    ]},
    {"agent": "aggregator", "action": "Combine all findings"}
  ]
}
"""
        elif pattern == "orchestrator-workers":
            base_prompt += """
Create an orchestrator-workers workflow where a central orchestrator dynamically delegates tasks to specialized workers.
The orchestrator analyzes the input, decides which workers are needed, and synthesizes results.

Example structure:
{
  "name": "Orchestrator-Workers Workflow",
  "description": "Central orchestrator delegates to specialized workers",
  "agents": {
    "orchestrator": {"name": "Orchestrator", "role": "Task Coordinator", "goal": "Analyze tasks and delegate to appropriate workers", "instructions": "Break down the task, identify required specialists, and coordinate their work. Output a JSON with 'subtasks' array listing which workers to invoke."},
    "researcher": {"name": "Researcher", "role": "Research Specialist", "goal": "Gather information", "instructions": "Research and provide factual information"},
    "analyst": {"name": "Analyst", "role": "Data Analyst", "goal": "Analyze data and patterns", "instructions": "Analyze information and identify insights"},
    "writer": {"name": "Writer", "role": "Content Writer", "goal": "Create written content", "instructions": "Write clear, engaging content"},
    "synthesizer": {"name": "Synthesizer", "role": "Results Synthesizer", "goal": "Combine all worker outputs", "instructions": "Synthesize all worker outputs into a coherent final result"}
  },
  "steps": [
    {"agent": "orchestrator", "action": "Analyze task and determine required workers: {{input}}"},
    {"name": "worker_dispatch", "parallel": [
      {"agent": "researcher", "action": "Research: {{input}}"},
      {"agent": "analyst", "action": "Analyze: {{input}}"},
      {"agent": "writer", "action": "Draft content for: {{input}}"}
    ]},
    {"agent": "synthesizer", "action": "Combine all worker outputs into final result"}
  ]
}
"""
        elif pattern == "evaluator-optimizer":
            base_prompt += """
Create an evaluator-optimizer workflow where one agent generates content and another evaluates it in a loop.
The generator improves based on evaluator feedback until quality criteria are met.

Example structure:
{
  "name": "Evaluator-Optimizer Workflow",
  "description": "Iterative refinement through generation and evaluation",
  "agents": {
    "generator": {"name": "Generator", "role": "Content Generator", "goal": "Generate high-quality content", "instructions": "Create content based on the input. If feedback is provided, improve the content accordingly."},
    "evaluator": {"name": "Evaluator", "role": "Quality Evaluator", "goal": "Evaluate content quality", "instructions": "Evaluate the content on: clarity, accuracy, completeness, and relevance. Score 1-10 for each. If average score < 7, provide specific improvement feedback. If score >= 7, respond with 'APPROVED'."}
  },
  "steps": [
    {"agent": "generator", "action": "Generate initial content for: {{input}}"},
    {"name": "evaluation_loop", "loop": {
      "agent": "evaluator",
      "action": "Evaluate the generated content",
      "condition": "output does not contain 'APPROVED'",
      "max_iterations": 3,
      "feedback_to": "generator"
    }},
    {"agent": "generator", "action": "Finalize content based on all feedback"}
  ]
}
"""
        else:  # sequential
            base_prompt += """
Create a sequential workflow where agents work one after another.

Example structure:
{
  "name": "Sequential Workflow",
  "description": "Agents work in sequence",
  "agents": {
    "researcher": {"name": "Researcher", "role": "Research Analyst", "goal": "Research topics", "instructions": "Provide research findings"},
    "writer": {"name": "Writer", "role": "Content Writer", "goal": "Write content", "instructions": "Write clear content"}
  },
  "steps": [
    {"agent": "researcher", "action": "Research: {{input}}"},
    {"agent": "writer", "action": "Write based on: {{previous_output}}"}
  ]
}
"""
        
        base_prompt += f"\nGenerate a workflow for: {self.topic}"
        return base_prompt
    
    def _save_workflow(self, data: Dict, pattern: str) -> str:
        """Save the workflow to a YAML file."""
        # Build the workflow YAML structure
        workflow_yaml = {
            'name': data.get('name', 'Auto-Generated Workflow'),
            'description': data.get('description', ''),
            'framework': 'praisonai',
            'workflow': {
                'output': 'verbose',  # Use output= instead of deprecated verbose=
                'planning': False,
                'reasoning': False
            },
            'agents': {},
            'steps': data.get('steps', [])
        }
        
        # Convert agents
        for agent_id, agent_data in data.get('agents', {}).items():
            workflow_yaml['agents'][agent_id] = {
                'name': agent_data.get('name', agent_id),
                'role': agent_data.get('role', 'Assistant'),
                'goal': agent_data.get('goal', ''),
                'instructions': agent_data.get('instructions', '')
            }
            if agent_data.get('tools'):
                workflow_yaml['agents'][agent_id]['tools'] = agent_data['tools']
        
        # Write to file
        full_path = os.path.abspath(self.workflow_file)
        with open(full_path, 'w') as f:
            yaml.dump(workflow_yaml, f, default_flow_style=False, sort_keys=False)
        
        return full_path