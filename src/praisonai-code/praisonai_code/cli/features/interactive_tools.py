"""
Interactive Default Tools Provider for PraisonAI.

This module provides the canonical source of truth for default tools
in interactive modes (TUI and `praison "prompt"`).

Tool Groups:
- `acp`: ACP-powered file operations (create, edit, delete, execute)
- `edit`: Targeted/fuzzy atomic edits (edit_file, apply_patch) from core
- `lsp`: LSP-powered code intelligence (symbols, definitions, references)
- `search`: Fast codebase search (ripgrep-backed grep/glob, structural ast_grep)
- `basic`: Basic file tools (read, list, search)
- `clarify`: Human-in-the-loop clarify tool (gated on an interactive TTY)
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
import sys
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
    "search": [
        "grep",
        "glob",
        "ast_grep_search",
    ],
    "basic": [
        "read_file",
        "write_file",
        "list_files",
        "execute_command",
        "internet_search",
        "web_crawl",
    ],
    "clarify": [
        "clarify",
    ],
}

# Default interactive group includes all
TOOL_GROUPS["interactive"] = (
    TOOL_GROUPS["acp"] + 
    TOOL_GROUPS["edit"] + 
    TOOL_GROUPS["lsp"] + 
    TOOL_GROUPS["search"] + 
    TOOL_GROUPS["basic"] +
    TOOL_GROUPS["clarify"]
)


@dataclass
class ToolConfig:
    """Configuration for tool loading."""
    workspace: str = field(default_factory=os.getcwd)
    enable_acp: bool = True
    enable_edit: bool = True
    enable_lsp: bool = True
    enable_search: bool = True
    enable_basic: bool = True
    enable_clarify: bool = True
    approval_mode: str = "auto"  # auto (full privileges), manual, scoped
    lsp_enabled: bool = True
    acp_enabled: bool = True

    def __post_init__(self) -> None:
        # Honour PRAISON_TOOLS_DISABLE for *every* ToolConfig, not just the
        # ``from_env`` path. Callers that construct ToolConfig directly (e.g.
        # ``InteractiveConfig.to_tool_config`` and ``HeadlessInteractiveCore``)
        # would otherwise silently keep a group enabled despite the advertised
        # opt-out. This only turns groups *off* — an explicit ``enable_*=True``
        # passed by a caller is still overridden by the operator's env opt-out,
        # matching the "disable" semantics of the flag.
        self._apply_env_disable()

    def _apply_env_disable(self) -> None:
        """Disable tool groups listed in ``PRAISON_TOOLS_DISABLE`` (in place)."""
        disable_str = os.environ.get("PRAISON_TOOLS_DISABLE", "")
        if not disable_str:
            return
        disabled = {g.strip().lower() for g in disable_str.split(",")}
        if "acp" in disabled:
            self.enable_acp = False
        if "edit" in disabled:
            self.enable_edit = False
        if "lsp" in disabled:
            self.enable_lsp = False
        if "search" in disabled:
            self.enable_search = False
        if "basic" in disabled:
            self.enable_basic = False
        if "clarify" in disabled:
            self.enable_clarify = False

    @classmethod
    def from_env(cls) -> "ToolConfig":
        """Create config from environment variables."""
        config = cls()  # __post_init__ already applied PRAISON_TOOLS_DISABLE

        # Check for workspace. The `praisonai code --workspace` flag writes
        # PRAISONAI_WORKSPACE (code.py), so honour that canonical name first and
        # fall back to the older PRAISON_WORKSPACE for backward compatibility.
        workspace = os.environ.get("PRAISONAI_WORKSPACE") or os.environ.get(
            "PRAISON_WORKSPACE", ""
        )
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
        if config.enable_search:
            tool_names.update(TOOL_GROUPS["search"])
        if config.enable_basic:
            tool_names.update(TOOL_GROUPS["basic"])
        if config.enable_clarify:
            tool_names.update(TOOL_GROUPS["clarify"])
    
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


def _interactive_channel_available() -> bool:
    """Whether a live interactive channel exists for asking the user.

    The ``clarify`` tool is only useful when the agent can actually pause and
    read an answer from the operator. We treat a channel as available when both
    stdin and stdout are TTYs and the run has not been explicitly marked as
    headless/machine-output. In non-interactive/headless/CI runs the tool is
    withheld so the core ``ClarifyHandler`` best-judgment fallback keeps
    scripted runs from blocking on an unanswerable prompt.

    Operators can force the tool off with ``PRAISON_NO_CLARIFY`` (mirroring a
    ``--no-clarify`` override) or the shared ``PRAISON_TOOLS_DISABLE=clarify``.
    """
    no_clarify = os.environ.get("PRAISON_NO_CLARIFY", "").strip().lower()
    if no_clarify in ("1", "true", "yes"):
        return False

    # CI runners can allocate pseudo-terminals, so both streams may report as
    # TTYs while no human is present to answer. Treat any truthy ``CI`` signal
    # as headless and withhold the tool, so an unattended run falls back to the
    # core best-judgment path instead of blocking on ``input()``.
    ci = os.environ.get("CI", "").strip().lower()
    if ci not in ("", "0", "false", "no"):
        return False

    # A structured/JSON output mode is a machine consumer; never prompt.
    output_mode = os.environ.get("PRAISON_OUTPUT_MODE", "").strip().lower()
    if output_mode in ("json", "stream-json", "actions"):
        return False

    try:
        return bool(sys.stdin and sys.stdin.isatty()
                    and sys.stdout and sys.stdout.isatty())
    except (ValueError, AttributeError, OSError):
        return False


def _load_clarify_tools(config: ToolConfig) -> Dict[str, Callable]:
    """Lazy-load the human-in-the-loop ``clarify`` tool for interactive runs.

    Wires the existing core ``ClarifyTool`` + ``create_cli_clarify_handler``
    (stdin prompt) into the default interactive toolset so a terminal agent can
    pause and ask one focused question instead of silently guessing on genuine
    ambiguity.

    Gated on an interactive channel (:func:`_interactive_channel_available`):
    in headless/non-TTY/JSON/CI runs the tool is withheld entirely, preserving
    the core best-judgment fallback so scripted runs never block.
    """
    tools: Dict[str, Callable] = {}

    if not _interactive_channel_available():
        logger.debug("clarify tool withheld: no interactive channel")
        return tools

    try:
        from praisonaiagents.tools.clarify import (
            ClarifyTool,
            create_cli_clarify_handler,
        )
    except ImportError as e:
        logger.debug(f"clarify tool not available: {e}")
        return tools

    clarify_tool = ClarifyTool(handler=create_cli_clarify_handler())

    async def clarify(question: str, choices: Optional[List[str]] = None) -> str:
        """Ask the user a focused clarifying question when genuinely ambiguous.

        Use sparingly — only when you cannot proceed without the user's input.
        Pauses the turn and reads the answer from the terminal.

        Args:
            question: The single, focused question to ask.
            choices: Optional list of predefined answer choices (rendered as a
                numbered menu; the user may also type free text).

        Returns:
            The user's answer.
        """
        return await clarify_tool.run(question=question, choices=choices)

    tools["clarify"] = clarify
    logger.debug("Loaded clarify tool (interactive channel available)")

    return tools


def _load_search_tools(config: ToolConfig) -> Dict[str, Callable]:
    """Lazy load fast codebase-search tools from praisonaiagents.

    Wires the existing core search builtins into the default interactive
    toolset so the coding agent no longer has to shell out to a raw
    ``grep -rn``: ripgrep-backed ``grep`` and ``glob`` (gitignore-aware,
    result-capped, truncation-safe) and structural ``ast_grep_search``.

    The core ``grep``/``glob`` contain paths to ``os.getcwd()`` and
    ``ast_grep_search`` performs no containment at all. In headless
    ``code -p --workspace <dir>`` mode the process is not chdir'd into the
    selected workspace, so a model-supplied ``path`` (relative *or* absolute)
    could read outside it. Fail closed by binding every search tool's ``path``
    to the configured workspace before delegating — mirroring the containment
    the edit/ACP/LSP groups already enforce. If containment is unavailable we
    do not expose the search tools rather than expose an unbounded reader.

    The wrapper resolves the caller path against the workspace root and then
    delegates with the process cwd temporarily pinned to that root, so the
    core tool's own ``os.getcwd()``-based containment agrees with ours instead
    of rejecting a legitimate absolute in-workspace path.
    """
    tools: Dict[str, Callable] = {}

    try:
        import contextlib
        from pathlib import Path

        from praisonaiagents.tools.path_safety import resolve_within_root
    except ImportError as e:
        logger.warning(
            f"Search tools disabled: path containment unavailable: {e}"
        )
        return tools

    root = str(Path(config.workspace).resolve())

    def _contained(path: Optional[str]) -> Optional[str]:
        """Resolve *path* under the workspace root, or ``None`` if it escapes."""
        return resolve_within_root(path or ".", root)

    @contextlib.contextmanager
    def _in_workspace():
        """Pin the process cwd to the workspace root for the delegated call.

        The core search builtins hard-bind containment/relative resolution to
        ``os.getcwd()``. Restored in a ``finally`` so it never leaks. Best
        effort: if the chdir fails we still return the (already contained)
        absolute path to the core tool.
        """
        prev = None
        try:
            prev = os.getcwd()
        except OSError:
            prev = None
        try:
            os.chdir(root)
        except OSError:
            pass
        try:
            yield
        finally:
            if prev is not None:
                try:
                    os.chdir(prev)
                except OSError:
                    pass

    try:
        from praisonaiagents.tools import grep as _grep

        def grep(pattern: str, path: str = ".", glob: Optional[str] = None,
                 case_insensitive: bool = False, max_results: int = 100) -> str:
            """Search file contents for a regex/literal pattern in the workspace.

            Args:
                pattern: Regex/literal to search for.
                path: Directory/file under the workspace to search.
                glob: Optional filename glob (e.g. ``"*.py"``).
                case_insensitive: Case-insensitive matching when True.
                max_results: Hard cap on the number of matching lines returned.

            Returns:
                ``path:line: match`` entries, or an error string.
            """
            safe = _contained(path)
            if safe is None:
                return f"Error: path {path!r} escapes the workspace."
            with _in_workspace():
                return _grep(pattern, safe, glob, case_insensitive, max_results)

        tools["grep"] = grep
    except ImportError:
        logger.debug("grep not available")

    try:
        from praisonaiagents.tools import glob as _glob

        def glob(pattern: str, path: str = ".", max_results: int = 100) -> str:
            """Return files matching a glob pattern under the workspace.

            Args:
                pattern: Glob pattern (e.g. ``"**/*.py"``).
                path: Directory under the workspace to search.
                max_results: Hard cap on the number of paths returned.

            Returns:
                Newline-joined relative file paths, or an error string.
            """
            safe = _contained(path)
            if safe is None:
                return f"Error: path {path!r} escapes the workspace."
            with _in_workspace():
                return _glob(pattern, safe, max_results)

        tools["glob"] = glob
    except ImportError:
        logger.debug("glob not available")

    try:
        from praisonaiagents.tools import ast_grep_search as _ast_grep_search

        def ast_grep_search(pattern: str, lang: str, path: str = ".",
                            json_output: bool = True) -> str:
            """Structural (AST) code search under the workspace.

            Args:
                pattern: AST pattern (e.g. ``"def $FN($$$)"``).
                lang: Programming language (python, javascript, ...).
                path: Directory/file under the workspace to search.
                json_output: Return JSON when True.

            Returns:
                Search results, or an error string.
            """
            safe = _contained(path)
            if safe is None:
                return f"Error: path {path!r} escapes the workspace."
            return _ast_grep_search(pattern, lang, safe, json_output)

        tools["ast_grep_search"] = ast_grep_search
    except ImportError:
        logger.debug("ast_grep_search not available")

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

    # Fail closed on workspace containment: the fallback path inside the core
    # engine (workspace=None) only rejects ``..`` traversal and still accepts
    # absolute paths (e.g. ``/etc/hosts``). Combined with auto-approval that
    # would let an edit escape the configured workspace, so if containment is
    # unavailable we simply do not expose the edit tools.
    try:
        from pathlib import Path
        from praisonaiagents.workspace import Workspace  # type: ignore
        workspace = Workspace(root=Path(config.workspace))
    except Exception as e:
        logger.warning(
            f"Edit tools disabled: workspace containment unavailable: {e}"
        )
        return tools

    engine = EditTools(workspace=workspace)

    # The core edit engine marks edit_file/apply_patch as high-risk and routes
    # them through the approval registry. In the interactive "auto" approval
    # mode the agent runs with full privileges (matching the ACP tools), so
    # register these as context-approved to avoid a blocking console prompt.
    # Manual/scoped modes leave the normal approval flow (with diff preview)
    # in place.
    #
    # Merge into the existing YAML-approved set rather than replacing it:
    # ``set_yaml_approved_tools`` overwrites the whole context-local set, which
    # would clobber previously approved workflow tools. ``add_yaml_approved_tools``
    # unions ``edit_file``/``apply_patch`` into the current context set so no
    # existing approval is dropped. Approvals are context-local (a contextvar),
    # so they do not leak across independent agent/task contexts.
    if config.approval_mode == "auto":
        try:
            from praisonaiagents.approval import add_yaml_approved_tools
            add_yaml_approved_tools(["edit_file", "apply_patch"])
        except ImportError:
            # Older core without the non-clobbering merge helper: fall back but
            # preserve every tool already approved in this context (not just the
            # interactive-group ones) by reading the current set directly from
            # the registry's context-local store before merging.
            try:
                from praisonaiagents.approval import (
                    get_approval_registry,
                    set_yaml_approved_tools,
                )
                registry = get_approval_registry()
                try:
                    current = set(registry._yaml_approved_tools.get())
                except (LookupError, AttributeError):
                    current = set()
                merged = current | {"edit_file", "apply_patch"}
                set_yaml_approved_tools(sorted(merged))
            except Exception as e:
                logger.debug(f"Could not auto-approve edit tools: {e}")
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
    
    # Load the human-in-the-loop clarify tool (gated on an interactive channel;
    # withheld in headless/non-TTY/JSON runs so scripted runs never block).
    if config.enable_clarify and not (disable and "clarify" in disable):
        clarify_tools = _load_clarify_tools(config)
        all_tools.update(clarify_tools)
    
    # Load fast search tools (always available, no runtime needed)
    if config.enable_search and not (disable and "search" in disable):
        search_tools = _load_search_tools(config)
        all_tools.update(search_tools)
    
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
    search_names = set(TOOL_GROUPS["search"])
    search_count = sum(1 for t in tools if t.__name__ in search_names)
    basic_count = len(tools) - acp_count - lsp_count - edit_count - search_count
    
    print(f"Interactive tools loaded: {len(tools)} total")
    print(f"  - ACP tools: {acp_count}")
    print(f"  - Edit tools: {edit_count}")
    print(f"  - LSP tools: {lsp_count}")
    print(f"  - Search tools: {search_count}")
    print(f"  - Basic tools: {basic_count}")
