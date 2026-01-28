"""Tools package for PraisonAI Agents - uses lazy loading for performance"""
from importlib import import_module
from typing import Any

# Lazy loading cache
_tools_lazy_cache = {}

# Export core tool items for organized imports (lightweight)
from .base import BaseTool, ToolResult, ToolValidationError, validate_tool
from .decorator import tool, FunctionTool
from .registry import get_registry, register_tool, get_tool, add_tool, has_tool, remove_tool, list_tools, ToolRegistry
from .tools import Tools

# Export Injected type directly for easy access
from .injected import Injected, AgentState

# Export validation and retry protocols
from .validators import (
    ValidationResult,
    ToolValidatorProtocol,
    AsyncToolValidatorProtocol,
    PassthroughValidator,
)
from .retry import RetryPolicy, FallbackChain, ToolExecutionConfig

# Map of function names to their module and class (if any)
TOOL_MAPPINGS = {
    # Direct functions
    'internet_search': ('.duckduckgo_tools', None),
    'duckduckgo': ('.duckduckgo_tools', None),
    'searxng_search': ('.searxng_tools', None),
    'searxng': ('.searxng_tools', None),
    
    
    # Spider Tools
    'scrape_page': ('.spider_tools', None),
    'extract_links': ('.spider_tools', None),
    'crawl': ('.spider_tools', None),
    'extract_text': ('.spider_tools', None),
    'spider_tools': ('.spider_tools', None),
    
    
    # Shell Tools
    'execute_command': ('.shell_tools', None),
    'list_processes': ('.shell_tools', None),
    'kill_process': ('.shell_tools', None),
    'get_system_info': ('.shell_tools', None),
    'shell_tools': ('.shell_tools', None),


    # File Tools
    'read_file': ('.file_tools', 'FileTools'),
    'write_file': ('.file_tools', 'FileTools'),
    'list_files': ('.file_tools', 'FileTools'),
    'get_file_info': ('.file_tools', 'FileTools'),
    'copy_file': ('.file_tools', 'FileTools'),
    'move_file': ('.file_tools', 'FileTools'),
    'delete_file': ('.file_tools', 'FileTools'),
    'file_tools': ('.file_tools', 'FileTools'),


    # Python Tools
    'execute_code': ('.python_tools', 'PythonTools'),
    'analyze_code': ('.python_tools', 'PythonTools'),
    'format_code': ('.python_tools', 'PythonTools'),
    'lint_code': ('.python_tools', 'PythonTools'),
    'disassemble_code': ('.python_tools', 'PythonTools'),
    'python_tools': ('.python_tools', 'PythonTools'),


    # Chain of Thought Training Tools
    'cot_run': ('.train.data.generatecot', 'GenerateCOT'),           # Orchestrates text solution
    'cot_run_dict': ('.train.data.generatecot', 'GenerateCOT'),      # Orchestrates dict-based solution
    'cot_generate': ('.train.data.generatecot', 'GenerateCOT'),      # Generate text solution
    'cot_generate_dict': ('.train.data.generatecot', 'GenerateCOT'), # Generate structured solution
    'cot_improve': ('.train.data.generatecot', 'GenerateCOT'),       # Improve text solution
    'cot_improve_dict': ('.train.data.generatecot', 'GenerateCOT'),  # Improve dict-based solution
    'cot_check': ('.train.data.generatecot', 'GenerateCOT'),         # Check correctness
    'cot_find_error': ('.train.data.generatecot', 'GenerateCOT'),    # Locate error in solution
    'cot_load_answers': ('.train.data.generatecot', 'GenerateCOT'),  # Load QA pairs
    
    # COT Save/Export with QA Pairs
    'cot_save_solutions_with_qa_pairs': ('.train.data.generatecot', 'GenerateCOT'),    # Save with QA pairs
    'cot_append_solutions_with_qa_pairs': ('.train.data.generatecot', 'GenerateCOT'),  # Append with QA pairs
    'cot_export_json_with_qa_pairs': ('.train.data.generatecot', 'GenerateCOT'),       # Export JSON with QA pairs
    'cot_export_csv_with_qa_pairs': ('.train.data.generatecot', 'GenerateCOT'),        # Export CSV with QA pairs
    'cot_append_csv_with_qa_pairs': ('.train.data.generatecot', 'GenerateCOT'),        # Append CSV with QA pairs
    'cot_save': ('.train.data.generatecot', 'GenerateCOT'),                           # Save single QA to file
    'cot_upload_to_huggingface': ('.train.data.generatecot', 'GenerateCOT'),           # Upload dataset to HuggingFace
    'cot_tools': ('.train.data.generatecot', 'GenerateCOT'),                           # Full toolkit access
    
    
    # Tavily Tools (requires TAVILY_API_KEY)
    'tavily': ('.tavily_tools', None),
    'tavily_search': ('.tavily_tools', None),
    'tavily_extract': ('.tavily_tools', None),
    'tavily_crawl': ('.tavily_tools', None),
    'tavily_map': ('.tavily_tools', None),
    'tavily_search_async': ('.tavily_tools', None),
    'tavily_extract_async': ('.tavily_tools', None),
    'TavilyTools': ('.tavily_tools', 'TavilyTools'),
    'tavily_tools': ('.tavily_tools', None),
    
    # You.com Tools (requires YDC_API_KEY)
    'ydc': ('.youdotcom_tools', None),
    'ydc_search': ('.youdotcom_tools', None),
    'ydc_contents': ('.youdotcom_tools', None),
    'ydc_news': ('.youdotcom_tools', None),
    'ydc_images': ('.youdotcom_tools', None),
    'YouTools': ('.youdotcom_tools', 'YouTools'),
    'youdotcom_tools': ('.youdotcom_tools', None),
    
    # Exa Tools (requires EXA_API_KEY)
    'exa': ('.exa_tools', None),
    'exa_search': ('.exa_tools', None),
    'exa_search_contents': ('.exa_tools', None),
    'exa_find_similar': ('.exa_tools', None),
    'exa_answer': ('.exa_tools', None),
    'exa_search_async': ('.exa_tools', None),
    'exa_search_contents_async': ('.exa_tools', None),
    'exa_answer_async': ('.exa_tools', None),
    'ExaTools': ('.exa_tools', 'ExaTools'),
    'exa_tools': ('.exa_tools', None),
    
    # Crawl4AI Tools (async web crawling)
    'crawl4ai': ('.crawl4ai_tools', None),
    'crawl4ai_many': ('.crawl4ai_tools', None),
    'crawl4ai_extract': ('.crawl4ai_tools', None),
    'crawl4ai_llm_extract': ('.crawl4ai_tools', None),
    'crawl4ai_sync': ('.crawl4ai_tools', None),
    'crawl4ai_extract_sync': ('.crawl4ai_tools', None),
    'Crawl4AITools': ('.crawl4ai_tools', 'Crawl4AITools'),
    'crawl4ai_tools': ('.crawl4ai_tools', None),
    
    # Unified Web Search (auto-fallback across providers)
    'search_web': ('.web_search', None),
    'web_search': ('.web_search', None),  # Alias
    'get_available_providers': ('.web_search', None),
    
    # Unified Web Crawl (auto-fallback across providers)
    'web_crawl': ('.web_crawl', None),
    'crawl_web': ('.web_crawl', None),  # Alias
    'get_available_crawl_providers': ('.web_crawl', None),
    
    # Skill Tools (for Agent Skills script execution)
    'run_skill_script': ('.skill_tools', None),
    'read_skill_file': ('.skill_tools', None),
    'list_skill_scripts': ('.skill_tools', None),
    'create_skill_tools': ('.skill_tools', None),
    'SkillTools': ('.skill_tools', 'SkillTools'),
    'skill_tools': ('.skill_tools', None),
}

_instances = {}  # Cache for class instances

def __getattr__(name: str) -> Any:
    """Smart lazy loading of tools with class method support."""
    if name not in TOOL_MAPPINGS:
        raise AttributeError(f"module '{__package__}' has no attribute '{name}'")
    
    module_path, class_name = TOOL_MAPPINGS[name]
    
    # Return class itself (not instance) for TavilyTools, YouTools, ExaTools, Crawl4AITools
    if name in ('TavilyTools', 'YouTools', 'ExaTools', 'Crawl4AITools'):
        module = import_module(module_path, __package__)
        return getattr(module, class_name)
    
    if class_name is None:
        # Direct function import
        module = import_module(module_path, __package__)
        if name in [
            'duckduckgo', 'internet_search', 'searxng_search', 'searxng',
            'scrape_page', 'extract_links', 'crawl', 'extract_text',
            'execute_command', 'list_processes', 'kill_process', 'get_system_info',
            'tavily', 'tavily_search', 'tavily_extract', 'tavily_crawl', 'tavily_map',
            'tavily_search_async', 'tavily_extract_async',
            'ydc', 'ydc_search', 'ydc_contents', 'ydc_news', 'ydc_images',
            'exa', 'exa_search', 'exa_search_contents', 'exa_find_similar', 'exa_answer',
            'exa_search_async', 'exa_search_contents_async', 'exa_answer_async',
            'crawl4ai', 'crawl4ai_many', 'crawl4ai_extract', 'crawl4ai_llm_extract',
            'crawl4ai_sync', 'crawl4ai_extract_sync',
            'search_web', 'web_search', 'get_available_providers',
            'web_crawl', 'crawl_web', 'get_available_crawl_providers',
            'run_skill_script', 'read_skill_file', 'list_skill_scripts', 'create_skill_tools'
        ]:
            return getattr(module, name)
        if name in ['file_tools', 'spider_tools', 'python_tools', 'shell_tools', 'cot_tools', 'tavily_tools', 'youdotcom_tools', 'exa_tools', 'crawl4ai_tools', 'skill_tools']:
            return module  # Returns the callable module
        return getattr(module, name)
    else:
        # Class method import
        if class_name not in _instances:
            module = import_module(module_path, __package__)
            class_ = getattr(module, class_name)
            _instances[class_name] = class_()
        
        # Get the method and bind it to the instance
        method = getattr(_instances[class_name], name)
        return method

__all__ = list(TOOL_MAPPINGS.keys()) + [
    'Injected', 'AgentState',
    'BaseTool', 'ToolResult', 'ToolValidationError', 'validate_tool',
    'tool', 'FunctionTool',
    'get_registry', 'register_tool', 'get_tool', 'add_tool', 'has_tool', 'remove_tool', 'list_tools', 'ToolRegistry',
    'Tools',
    # Validation and retry protocols
    'ValidationResult', 'ToolValidatorProtocol', 'AsyncToolValidatorProtocol', 'PassthroughValidator',
    'RetryPolicy', 'FallbackChain', 'ToolExecutionConfig',
]