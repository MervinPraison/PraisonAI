"""
Interactive Default Tools Provider for PraisonAI.

This module provides the canonical source of truth for default tools
in interactive modes (TUI and `praison "prompt"`).

Tool Groups:
- `acp`: ACP-powered file operations (create, edit, delete, execute)
- `edit`: Targeted/fuzzy atomic edits (edit_file, apply_patch) from core
- `lsp`: LSP-powered code intelligence (symbols, definitions, references)
- `basic`: Basic file tools (read, list, search)
- `interactive`: Union of all groups (default)

Usage:
    from praisonai_code.cli.features.interactive_tools import (
        get_interactive_tools,
        resolve_tool_groups,
        TOOL_GROUPS,
    )
    
    # Get all interactive tools (default)
    tools = get_interactive_tools()
    
    # Get specific groups
    tools = get_interactive_tools(groups=["acp", "basic"])
    
    # Disable specific groups
    tools = get_interactive_tools(disable=["lsp"])
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Tool group definitions
TOOL_GROUPS = {
    "acp": [
        "acp_create_file",
        "acp_edit_file", 
        "acp_delete_file",
        "acp_execute_command",
    ],
    "edit": [
        "edit_file",
        "apply_patch",
    ],
    "lsp": [
        "lsp_list_symbols",
        "lsp_find_definition",
        "lsp_find_references",
        "lsp_get_diagnostics",
    ],
    "basic": [
        "read_file",
        "write_file",
        "list_files",
        "execute_command",
        "internet_search",
        "web_crawl",
    ],
}

# Default interactive group includes all
TOOL_GROUPS["interactive"] = (
    TOOL_GROUPS["acp"] + 
    TOOL_GROUPS["edit"] + 
    TOOL_GROUPS["lsp"] + 
    TOOL_GROUPS["basic"]
)


@dataclass
class ToolConfig:
    """Configuration for tool loading."""
    workspace: str = field(default_factory=os.getcwd)
    enable_acp: bool = True
    enable_edit: bool = True
    enable_lsp: bool = True
    enable_basic: bool = True
    approval_mode: str = "auto"  # auto (full privileges), manual, scoped
    lsp_enabled: bool = True
    acp_enabled: bool = True
    
    @classmethod
    def from_env(cls) -> "ToolConfig":
        """Create config from environment variables."""
        config = cls()
        
        # Check env vars for disabling groups
        disable_str = os.environ.get("PRAISON_TOOLS_DISABLE", "")
        if disable_str:
            disabled = [g.strip().lower() for g in disable_str.split(",")]
            if "acp" in disabled:
                config.enable_acp = False
            if "edit" in disabled:
                config.enable_edit = False
            if "lsp" in disabled:
                config.enable_lsp = False
            if "basic" in disabled:
                config.enable_basic = False
        
        # Check for workspace
        workspace = os.environ.get("PRAISON_WORKSPACE", "")
        if workspace:
            config.workspace = workspace
        
        # Check approval mode
        approval = os.environ.get("PRAISON_APPROVAL_MODE", "")
        if approval in ("auto", "manual", "scoped"):
            config.approval_mode = approval
        
        return config


def resolve_tool_groups(
    groups: Optional[List[str]] = None,
    disable: Optional[List[str]] = None,
    config: Optional[ToolConfig] = None,
) -> Set[str]:
    """
    Resolve which tool names should be included based on groups and config.
    
    Args:
        groups: Specific groups to include (None = all enabled)
        disable: Groups to explicitly disable
        config: Tool configuration
        
    Returns:
        Set of tool names to include
    """
    if config is None:
        config = ToolConfig.from_env()
    
    disable = disable or []
    
    # Start with requested groups or all enabled
    if groups:
        tool_names = set()
        for group in groups:
            if group in TOOL_GROUPS:
                tool_names.update(TOOL_GROUPS[group])
    else:
        tool_names = set()
        if config.enable_acp:
            tool_names.update(TOOL_GROUPS["acp"])
        if config.enable_edit:
            tool_names.update(TOOL_GROUPS["edit"])
        if config.enable_lsp:
            tool_names.update(TOOL_GROUPS["lsp"])
        if config.enable_basic:
            tool_names.update(TOOL_GROUPS["basic"])
    
    # Remove disabled groups
    for group in disable:
        if group in TOOL_GROUPS:
            tool_names -= set(TOOL_GROUPS[group])
    
    return tool_names


def _load_basic_tools() -> Dict[str, Callable]:
    """Lazy load basic tools from praisonaiagents."""
    tools = {}
    
    try:
        from praisonaiagents.tools import read_file
        tools["read_file"] = read_file
    except ImportError:
        logger.debug("read_file not available")
    
    try:
        from praisonaiagents.tools import write_file
        tools["write_file"] = write_file
    except ImportError:
        logger.debug("write_file not available")
    
    try:
        from praisonaiagents.tools import list_files
        tools["list_files"] = list_files
    except ImportError:
        logger.debug("list_files not available")
    
    try:
        from praisonaiagents.tools import execute_command
        tools["execute_command"] = execute_command
    except ImportError:
        logger.debug("execute_command not available")
    
    try:
        from praisonaiagents.tools import internet_search
        tools["internet_search"] = internet_search
    except ImportError:
        logger.debug("internet_search not available")
    
    try:
        from praisonaiagents.tools import web_crawl
        tools["web_crawl"] = web_crawl
    except ImportError:
        logger.debug("web_crawl not available")
    
    return tools


def _load_edit_tools(config: ToolConfig) -> Dict[str, Callable]:
    """Lazy load the targeted/fuzzy edit engine from praisonaiagents.

    Wires the existing core ``edit_file`` (5-strategy fuzzy match ladder,
    SHA-256 staleness guard via ``expected_hash``, BOM/CRLF preservation,
    post-edit LSP/linter diagnostics) and ``apply_patch`` (atomic multi-file
    Add/Update/Delete with rollback) into the default interactive toolset,
    replacing whole-file rewrites as the primary edit path.

    The tools are bound to the workspace so relative paths resolve inside it,
    matching the containment used by the ACP/basic file tools.
    """
    tools: Dict[str, Callable] = {}

    try:
        from praisonaiagents.tools.edit_tools import EditTools
    except ImportError as e:
        logger.debug(f"Edit tools not available: {e}")
        return tools

    try:
        from pathlib import Path
        from praisonaiagents.workspace import Workspace  # type: ignore
        workspace = Workspace(root=Path(config.workspace))
    except Exception as e:
        logger.debug(f"Edit tools workspace containment unavailable: {e}")
        workspace = None

    engine = EditTools(workspace=workspace)

    # The core edit engine marks edit_file/apply_patch as high-risk and routes
    # them through the approval registry. In the interactive "auto" approval
    # mode the agent runs with full privileges (matching the ACP tools), so
    # register these as context-approved to avoid a blocking console prompt.
    # Manual/scoped modes leave the normal approval flow (with diff preview)
    # in place.
    if config.approval_mode == "auto":
        try:
            from praisonaiagents.approval import set_yaml_approved_tools
            set_yaml_approved_tools(["edit_file", "apply_patch"])
        except Exception as e:
            logger.debug(f"Could not auto-approve edit tools: {e}")

    def edit_file(filepath: str, old_string: str, new_string: str,
                  replace_all: bool = False, expected_hash: Optional[str] = None,
                  force: bool = False) -> str:
        """Edit a file with a targeted, fuzzy, atomic find-and-replace.

        Prefer this over whole-file rewrites: emit only the ``old_string`` you
        want replaced and its ``new_string``. Uses a 5-strategy fuzzy match
        ladder and preserves line endings/BOM. If the file changed since you
        read it, pass ``expected_hash`` (from a prior read) for an
        optimistic-concurrency staleness guard — on mismatch, read the file
        again before editing rather than overwriting.

        Args:
            filepath: Path to the file to edit (relative to workspace).
            old_string: Exact text to find and replace.
            new_string: Replacement text.
            replace_all: Replace all occurrences (default: first only).
            expected_hash: Optional SHA256 of expected content (staleness guard).
            force: Bypass the staleness guard for an intentional blind write.

        Returns:
            Success message with unified diff (and any diagnostics), or an
            error describing the mismatch/ambiguity to self-correct.
        """
        return engine.edit_file(filepath, old_string, new_string,
                                replace_all, expected_hash, force)

    def apply_patch(patch: str, force: bool = False) -> str:
        """Apply a structured multi-file patch atomically (Add/Update/Delete).

        Use for coordinated edits across multiple files. Staged temp-file
        writes with full rollback on any failure.

        Args:
            patch: Structured patch text with ``*** Add File:``,
                ``*** Update File:`` and ``*** Delete File:`` sections.
            force: Bypass the staleness guard on Update operations.

        Returns:
            Combined success message with diffs, or an error description.
        """
        return engine.apply_patch(patch, force)

    tools["edit_file"] = edit_file
    tools["apply_patch"] = apply_patch

    logger.debug(f"Loaded {len(tools)} edit tools")

    return tools


# ── Context-local runtime for multi-agent safety ──────────────────────────
# Each agent/task/request gets its own runtime context to avoid config conflicts and race conditions.
import contextvars

_runtime_var: contextvars.ContextVar = contextvars.ContextVar("interactive_runtime", default=None)


def _get_shared_runtime(config: ToolConfig):
    """Get or create a context-local InteractiveRuntime instance.
    
    Each context (agent/task/request) gets its own runtime with the config provided.
    This prevents race conditions and config capture issues from global singletons.
    
    First-caller-wins policy: Once a runtime is created for a context with specific
    config, subsequent calls in the same context will return the cached runtime and
    ignore any different config parameters.
    
    Returns (runtime, all_tools) — the runtime and the full list of
    agent-centric tool functions created from it.
    """
    bundle = _runtime_var.get()
    if bundle is not None:
        # Return cached runtime (first-caller-wins for this context)
        return bundle
        
    # Create new runtime for this context
    from .interactive_runtime import InteractiveRuntime, RuntimeConfig
    from .agent_tools import create_agent_centric_tools
    
    runtime_config = RuntimeConfig(
        workspace=config.workspace,
        lsp_enabled=config.lsp_enabled,
        acp_enabled=config.acp_enabled,
        approval_mode=config.approval_mode,
    )
    
    runtime = InteractiveRuntime(runtime_config)
    agent_tools = create_agent_centric_tools(runtime)
    bundle = (runtime, agent_tools)
    _runtime_var.set(bundle)
    logger.debug("Created context-local InteractiveRuntime")
    
    return bundle


def cleanup_runtime():
    """Stop the context-local InteractiveRuntime (LSP server, ACP session).
    
    Call this when the agent finishes to release resources.
    Safe to call multiple times or when no runtime exists in this context.
    """
    bundle = _runtime_var.get()
    if bundle is None:
        return
        
    runtime, _ = bundle
    
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(asyncio.run, runtime.stop()).result(timeout=5)
        else:
            loop.run_until_complete(runtime.stop())
    except Exception as e:
        logger.debug(f"Runtime cleanup: {e}")
    
    _runtime_var.set(None)
    logger.debug("Context-local InteractiveRuntime stopped")


def _load_acp_tools(config: ToolConfig) -> Dict[str, Callable]:
    """Lazy load ACP tools via the shared runtime."""
    tools = {}
    
    try:
        _, all_tools = _get_shared_runtime(config)
        
        for tool in all_tools:
            name = tool.__name__
            if name.startswith("acp_"):
                tools[name] = tool
        
        logger.debug(f"Loaded {len(tools)} ACP tools")
        
    except ImportError as e:
        logger.debug(f"ACP tools not available: {e}")
    except Exception as e:
        logger.warning(f"Error loading ACP tools: {e}")
    
    return tools


def _load_lsp_tools(config: ToolConfig) -> Dict[str, Callable]:
    """Lazy load LSP tools via the shared runtime."""
    tools = {}
    
    try:
        _, all_tools = _get_shared_runtime(config)
        
        for tool in all_tools:
            name = tool.__name__
            if name.startswith("lsp_"):
                tools[name] = tool
        
        logger.debug(f"Loaded {len(tools)} LSP tools")
        
    except ImportError as e:
        logger.debug(f"LSP tools not available: {e}")
    except Exception as e:
        logger.warning(f"Error loading LSP tools: {e}")
    
    return tools


def get_interactive_tools(
    groups: Optional[List[str]] = None,
    disable: Optional[List[str]] = None,
    config: Optional[ToolConfig] = None,
    workspace: Optional[str] = None,
) -> List[Callable]:
    """
    Get the default interactive tools for TUI and prompt modes.
    
    This is the canonical source of truth for interactive tool defaults.
    Both `praisonai tui launch` and `praison "prompt"` should use this.
    
    Args:
        groups: Specific tool groups to include (default: all enabled)
        disable: Tool groups to disable (e.g., ["acp", "lsp"])
        config: Tool configuration (created from env if not provided)
        workspace: Override workspace path
        
    Returns:
        List of tool callables
        
    Example:
        # Default (all tools)
        tools = get_interactive_tools()
        
        # Disable ACP tools
        tools = get_interactive_tools(disable=["acp"])
        
        # Only basic tools
        tools = get_interactive_tools(groups=["basic"])
    """
    if config is None:
        config = ToolConfig.from_env()
    
    if workspace:
        config.workspace = workspace
    
    # Resolve which tools to include
    tool_names = resolve_tool_groups(groups, disable, config)
    
    # Load tools by group
    all_tools: Dict[str, Callable] = {}
    
    # Load basic tools (always available, no runtime needed)
    if config.enable_basic and not (disable and "basic" in disable):
        basic_tools = _load_basic_tools()
        all_tools.update(basic_tools)
    
    # Load targeted/fuzzy edit tools (no runtime needed)
    if config.enable_edit and not (disable and "edit" in disable):
        edit_tools = _load_edit_tools(config)
        all_tools.update(edit_tools)
    
    # Load ACP tools (requires runtime)
    if config.enable_acp and not (disable and "acp" in disable):
        acp_tools = _load_acp_tools(config)
        all_tools.update(acp_tools)
    
    # Load LSP tools (requires runtime)
    if config.enable_lsp and not (disable and "lsp" in disable):
        lsp_tools = _load_lsp_tools(config)
        all_tools.update(lsp_tools)
    
    # Filter to requested tools
    result = []
    for name in sorted(tool_names):  # Deterministic ordering
        if name in all_tools:
            result.append(all_tools[name])
    
    logger.debug(f"Loaded {len(result)} interactive tools: {[t.__name__ for t in result]}")
    
    return result


def merge_tool_overrides(
    default_tools: List[Callable],
    add_tools: Optional[List[Callable]] = None,
    remove_names: Optional[List[str]] = None,
) -> List[Callable]:
    """
    Merge tool overrides with default tools.
    
    Args:
        default_tools: Base list of tools
        add_tools: Tools to add
        remove_names: Tool names to remove
        
    Returns:
        Merged tool list
    """
    # Build name -> tool map
    tool_map = {t.__name__: t for t in default_tools}
    
    # Remove specified tools
    if remove_names:
        for name in remove_names:
            tool_map.pop(name, None)
    
    # Add new tools
    if add_tools:
        for tool in add_tools:
            tool_map[tool.__name__] = tool
    
    return list(tool_map.values())


def get_tool_group_names() -> Dict[str, List[str]]:
    """Get available tool groups and their tool names."""
    return TOOL_GROUPS.copy()


def print_tool_summary(tools: List[Callable]) -> None:
    """Print a summary of loaded tools (for debugging)."""
    acp_count = sum(1 for t in tools if t.__name__.startswith("acp_"))
    lsp_count = sum(1 for t in tools if t.__name__.startswith("lsp_"))
    edit_names = set(TOOL_GROUPS["edit"])
    edit_count = sum(1 for t in tools if t.__name__ in edit_names)
    basic_count = len(tools) - acp_count - lsp_count - edit_count
    
    print(f"Interactive tools loaded: {len(tools)} total")
    print(f"  - ACP tools: {acp_count}")
    print(f"  - Edit tools: {edit_count}")
    print(f"  - LSP tools: {lsp_count}")
    print(f"  - Basic tools: {basic_count}")
