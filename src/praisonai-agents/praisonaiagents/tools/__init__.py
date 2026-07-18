"""Tools package for PraisonAI Agents - uses lazy loading for performance"""
from importlib import import_module
from typing import Any

# Note: actual lazy loading cache is implemented with _loaded_classes in __getattr__

# Export core tool items for organized imports (lightweight)
from .base import (
    BaseTool, ToolResult, ToolValidationError, validate_tool,
    multimodal_content, text_part, image_part, file_part,
)
from .decorator import tool, FunctionTool
from .call_executor import (
    ToolProgress, DeferredToolResult, defer,
    ToolTimeoutError, ToolCancelledError,
)
from .registry import get_registry, register_tool, get_tool, add_tool, has_tool, remove_tool, list_tools, list_available_tools, list_tools_with_allowed_filter, list_tools_with_hermes_filter, ToolRegistry
from .resolver import resolve_tool_name, resolve_tool_names, ToolResolutionError
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

# Circuit breaker functionality (lazy loaded)
_CIRCUIT_BREAKER_EXPORTS = frozenset({
    'CircuitBreaker', 'CircuitBreakerProtocol', 'CircuitBreakerConfig', 'CircuitBreakerException',
    'CircuitBreakerStats', 'CircuitState', 'HealthCheckProtocol', 'CircuitBreakerRegistry',
    'get_circuit_breaker', 'get_all_circuit_breaker_stats', 'reset_all_circuit_breakers',
    # Integration utilities
    'with_circuit_breaker', 'LLMCircuitBreakerIntegration', 'MemoryCircuitBreakerIntegration',
    'MCPCircuitBreakerIntegration', 'create_resilient_external_call', 'integrate_with_retry_policy',
    # Health monitoring
    'HealthMonitor', 'HealthMetrics', 'ServiceHealthConfig', 'TelemetryProtocol',
    'get_health_monitor', 'get_circuit_breaker_dashboard_data'
})

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
    'execute_code': ('.python_tools', None),
    'execute_code_with_tools': ('.python_tools', None),
    'analyze_code': ('.python_tools', None),
    'format_code': ('.python_tools', None),
    'lint_code': ('.python_tools', None),
    'disassemble_code': ('.python_tools', None),
    'python_tools': ('.python_tools', None),


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
    'web_crawl': ('.web_crawl_tools', None),
    'crawl_web': ('.web_crawl_tools', None),  # Alias
    'get_available_crawl_providers': ('.web_crawl_tools', None),
    
    # Skill Tools (for Agent Skills script execution)
    'run_skill_script': ('.skill_tools', None),
    'read_skill_file': ('.skill_tools', None),
    'list_skill_scripts': ('.skill_tools', None),
    'create_skill_tools': ('.skill_tools', None),
    'SkillTools': ('.skill_tools', 'SkillTools'),
    'skill_tools': ('.skill_tools', None),
    
    # Github Tools
    'github_create_branch': ('.github_tools', None),
    'github_commit_and_push': ('.github_tools', None),
    'github_create_pull_request': ('.github_tools', None),
    'github_tools': ('.github_tools', None),
    
    # JIRA Tools (watch and monitor JIRA issues/projects)
    'jira_watch_issue': ('.jira_tools', None),
    'jira_watch_project': ('.jira_tools', None),
    'jira_get_issue_info': ('.jira_tools', None),
    'jira_search_issues': ('.jira_tools', None),
    'jira_tools': ('.jira_tools', None),
    
    # Schedule Tools (agent-centric scheduling)
    'schedule_add': ('.schedule_tools', None),
    'schedule_list': ('.schedule_tools', None),
    'schedule_remove': ('.schedule_tools', None),
    'schedule_tools': ('.schedule_tools', None),

    # Computer Use Tools (agent-centric screen control - Issue #516)
    'computer_screenshot': ('.computer_tools', None),
    'computer_screen_size': ('.computer_tools', None),
    'computer_move': ('.computer_tools', None),
    'computer_click': ('.computer_tools', None),
    'computer_type': ('.computer_tools', None),
    'computer_key': ('.computer_tools', None),
    'computer_scroll': ('.computer_tools', None),
    'set_computer_approval': ('.computer_tools', None),
    'computer_tools': ('.computer_tools', None),

    # Proactive messaging (agent-facing gateway delivery)
    'send_message': ('.messaging_tools', None),
    'messaging_tools': ('.messaging_tools', None),
    
    # Search Tools (fast, capped content grep + file glob)
    'grep': ('.search_tools', None),
    'glob': ('.search_tools', None),
    'search_tools': ('.search_tools', None),

    # AST-Grep Tools (structural code search/rewrite)
    'ast_grep_search': ('.ast_grep_tool', None),
    'ast_grep_rewrite': ('.ast_grep_tool', None),
    'ast_grep_scan': ('.ast_grep_tool', None),
    'is_ast_grep_available': ('.ast_grep_tool', None),
    'get_ast_grep_tools': ('.ast_grep_tool', None),
    'ast_grep_tools': ('.ast_grep_tool', None),

    # Edit Tools (diff-based file editing with fuzzy matching + LSP diagnostics)
    'edit_file': ('.edit_tools', None),
    'apply_patch': ('.edit_tools', None),
    'create_edit_tools': ('.edit_tools', None),
    'edit_tools': ('.edit_tools', None),

    # Todo Tools (agent-facing task tracking)
    'todo_add': ('.todo_tools', None),
    'todo_list': ('.todo_tools', None),
    'todo_update': ('.todo_tools', None),
    'create_todo_tools': ('.todo_tools', None),
    'todo_tools': ('.todo_tools', None),

    # LSP Navigation Tools (language-server-accurate code navigation)
    'lsp_definition': ('.lsp_tools', None),
    'lsp_references': ('.lsp_tools', None),
    'lsp_hover': ('.lsp_tools', None),
    'lsp_document_symbols': ('.lsp_tools', None),
    'lsp_workspace_symbols': ('.lsp_tools', None),
    
    # Memory Tools (active memory store/search for agents)
    'store_memory': ('.memory', None),
    'search_memory': ('.memory', None),
    
    # Learning Tools (active categorized knowledge store/search)
    'store_learning': ('.learning', None),
    'search_learning': ('.learning', None),

    # Session Tools (cross-session conversation recall - Issue #2184)
    'session_search': ('.session_tools', None),
    'create_session_tools': ('.session_tools', None),
    'SessionTools': ('.session_tools', 'SessionTools'),

    # Email Tools (AgentMail-based send/read/list/reply/create)
    'send_email': ('.email_tools', None),
    'list_emails': ('.email_tools', None),
    'read_email': ('.email_tools', None),
    'reply_email': ('.email_tools', None),
    'list_inboxes': ('.email_tools', None),
    'create_inbox': ('.email_tools', None),
    # Email Tools (SMTP/IMAP-based — direct mailbox credentials)
    'smtp_send_email': ('.email_tools', None),
    'smtp_read_inbox': ('.email_tools', None),
    'email_tools': ('.email_tools', None),
    
    # Clarify tool
    'clarify': ('.clarify', None),  # Direct import of clarify instance
    'ClarifyTool': ('.clarify', 'ClarifyTool'),
    'ClarifyHandler': ('.clarify', 'ClarifyHandler'),
    'create_cli_clarify_handler': ('.clarify', 'create_cli_clarify_handler'),
    'create_bot_clarify_handler': ('.clarify', 'create_bot_clarify_handler'),
}

# Tool factory functions - caches classes but creates fresh instances
# This prevents state leakage between concurrent agents while optimizing import performance
_loaded_classes = {}  # Cache the Class, NOT the instance

def _create_tool_instance(class_name: str, module_path: str):
    """Create a new tool instance. Caches the class but returns fresh instances to prevent state sharing."""
    if class_name not in _loaded_classes:
        module = import_module(module_path, __package__)
        _loaded_classes[class_name] = getattr(module, class_name)
    return _loaded_classes[class_name]()  # Fresh instance safe for multi-agent

# Profile exports (lazy loaded)
_PROFILE_EXPORTS = frozenset({
    'ToolProfile', 'AUTONOMY_PROFILE', 'BUILTIN_PROFILES',
    'register_profile', 'get_profile', 'resolve_profiles', 'list_profiles'
})

# Code-tools bridge exports (lazy loaded to keep import-time cost off the
# default path; only resolved when the opt-in code mode is used).
_TOOL_PROXY_EXPORTS = frozenset({'ToolProxy', 'build_tool_namespace'})

def __getattr__(name: str) -> Any:
    """Smart lazy loading of tools and profiles."""
    # Handle code-tools bridge exports
    if name in _TOOL_PROXY_EXPORTS:
        from .tool_proxy import ToolProxy, build_tool_namespace
        return {'ToolProxy': ToolProxy, 'build_tool_namespace': build_tool_namespace}[name]

    # Handle circuit breaker imports first
    if name in _CIRCUIT_BREAKER_EXPORTS:
        from .circuit_breaker import (
            CircuitBreaker, CircuitBreakerProtocol, CircuitBreakerConfig, CircuitBreakerException,
            CircuitBreakerStats, CircuitState, HealthCheckProtocol, CircuitBreakerRegistry,
            get_circuit_breaker, get_all_circuit_breaker_stats, reset_all_circuit_breakers
        )
        # Lazy import integration utilities
        integration_imports = {}
        if name in {'with_circuit_breaker', 'LLMCircuitBreakerIntegration', 'MemoryCircuitBreakerIntegration',
                    'MCPCircuitBreakerIntegration', 'create_resilient_external_call', 'integrate_with_retry_policy'}:
            from .circuit_breaker_integrations import (
                with_circuit_breaker, LLMCircuitBreakerIntegration, MemoryCircuitBreakerIntegration,
                MCPCircuitBreakerIntegration, create_resilient_external_call, integrate_with_retry_policy
            )
            integration_imports.update({
                'with_circuit_breaker': with_circuit_breaker,
                'LLMCircuitBreakerIntegration': LLMCircuitBreakerIntegration,
                'MemoryCircuitBreakerIntegration': MemoryCircuitBreakerIntegration,
                'MCPCircuitBreakerIntegration': MCPCircuitBreakerIntegration,
                'create_resilient_external_call': create_resilient_external_call,
                'integrate_with_retry_policy': integrate_with_retry_policy,
            })
        
        # Lazy import health monitoring
        health_imports = {}
        if name in {'HealthMonitor', 'HealthMetrics', 'ServiceHealthConfig', 'TelemetryProtocol',
                    'get_health_monitor', 'get_circuit_breaker_dashboard_data'}:
            from .health_monitor import (
                HealthMonitor, HealthMetrics, ServiceHealthConfig, TelemetryProtocol,
                get_health_monitor, get_circuit_breaker_dashboard_data
            )
            health_imports.update({
                'HealthMonitor': HealthMonitor,
                'HealthMetrics': HealthMetrics,
                'ServiceHealthConfig': ServiceHealthConfig,
                'TelemetryProtocol': TelemetryProtocol,
                'get_health_monitor': get_health_monitor,
                'get_circuit_breaker_dashboard_data': get_circuit_breaker_dashboard_data,
            })
        
        _circuit_breaker_map = {
            'CircuitBreaker': CircuitBreaker,
            'CircuitBreakerProtocol': CircuitBreakerProtocol,
            'CircuitBreakerConfig': CircuitBreakerConfig,
            'CircuitBreakerException': CircuitBreakerException,
            'CircuitBreakerStats': CircuitBreakerStats,
            'CircuitState': CircuitState,
            'HealthCheckProtocol': HealthCheckProtocol,
            'CircuitBreakerRegistry': CircuitBreakerRegistry,
            'get_circuit_breaker': get_circuit_breaker,
            'get_all_circuit_breaker_stats': get_all_circuit_breaker_stats,
            'reset_all_circuit_breakers': reset_all_circuit_breakers,
            **integration_imports,
            **health_imports,
        }
        return _circuit_breaker_map[name]
    
    # Handle profile imports
    if name in _PROFILE_EXPORTS:
        from .profiles import (
            ToolProfile, AUTONOMY_PROFILE, BUILTIN_PROFILES,
            register_profile, get_profile, resolve_profiles, list_profiles
        )
        _profile_map = {
            'ToolProfile': ToolProfile,
            'AUTONOMY_PROFILE': AUTONOMY_PROFILE,
            'BUILTIN_PROFILES': BUILTIN_PROFILES,
            'register_profile': register_profile,
            'get_profile': get_profile,
            'resolve_profiles': resolve_profiles,
            'list_profiles': list_profiles,
        }
        return _profile_map[name]
    
    # Handle tool mappings
    if name not in TOOL_MAPPINGS:
        raise AttributeError(f"module '{__package__}' has no attribute '{name}'")
    
    module_path, class_name = TOOL_MAPPINGS[name]
    
    # Return class itself (not instance) for TavilyTools, YouTools, ExaTools, Crawl4AITools
    if name in ('TavilyTools', 'YouTools', 'ExaTools', 'Crawl4AITools', 'SessionTools'):
        module = import_module(module_path, __package__)
        return getattr(module, class_name)
    
    # Remove the special case since it's now handled by None class_name
    
    if class_name is None:
        # Direct function import
        module = import_module(module_path, __package__)
        if name in ['file_tools', 'spider_tools', 'python_tools', 'shell_tools', 'cot_tools', 'tavily_tools', 'youdotcom_tools', 'exa_tools', 'crawl4ai_tools', 'skill_tools', 'github_tools', 'jira_tools', 'schedule_tools', 'computer_tools', 'messaging_tools', 'search_tools', 'ast_grep_tools', 'edit_tools', 'todo_tools', 'email_tools']:
            return module  # Returns the callable module
        return getattr(module, name)
    else:
        # Create a fresh tool instance for each agent/session to prevent state leakage
        # This factory pattern ensures multi-agent safety by avoiding shared mutable state
        instance = _create_tool_instance(class_name, module_path)
        method = getattr(instance, name)
        return method

__all__ = list(TOOL_MAPPINGS.keys()) + [
    'Injected', 'AgentState',
    'BaseTool', 'ToolResult', 'ToolValidationError', 'validate_tool',
    'multimodal_content', 'text_part', 'image_part', 'file_part',
    'tool', 'FunctionTool',
    # Deferred/progress tool-execution protocol (Issue #2925)
    'ToolProgress', 'DeferredToolResult', 'defer',
    'ToolTimeoutError', 'ToolCancelledError',
    'get_registry', 'register_tool', 'get_tool', 'add_tool', 'has_tool', 'remove_tool', 
    'list_tools', 'list_available_tools', 'list_tools_with_allowed_filter', 'list_tools_with_hermes_filter', 'ToolRegistry',
    'resolve_tool_name', 'resolve_tool_names', 'ToolResolutionError',
    'ToolProxy', 'build_tool_namespace',
    'Tools',
    # Validation and retry protocols
    'ValidationResult', 'ToolValidatorProtocol', 'AsyncToolValidatorProtocol', 'PassthroughValidator',
    'RetryPolicy', 'FallbackChain', 'ToolExecutionConfig',
    # Circuit breaker functionality
    'CircuitBreaker', 'CircuitBreakerProtocol', 'CircuitBreakerConfig', 'CircuitBreakerException',
    'CircuitBreakerStats', 'CircuitState', 'HealthCheckProtocol', 'CircuitBreakerRegistry',
    'get_circuit_breaker', 'get_all_circuit_breaker_stats', 'reset_all_circuit_breakers',
    # Integration utilities
    'with_circuit_breaker', 'LLMCircuitBreakerIntegration', 'MemoryCircuitBreakerIntegration',
    'MCPCircuitBreakerIntegration', 'create_resilient_external_call', 'integrate_with_retry_policy',
    # Health monitoring
    'HealthMonitor', 'HealthMetrics', 'ServiceHealthConfig', 'TelemetryProtocol',
    'get_health_monitor', 'get_circuit_breaker_dashboard_data',
    # Tool profiles (DRY tool sets for autonomy/interactive modes)
    'ToolProfile', 'AUTONOMY_PROFILE', 'BUILTIN_PROFILES',
    'register_profile', 'get_profile', 'resolve_profiles', 'list_profiles',
]