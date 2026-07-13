"""Direct prompt execution (C8.4)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import yaml
from dotenv import load_dotenv
from rich import print

import praisonai_code.cli.main as _cli_main


def _ensure_availability_flags():
    _cli_main._ensure_availability_flags()


def _get_autogen():
    from praisonai_code.cli.legacy.praison_ai import _get_autogen as _pa_get_autogen
    return _pa_get_autogen()


def _availability_flag(name: str):
    _ensure_availability_flags()
    return getattr(_cli_main, name)

def _rewrite_query(self, query: str, rewrite_tools: str = None, verbose: bool = False) -> str:
    """
    Rewrite query using QueryRewriterAgent.
    
    Args:
        query: The query to rewrite
        rewrite_tools: Tool names (comma-separated) or path to tools.py
        verbose: Enable verbose output
        
    Returns:
        Rewritten query or original if rewriting fails
    """
    try:
        from praisonaiagents import QueryRewriterAgent, RewriteStrategy
        from rich import print
        
        print("[bold cyan]Rewriting query for better results...[/bold cyan]")
        
        # Load rewrite tools if specified
        rewrite_tools_list = []
        if rewrite_tools:
            if os.path.isfile(rewrite_tools):
                # Load from file
                try:
                    from praisonai_code.tool_resolver import ToolResolver
                    funcs = ToolResolver().load_functions_from_module(
                        rewrite_tools,
                        functions_only=True,
                        skip_private=True,
                        module_name="rewrite_tools_module",
                    )
                    if funcs:
                        rewrite_tools_list.extend(funcs.values())
                        print(f"[cyan]Loaded {len(rewrite_tools_list)} tools for query rewriter[/cyan]")
                    else:
                        print(f"[yellow]Warning: No rewrite tools loaded from {rewrite_tools} (module has no public functions, or local tools loading is disabled — set PRAISONAI_ALLOW_LOCAL_TOOLS=true to enable).[/yellow]")
                except Exception as e:
                    print(f"[yellow]Warning: Failed to load rewrite tools: {e}[/yellow]")
            else:
                # Treat as comma-separated tool names
                try:
                    import inspect
                    from praisonai_code.tool_resolver import resolve_tool

                    tool_names = [t.strip() for t in rewrite_tools.split(',') if t.strip()]
                    for tool_name in tool_names:
                        tool = resolve_tool(tool_name)
                        if tool is not None:
                            rewrite_tools_list.append(tool() if inspect.isclass(tool) else tool)
                        else:
                            print(f"[yellow]Warning: Unknown rewrite tool '{tool_name}'[/yellow]")
                    if rewrite_tools_list:
                        print(f"[cyan]Using rewrite tools: {', '.join(tool_names)}[/cyan]")
                except ImportError:
                    print("[yellow]Warning: Could not import tools module[/yellow]")
        
        rewrite_model = (
            getattr(getattr(self, 'args', None), 'llm', None)
            or os.environ.get("MODEL_NAME")
            or os.environ.get("OPENAI_MODEL_NAME")
            or "gpt-4o-mini"
        )
        rewriter = QueryRewriterAgent(
            model=rewrite_model,
            verbose=verbose, 
            tools=rewrite_tools_list if rewrite_tools_list else None
        )
        result = rewriter.rewrite(query, strategy=RewriteStrategy.AUTO)
        rewritten = result.primary_query
        
        print(f"[cyan]Original:[/cyan] {query}")
        print(f"[cyan]Rewritten:[/cyan] {rewritten}")
        
        return rewritten
        
    except ImportError:
        from rich import print
        print("[yellow]Warning: QueryRewriterAgent not available, using original query[/yellow]")
        return query
    except Exception as e:
        from rich import print
        print(f"[yellow]Warning: Query rewrite failed ({e}), using original query[/yellow]")
        return query

def _rewrite_query_if_enabled(self, query: str) -> str:
    """
    Rewrite query using QueryRewriterAgent if --query-rewrite is enabled.
    Returns the rewritten query or original if rewriting is disabled/fails.
    """
    if not hasattr(self, 'args') or not getattr(self.args, 'query_rewrite', False):
        return query
    
    rewrite_tools = getattr(self.args, 'rewrite_tools', None)
    verbose = getattr(self.args, 'verbose', False)
    return self._rewrite_query(query, rewrite_tools, verbose)

def _expand_prompt(self, prompt: str, expand_tools: str = None, verbose: bool = False) -> str:
    """
    Expand prompt using PromptExpanderAgent.
    
    Args:
        prompt: The prompt to expand
        expand_tools: Tool names (comma-separated) or path to tools.py
        verbose: Enable verbose output
        
    Returns:
        Expanded prompt or original if expansion fails
    """
    try:
        from praisonaiagents import PromptExpanderAgent, ExpandStrategy
        from rich import print
        
        print("[bold cyan]Expanding prompt for detailed execution...[/bold cyan]")
        
        # Load expand tools if specified
        expand_tools_list = []
        if expand_tools:
            if os.path.isfile(expand_tools):
                # Load from file
                try:
                    from praisonai_code.tool_resolver import ToolResolver
                    funcs = ToolResolver().load_functions_from_module(
                        expand_tools,
                        functions_only=True,
                        skip_private=True,
                        module_name="expand_tools_module",
                    )
                    if funcs:
                        expand_tools_list.extend(funcs.values())
                        print(f"[cyan]Loaded {len(expand_tools_list)} tools for prompt expander[/cyan]")
                    else:
                        print(f"[yellow]Warning: No expand tools loaded from {expand_tools} (module has no public functions, or local tools loading is disabled — set PRAISONAI_ALLOW_LOCAL_TOOLS=true to enable).[/yellow]")
                except Exception as e:
                    print(f"[yellow]Warning: Failed to load expand tools: {e}[/yellow]")
            else:
                # Treat as comma-separated tool names
                try:
                    import inspect
                    from praisonai_code.tool_resolver import resolve_tool

                    tool_names = [t.strip() for t in expand_tools.split(',') if t.strip()]
                    for tool_name in tool_names:
                        tool = resolve_tool(tool_name)
                        if tool is not None:
                            expand_tools_list.append(tool() if inspect.isclass(tool) else tool)
                        else:
                            print(f"[yellow]Warning: Unknown expand tool '{tool_name}'[/yellow]")
                    if expand_tools_list:
                        print(f"[cyan]Using expand tools: {', '.join(tool_names)}[/cyan]")
                except ImportError:
                    print("[yellow]Warning: Could not import tools module[/yellow]")
        
        expand_model = (
            getattr(getattr(self, 'args', None), 'llm', None)
            or os.environ.get("MODEL_NAME")
            or os.environ.get("OPENAI_MODEL_NAME")
            or "gpt-4o-mini"
        )
        expander = PromptExpanderAgent(
            model=expand_model,
            verbose=verbose, 
            tools=expand_tools_list if expand_tools_list else None
        )
        result = expander.expand(prompt, strategy=ExpandStrategy.AUTO)
        expanded = result.expanded_prompt
        
        print(f"[cyan]Original:[/cyan] {prompt}")
        print(f"[cyan]Expanded:[/cyan] {expanded}")
        
        return expanded
        
    except ImportError:
        from rich import print
        print("[yellow]Warning: PromptExpanderAgent not available, using original prompt[/yellow]")
        return prompt
    except Exception as e:
        from rich import print
        print(f"[yellow]Warning: Prompt expansion failed ({e}), using original prompt[/yellow]")
        return prompt

def _expand_prompt_if_enabled(self, prompt: str) -> str:
    """
    Expand prompt using PromptExpanderAgent if --expand-prompt is enabled.
    Returns the expanded prompt or original if expansion is disabled/fails.
    """
    if not hasattr(self, 'args') or not getattr(self.args, 'expand_prompt', False):
        return prompt
    
    expand_tools = getattr(self.args, 'expand_tools', None)
    verbose = getattr(self.args, 'verbose', False)
    return self._expand_prompt(prompt, expand_tools, verbose)

def _load_tools(self, tools_path: str) -> list:
    """
    Load tools from a file path or comma-separated tool names.
    
    Args:
        tools_path: Path to tools.py file or comma-separated tool names
        
    Returns:
        List of tool functions
    """
    tools_list = []
    if not tools_path:
        return tools_list
        
    if os.path.isfile(tools_path):
        # Load from file
        try:
            from praisonai_code.tool_resolver import ToolResolver
            funcs = ToolResolver().load_functions_from_module(
                tools_path,
                functions_only=True,
                skip_private=True,
            )
            if funcs:
                tools_list.extend(funcs.values())
                print(f"[cyan]Loaded {len(tools_list)} tools from {tools_path}[/cyan]")
            else:
                print(f"[yellow]Warning: No tools loaded from {tools_path} (module has no public functions, or local tools loading is disabled — set PRAISONAI_ALLOW_LOCAL_TOOLS=true to enable).[/yellow]")
        except Exception as e:
            print(f"[yellow]Warning: Failed to load tools from {tools_path}: {e}[/yellow]")
    else:
        # Comma-separated names: use the unified resolver so CLI == YAML == Python
        from praisonai_code.tool_resolver import ToolResolver
        resolver = ToolResolver()
        tool_names = [t.strip() for t in tools_path.split(',') if t.strip()]
        for tool_name in tool_names:
            try:
                tool = resolver.resolve(tool_name, instantiate=True)
                if tool is not None:
                    tools_list.append(tool)
                else:
                    print(f"[yellow]Warning: Unknown tool '{tool_name}'[/yellow]")
            except Exception as e:
                print(f"[yellow]Warning: Failed to load tool '{tool_name}': {e}[/yellow]")
        if tools_list:
            print(f"[cyan]Loaded {len(tools_list)} tools[/cyan]")
    
    return tools_list

def _load_toolsets(self, toolset_names: list) -> list:
    """
    Load tools from named toolset groups.
    
    Args:
        toolset_names: List of toolset names to resolve
        
    Returns:
        List of tool functions from all toolsets
    """
    tools_list = []
    if not toolset_names:
        return tools_list
    
    try:
        from praisonai_code.tool_resolver import resolve_toolsets
        tools_list = resolve_toolsets(toolset_names)
        
        if tools_list:
            print(f"[cyan]Loaded {len(tools_list)} tools from toolsets: {', '.join(toolset_names)}[/cyan]")
        else:
            print(f"[yellow]Warning: No tools found for toolsets: {', '.join(toolset_names)}[/yellow]")
            
    except Exception as e:
        print(f"[yellow]Warning: Failed to load toolsets {toolset_names}: {e}[/yellow]")
    
    return tools_list

def _save_output(self, prompt: str, result: str):
    """
    Save output to output/prompts/ folder.
    
    Args:
        prompt: The original prompt
        result: The output result to save
    """
    from datetime import datetime
    from rich import print
    
    # Create output directory
    output_dir = os.path.join(os.getcwd(), "output", "prompts")
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # Create a safe filename from prompt (first 30 chars)
    safe_prompt = "".join(c if c.isalnum() or c in " -_" else "" for c in prompt[:30]).strip().replace(" ", "_")
    filename = f"{timestamp}_{safe_prompt}.md"
    filepath = os.path.join(output_dir, filename)
    
    # Write output
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# Prompt\n\n{prompt}\n\n")
        f.write(f"# Output\n\n{result}\n")
    
    print(f"[green]✅ Output saved to: {filepath}[/green]")

def _run_direct_prompt_via_adapter(self, prompt):
    """Run a one-shot direct prompt through the FrameworkAdapterRegistry.

    This keeps default framework selection in a single place (the registry's
    priority + entry-point discovery) and routes execution through the adapter
    contract so telemetry suppression, ``_resolve_llm`` normalisation and
    ``expected_output`` handling all apply — none of which the previous
    hardcoded ``from crewai import ...`` / ``from autogen import ...`` chain did.
    """
    from praisonai.framework_adapters.registry import get_default_registry

    registry = get_default_registry()
    try:
        framework = registry.pick_default()
    except RuntimeError as e:
        print(f"[red]ERROR: {e}[/red]")
        sys.exit(1)

    adapter = registry.create(framework)
    # AutoGen exposes a family router that resolves to a concrete version.
    if hasattr(adapter, "resolve"):
        adapter = adapter.resolve(config={})

    llm = getattr(getattr(self, "args", None), "llm", None)
    config_list = getattr(self, "config_list", None) or [{"model": llm or "gpt-4o"}]
    # Preserve the full first config entry so credentials/endpoint fields
    # (base_url, api_key, api_type, ...) that the adapter's _resolve_llm and the
    # AutoGen config_list depend on survive. Only the explicit --llm override
    # replaces the model; a missing model falls back to a sane default.
    llm_config = [dict(config_list[0])]
    if llm:
        llm_config[0]["model"] = llm
    llm_config[0].setdefault("model", "gpt-4o")

    # Canonical one-shot config shape shared with the YAML path; the adapter's
    # spec builder turns this into agents/tasks with a proper expected_output.
    config = {
        "roles": {
            "director": {
                "role": "Assistant",
                "goal": "Complete the given task",
                "backstory": "You are a helpful AI assistant",
                "tasks": {
                    "direct_task": {
                        "description": prompt,
                        "expected_output": "A complete response to the task.",
                    }
                },
                "tools": [],
            }
        }
    }

    return adapter.run(
        config,
        llm_config,
        prompt,
        tools_dict={},
        cli_config=vars(self.args) if hasattr(self, "args") and self.args else None,
    )


def handle_direct_prompt(self, prompt):
    """
    Handle direct prompt by creating a single agent and running it.
    
    Supports @mentions:
    - @file:path/to/file.py - Include file content
    - @web:query - Search the web
    - @doc:name - Include doc from .praison/docs/
    - @rule:name - Include specific rule
    - @url:https://... - Fetch URL content
    """
    # Seed availability flags so bare-name reads resolve when invoked
    # directly (e.g. `praison run` -> handle_direct_prompt) without main().
    _ensure_availability_flags()

    # Check for profiling mode - use unified profiler
    if hasattr(self, 'args') and getattr(self.args, 'profile', False):
        return self._handle_profiled_prompt(prompt)
    
    # Check for inline workflow mode
    if hasattr(self, 'args') and getattr(self.args, 'workflow', None):
        return self._run_inline_workflow(prompt)
    
    # Process @mentions in the prompt
    mention_context = ""
    try:
        from praisonaiagents.tools.mentions import MentionsParser
        parser = MentionsParser(workspace_path=os.getcwd())
        if parser.has_mentions(prompt):
            mention_context, prompt = parser.process(prompt)
            if mention_context:
                print("[bold cyan]Processing @mentions...[/bold cyan]")
    except ImportError:
        pass  # Mentions not available
    except Exception as e:
        logging.debug(f"Error processing mentions: {e}")
    
    # Apply query rewriting if enabled
    prompt = self._rewrite_query_if_enabled(prompt)
    # Apply prompt expansion if enabled
    prompt = self._expand_prompt_if_enabled(prompt)
    
    # Auto-inject project instruction files unless disabled
    rules_context = ""
    try:
        should_load_rules = False
        max_chars = 32000  # Default cap
        include_manual = None
        
        # First check for explicit --no-rules flag
        if hasattr(self, 'args') and getattr(self.args, 'no_rules', False):
            should_load_rules = False
        else:
            # Check for manual include_rules
            include_rules = getattr(self.args, 'include_rules', None) if hasattr(self, 'args') else None
            if include_rules:
                if include_rules == "auto":
                    should_load_rules = True
                else:
                    include_manual = [name.strip() for name in include_rules.split(",") if name.strip()]
                    should_load_rules = bool(include_manual)
            else:
                # Check config for auto rules
                try:
                    from ..configuration.loader import load_config
                    config = load_config()
                    should_load_rules = config.rules.auto
                    max_chars = config.rules.max_chars
                except Exception:
                    pass  # Config not available, use defaults
        
        if should_load_rules:
            from praisonaiagents.memory import RulesManager
            rules_manager = RulesManager(workspace_path=os.getcwd(), verbose=getattr(self.args, 'verbose', 0))
            rules_context = rules_manager.build_rules_context(
                include_manual=include_manual,
                max_chars=max_chars
            )
            if rules_context and getattr(self.args, 'verbose', 0):
                # Show loaded files in verbose mode
                active_rules = rules_manager.get_active_rules()
                loaded_files = []
                for rule in active_rules:
                    if rule.file_path and rule.priority >= 500:  # Root instruction files
                        loaded_files.append(os.path.basename(rule.file_path))
                if loaded_files:
                    print(f"[cyan]Loaded project instructions: {', '.join(loaded_files)}[/cyan]")
    except ImportError:
        pass  # RulesManager not available
    except Exception as e:
        if hasattr(self, 'args') and getattr(self.args, 'verbose', 0):
            logging.debug(f"Error loading rules: {e}")
    
    # Prepend mention context and rules context to prompt
    if mention_context and rules_context:
        prompt = f"{mention_context}{rules_context}\n\n# Task:\n{prompt}"
    elif mention_context:
        prompt = f"{mention_context}# Task:\n{prompt}"
    elif rules_context:
        prompt = f"{rules_context}\n\n# Task:\n{prompt}"
    
    if _availability_flag("PRAISONAI_AVAILABLE"):
        from praisonaiagents import Agent as PraisonAgent
        
        agent_config = {
            "name": "DirectAgent",
            "role": "Assistant",
            "goal": "Complete the given task",
            "backstory": "You are a helpful AI assistant"
        }
        
        # Autonomy Mode - full_auto by default for multi-turn autonomous execution
        # ACP tools disabled by default for speed (~3s vs 174s+); use --acp to enable
        autonomy_mode = getattr(self.args, 'autonomy', None) if hasattr(self, 'args') else None
        if autonomy_mode and autonomy_mode not in ('disable', None):
            agent_config["autonomy"] = {"level": autonomy_mode, "enabled": True}
        
        # Set SDK output preset based on verbosity flags
        # The display dispatcher handles CLI rendering; this controls SDK-level behavior
        v = getattr(self.args, 'verbose', 0) if hasattr(self, 'args') else 0
        if v >= 2:
            agent_config["output"] = "verbose"  # SDK debug-level detail
        elif v >= 1:
            agent_config["output"] = "verbose"
        else:
            agent_config["output"] = "minimal"
        
        # Load default tools (same as interactive mode) unless --no-tools is set
        # CRITICAL: For autonomy mode, disable slow ACP and LSP tools by default
        # ACP tools go through complex orchestration (174s+ delays)
        # LSP tools require starting language server (176s+ delays)
        # Use --acp or --lsp flags to explicitly enable them.
        if not getattr(self.args, 'no_tools', False):
            # Check if autonomy mode is enabled - disable ACP/LSP by default for speed
            is_autonomy = autonomy_mode and autonomy_mode not in ('disable', None)
            use_acp = getattr(self.args, 'acp', False)  # Explicit --acp flag
            use_lsp = getattr(self.args, 'lsp', False)  # Explicit --lsp flag
            
            if is_autonomy:
                if not use_acp:
                    # Force disable ACP for autonomy mode (use basic tools only)
                    # This makes full_auto fast (~3s vs 174s+)
                    self.args.no_acp = True
                    logging.debug("Autonomy mode: ACP tools disabled for speed (use --acp to enable)")
                if not use_lsp:
                    # Force disable LSP for autonomy mode
                    # LSP requires starting language server (176s+ delays)
                    self.args.no_lsp = True
                    logging.debug("Autonomy mode: LSP tools disabled for speed (use --lsp to enable)")
            
            default_tools = self._load_interactive_tools()
            if default_tools:
                agent_config["tools"] = default_tools
        else:
            agent_config["tools"] = []  # Explicitly set empty tools
        
        # Add llm if specified
        if hasattr(self, 'args') and self.args.llm:
            # Build LLM config dict
            llm_config = {"model": self.args.llm}
            
            # Add max_tokens if specified
            max_tokens = getattr(self.args, 'max_tokens', 16000)
            if max_tokens:
                llm_config["max_tokens"] = max_tokens
                logging.debug(f"Max tokens set to: {max_tokens}")
            
            # Add tool reliability settings (for weak models like Ollama)
            if getattr(self.args, 'max_tool_repairs', None) is not None:
                llm_config["max_tool_repairs"] = self.args.max_tool_repairs
            if getattr(self.args, 'force_tool_usage', None) is not None:
                llm_config["force_tool_usage"] = self.args.force_tool_usage
            
            agent_config["llm"] = llm_config
        
        # Add feature flags if enabled
        if hasattr(self, 'args'):
            if getattr(self.args, 'web_search', False) or getattr(self.args, 'web_fetch', False):
                from praisonaiagents.config.web_config import WebConfig
                agent_config["web"] = WebConfig(
                    search=getattr(self.args, 'web_search', False),
                    fetch=getattr(self.args, 'web_fetch', False),
                )
            if getattr(self.args, 'prompt_caching', False):
                from praisonaiagents import CachingConfig
                agent_config["caching"] = CachingConfig(prompt_caching=True)
            
            # Load tools if specified (--tools flag)
            if getattr(self.args, 'tools', None):
                tools_list = self._load_tools(self.args.tools)
                if tools_list:
                    existing_tools = agent_config.get('tools', [])
                    if isinstance(existing_tools, list):
                        existing_tools.extend(tools_list)
                        agent_config["tools"] = existing_tools
                    else:
                        agent_config["tools"] = tools_list

            # Auto-discover project-local .praisonai/tools/*.py (additive; mirrors
            # the agents/commands convention). Explicit --tools above take
            # precedence; discovery is gated by PRAISONAI_ALLOW_LOCAL_TOOLS and
            # skipped when --no-tools is set.
            if not getattr(self.args, 'no_tools', False):
                try:
                    from praisonai_code.cli.features.custom_definitions import (
                        discover_project_tools,
                    )
                    project_tools = discover_project_tools()
                except Exception:
                    project_tools = []
                if project_tools:
                    existing_tools = agent_config.get('tools', [])
                    if not isinstance(existing_tools, list):
                        existing_tools = [existing_tools] if existing_tools else []
                    seen = {id(t) for t in existing_tools}
                    existing_tools.extend(
                        t for t in project_tools if id(t) not in seen
                    )
                    agent_config["tools"] = existing_tools

            # Load toolsets if specified (--toolset flag)
            if getattr(self.args, 'toolset', None):
                toolset_names = [name.strip() for name in self.args.toolset.split(',') if name.strip()]
                toolset_tools = self._load_toolsets(toolset_names) if toolset_names else []
                if toolset_tools:
                    existing_tools = agent_config.get('tools', [])
                    if isinstance(existing_tools, list):
                        existing_tools.extend(toolset_tools)
                        agent_config["tools"] = existing_tools
                    else:
                        agent_config["tools"] = toolset_tools
                    print(f"[bold cyan]Toolsets loaded: {len(toolset_tools)} tool(s) from {self.args.toolset}[/bold cyan]")
            
            # Planning Mode
            if getattr(self.args, 'planning', False):
                from praisonaiagents import PlanningConfig
                planning_kwargs = {}
                print("[bold cyan]Planning mode enabled - agent will create a plan before execution[/bold cyan]")
                
                # Load planning tools if specified
                if getattr(self.args, 'planning_tools', None):
                    planning_tools_list = self._load_tools(self.args.planning_tools)
                    if planning_tools_list:
                        planning_kwargs["tools"] = planning_tools_list
                # If no planning_tools but --tools is specified, use those for planning too
                elif getattr(self.args, 'tools', None) and agent_config.get('tools'):
                    planning_kwargs["tools"] = agent_config['tools']
                    print("[cyan]Using --tools for planning as well[/cyan]")
                
                if getattr(self.args, 'planning_reasoning', False):
                    planning_kwargs["reasoning"] = True
                
                agent_config["planning"] = PlanningConfig(**planning_kwargs) if planning_kwargs else True
            
            # P8/G11: Tool timeout and retry policy via ToolConfig
            # Agent expects tool execution settings through tool_config=ToolConfig(...),
            # not the deprecated top-level tool_timeout / tool_retry_policy kwargs.
            tool_config_kwargs = {}

            # Tool timeout - prevent slow tools from blocking
            tool_timeout = getattr(self.args, 'tool_timeout', 60)
            if tool_timeout and tool_timeout > 0:
                tool_config_kwargs["timeout"] = int(tool_timeout)

            # Tool retry policy - handle transient failures with exponential backoff
            retry_attempts = getattr(self.args, 'tool_retry_attempts', 3)
            retry_delay = getattr(self.args, 'tool_retry_delay', 1000)
            retry_backoff = getattr(self.args, 'tool_retry_backoff', 2.0)
            retry_on_str = getattr(self.args, 'tool_retry_on', "timeout,rate_limit,connection_error")
            retry_on = set(error_type.strip() for error_type in retry_on_str.split(',') if error_type.strip())

            if retry_attempts > 1:  # Only create retry policy if retries are enabled
                from praisonaiagents.tools.retry import RetryPolicy
                tool_config_kwargs["retry_policy"] = RetryPolicy(
                    max_attempts=retry_attempts,
                    initial_delay_ms=retry_delay,
                    backoff_factor=retry_backoff,
                    retry_on=retry_on
                )

            if tool_config_kwargs:
                from praisonaiagents.config.feature_configs import ToolConfig
                agent_config["tool_config"] = ToolConfig(**tool_config_kwargs)
            
            # Memory
            if getattr(self.args, 'memory', False):
                memory_kwargs = {}
                if getattr(self.args, 'user_id', None):
                    memory_kwargs["user_id"] = self.args.user_id
                if getattr(self.args, 'auto_save', None):
                    memory_kwargs["auto_save"] = self.args.auto_save
                    print(f"[bold cyan]Auto-save enabled - session will be saved as '{self.args.auto_save}'[/bold cyan]")
                if memory_kwargs:
                    from praisonaiagents import MemoryConfig
                    agent_config["memory"] = MemoryConfig(**memory_kwargs)
                else:
                    agent_config["memory"] = True
                print("[bold cyan]Memory enabled - agent will remember context across sessions[/bold cyan]")
            elif getattr(self.args, 'cli_project_sessions', False) and (
                getattr(self.args, 'resume_session', None) or getattr(self.args, 'auto_save', None)
            ):
                from ..state.project_sessions import build_cli_memory_config
                agent_config["memory"] = build_cli_memory_config(
                    getattr(self.args, 'resume_session', None),
                    getattr(self.args, 'auto_save', None),
                )
                session_label = agent_config['memory'].auto_save or agent_config['memory'].session_id
                print(f"[bold cyan]Project session enabled - session '{session_label}'[/bold cyan]")
            elif getattr(self.args, 'auto_save', None):
                from praisonaiagents import MemoryConfig
                agent_config["memory"] = MemoryConfig(auto_save=self.args.auto_save)
                print(f"[bold cyan]Auto-save enabled - session will be saved as '{self.args.auto_save}'[/bold cyan]")
            
            if getattr(self.args, 'history', None):
                if agent_config.get("memory") is None:
                    agent_config["memory"] = True  # History requires memory
                # Note: history_in_context param removed - history loading now via context= param
                print(f"[bold cyan]History enabled - loading context from last {self.args.history} session(s)[/bold cyan]")

            # CLI session continuity from `praison run --continue/--session`
            # Only apply for resume sessions, not plain --auto-save
            _resume_id = getattr(self.args, 'resume_session', None)
            if _resume_id:
                _auto_save_id = getattr(self.args, 'auto_save', None)
                from ..utils.project import build_cli_memory_config
                _session_cfg = build_cli_memory_config(
                    session_id=_resume_id,
                    auto_save=_auto_save_id,
                )
                if _session_cfg:
                    agent_config["memory"] = _session_cfg
                    print(
                        f"[bold cyan]Session continuity enabled - "
                        f"session '{_session_cfg.session_id}'[/bold cyan]"
                    )
            
            # Claude Memory Tool (Anthropic only)
            if getattr(self.args, 'claude_memory', False):
                llm = getattr(self.args, 'llm', '')
                if llm and 'anthropic' in llm.lower():
                    from praisonaiagents import MemoryConfig
                    existing_memory = agent_config.get("memory")
                    if isinstance(existing_memory, MemoryConfig):
                        existing_memory.claude_memory = True
                    else:
                        agent_config["memory"] = MemoryConfig(claude_memory=True)
                    print("[bold cyan]Claude Memory Tool enabled - Claude will autonomously manage memories[/bold cyan]")
                else:
                    print("[yellow]Warning: --claude-memory requires an Anthropic model (--llm anthropic/...)[/yellow]")
            
            # Message Steering
            if getattr(self.args, 'message_steering', False):
                agent_config["message_steering"] = True
                print("[bold cyan]Message steering enabled - agent can receive guidance during execution[/bold cyan]")
            
            # ===== NEW CLI FEATURES INTEGRATION =====
            
            # Tool Approval - Auto-approve tools based on --trust or --approve-level
            if getattr(self.args, 'trust', False) or getattr(self.args, 'approve_level', None):
                from praisonaiagents.approval import set_approval_callback, ApprovalDecision
                
                if getattr(self.args, 'trust', False):
                    # Auto-approve all tools
                    def auto_approve_all(function_name, arguments, risk_level):
                        return ApprovalDecision(approved=True, reason="Auto-approved via --trust flag")
                    set_approval_callback(auto_approve_all)
                    print("[bold yellow]⚠️  Trust mode enabled - all tool executions will be auto-approved[/bold yellow]")
                elif getattr(self.args, 'approve_level', None):
                    # Auto-approve up to specified risk level
                    max_level = self.args.approve_level
                    risk_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
                    max_level_value = risk_order.get(max_level, 3)
                    
                    def level_based_approve(function_name, arguments, risk_level):
                        tool_level_value = risk_order.get(risk_level, 4)
                        if tool_level_value <= max_level_value:
                            return ApprovalDecision(approved=True, reason=f"Auto-approved (level {risk_level} <= {max_level})")
                        else:
                            # Signal to pause Live display before showing approval prompt
                            # This is handled by the approval_pending flag in status_info
                            from praisonaiagents.approval import console_approval_callback
                            return console_approval_callback(function_name, arguments, risk_level)
                    
                    set_approval_callback(level_based_approve)
                    print(f"[bold cyan]Auto-approve enabled for tools up to '{max_level}' risk level[/bold cyan]")
            
            # Approval Backend - Set agent-level approval via --approval flag
            approval_flag = getattr(self.args, 'approval', None)
            if approval_flag:
                from ..features._approval_bridge import resolve_approval_config
                try:
                    approval_val = resolve_approval_config(
                        approval_flag,
                        all_tools=getattr(self.args, 'approve_all_tools', False),
                        timeout=getattr(self.args, 'approval_timeout', None),
                    )
                    if approval_val is not None:
                        agent_config["approval"] = approval_val
                        print(f"[bold cyan]Approval backend: {approval_flag}[/bold cyan]")
                except ValueError as e:
                    print(f"[red]ERROR: {e}[/red]")
                    sys.exit(1)
            
            # Router - Smart model selection (must be before agent creation)
            if getattr(self.args, 'router', False):
                from ..features.router import RouterHandler
                router = RouterHandler(verbose=getattr(self.args, 'verbose', False))
                provider = getattr(self.args, 'router_provider', None)
                selected_model = router.select_model(prompt, provider)
                agent_config["llm"] = selected_model
            
            # Metrics - Token/cost tracking (display happens AFTER execution)
            if getattr(self.args, 'metrics', False):
                from praisonaiagents import OutputConfig
                agent_config["output"] = OutputConfig(metrics=True)
            
            # Telemetry - Usage monitoring
            if getattr(self.args, 'telemetry', False):
                from ..features.telemetry import TelemetryHandler
                telemetry = TelemetryHandler(verbose=getattr(self.args, 'verbose', False))
                telemetry.enable()
            
            # Sandbox - Secure command execution (display only, actual sandboxing is in tool approval)
            sandbox_mode = getattr(self.args, 'sandbox', None)
            if sandbox_mode and sandbox_mode != 'off':
                print(f"[bold green]🔒 Sandbox Mode: {sandbox_mode.upper()}[/bold green]")
                print("[dim]Commands will be validated before execution[/dim]")
            
            # Auto Memory - Automatic memory extraction (handled post-processing, not as Agent param)
            if getattr(self.args, 'auto_memory', False):
                print("[bold cyan]Auto Memory enabled - will extract and store memories[/bold cyan]")
            
            # MCP - Model Context Protocol tools.
            # Wire BOTH the ad-hoc single --mcp command string AND every
            # enabled server from project config (local stdio *and*
            # remote/URL), so multi-server and remote MCP setups are all
            # available — not just the first stdio server.
            mcp_command = getattr(self.args, 'mcp', None)
            mcp_servers = getattr(self.args, 'mcp_servers', None) or []
            if mcp_command or mcp_servers:
                # Single source of truth for MCP tool aggregation, shared
                # with the actions-mode run path (commands/run.py).
                from ..commands.run import _build_mcp_tools
                aggregated_mcp_tools = _build_mcp_tools(
                    mcp_command,
                    getattr(self.args, 'mcp_env', None),
                    mcp_servers,
                    verbose=getattr(self.args, 'verbose', False),
                )
                if aggregated_mcp_tools:
                    existing_tools = agent_config.get('tools', [])
                    if isinstance(existing_tools, list):
                        existing_tools.extend(aggregated_mcp_tools)
                    else:
                        existing_tools = aggregated_mcp_tools
                    agent_config['tools'] = existing_tools
            
            # External Agent - Use external AI CLI tools with manager delegation
            if getattr(self.args, 'external_agent', None):
                from rich.console import Console
                ext_console = Console()
                external_agent_name = self.args.external_agent
                direct = getattr(self.args, 'external_agent_direct', False)
                
                try:
                    from ..features.external_agents import ExternalAgentsHandler
                    handler = ExternalAgentsHandler(verbose=getattr(self.args, 'verbose', False))
                    
                    # Get workspace from current directory (os is imported at module level)
                    workspace = os.getcwd()
                    
                    integration = handler.get_integration(external_agent_name, workspace=workspace)
                    
                    if not integration.is_available:
                        ext_console.print(f"[yellow]⚠️ External agent '{external_agent_name}' is not installed[/yellow]")
                        ext_console.print(f"[dim]Install with: {handler._get_install_instructions(external_agent_name)}[/dim]")
                        return None
                    
                    if direct:
                        # Pass-through proxy (original behavior, preserved as escape hatch)
                        ext_console.print(f"[bold cyan]🔌 Using external agent (direct): {external_agent_name}[/bold cyan]")
                        import asyncio
                        try:
                            result = asyncio.run(integration.execute(prompt))
                            ext_console.print(f"\n[bold green]Result from {external_agent_name}:[/bold green]")
                            ext_console.print(result)
                            return ""
                        except Exception as e:
                            ext_console.print(f"[red]Error executing {external_agent_name}: {e.__class__.__name__}: {e}[/red]")
                            return None
                    
                    # NEW default: manager Agent uses external CLI as subagent tool
                    ext_console.print(f"[bold cyan]🔌 Using external agent via manager delegation: {external_agent_name}[/bold cyan]")
                    try:
                        from praisonaiagents import Agent
                        manager = Agent(
                            name="Manager",
                            instructions=(
                                f"You are a manager that delegates tasks to the {external_agent_name} subagent "
                                f"via the {integration.cli_command}_tool. Call the tool for coding/analysis tasks."
                            ),
                            tools=[integration.as_tool()],
                            llm=agent_config.get('llm') or os.environ.get("MODEL_NAME", "gpt-4o-mini"),
                        )
                        result = manager.start(prompt)
                        ext_console.print(f"\n[bold green]Manager delegation result:[/bold green]")
                        ext_console.print(result)
                        return ""
                    except Exception as e:
                        ext_console.print(f"[red]Error with manager delegation: {e.__class__.__name__}: {e}[/red]")
                        return None
                except Exception as e:
                    ext_console.print(f"[red]Error setting up external agent: {e}[/red]")
                    return None
            
            # Fast Context - Codebase search
            if getattr(self.args, 'fast_context', None):
                from ..features.fast_context import FastContextHandler
                fc_handler = FastContextHandler(verbose=getattr(self.args, 'verbose', False))
                context = fc_handler.execute(query=prompt, path=self.args.fast_context)
                if context:
                    prompt = f"{context}\n\n## Task\n{prompt}"
                    print("[bold cyan]Fast Context enabled - added relevant code context[/bold cyan]")
            
            # Handoff - Agent delegation (creates multiple agents)
            if getattr(self.args, 'handoff', None):
                from ..features.handoff import HandoffHandler
                handoff_handler = HandoffHandler(verbose=getattr(self.args, 'verbose', False))
                
                # Parse handoff config options
                detect_cycles = None
                if getattr(self.args, 'handoff_detect_cycles', None):
                    detect_cycles = self.args.handoff_detect_cycles.lower() == 'true'
                
                agents = handoff_handler.create_agents_with_handoff(
                    handoff_handler.parse_agent_names(self.args.handoff),
                    llm=agent_config.get('llm'),
                    context_policy=getattr(self.args, 'handoff_policy', None),
                    timeout_seconds=getattr(self.args, 'handoff_timeout', None),
                    max_concurrent=getattr(self.args, 'handoff_max_concurrent', None),
                    max_depth=getattr(self.args, 'handoff_max_depth', None),
                    detect_cycles=detect_cycles,
                )
                if agents:
                    # Use first agent with handoff chain
                    result = agents[0].start(prompt)
                    
                    # Post-process with guardrail if enabled
                    if getattr(self.args, 'guardrail', None):
                        from ..features.guardrail import GuardrailHandler
                        guardrail = GuardrailHandler(verbose=getattr(self.args, 'verbose', False))
                        guardrail.post_process_result(result, self.args.guardrail)
                    
                    # Save output if --save is enabled
                    if getattr(self.args, 'save', False):
                        self._save_output(prompt, result)
                    
                    return result
        
        # Image Description (Vision) - analyze existing images
        if hasattr(self, 'args') and getattr(self.args, 'image', None):
            from ..features.image import ImageHandler
            image_handler = ImageHandler(verbose=getattr(self.args, 'verbose', False))
            result = image_handler.execute(
                prompt=prompt,
                image_path=self.args.image,
                llm=agent_config.get('llm')
            )
            
            # Post-process with guardrail if enabled
            if getattr(self.args, 'guardrail', None):
                from ..features.guardrail import GuardrailHandler
                guardrail = GuardrailHandler(verbose=getattr(self.args, 'verbose', False))
                guardrail.post_process_result(result, self.args.guardrail)
            
            # Save output if --save is enabled
            if getattr(self.args, 'save', False):
                self._save_output(prompt, result)
            
            return result
        
        # Image Generation - create new images from text
        if hasattr(self, 'args') and getattr(self.args, 'image_generate', False):
            from ..features.image import ImageGenerateHandler
            image_gen_handler = ImageGenerateHandler(verbose=getattr(self.args, 'verbose', False))
            result = image_gen_handler.execute(
                prompt=prompt,
                llm=agent_config.get('llm')
            )
            
            # Format output for display
            if isinstance(result, dict):
                if 'error' in result:
                    print(f"[red]Error: {result['error']}[/red]")
                elif 'data' in result and len(result['data']) > 0:
                    image_url = result['data'][0].get('url', result['data'][0].get('b64_json', 'Generated'))
                    print(f"[green]Image generated successfully![/green]")
                    if 'url' in result['data'][0]:
                        print(f"URL: {result['data'][0]['url']}")
            
            return result
        
        # CLI Backend - delegate agent turns to external CLI tools
        if hasattr(self, 'args') and getattr(self.args, 'cli_backend', None):
            try:
                from praisonai_code.cli_backends import resolve_cli_backend
                agent_config["cli_backend"] = resolve_cli_backend(self.args.cli_backend)
            except Exception as e:
                logging.warning(f"Failed to resolve CLI backend '{self.args.cli_backend}': {e}")
        
        # Flow Display - Visual workflow tracking
        if hasattr(self, 'args') and getattr(self.args, 'flow_display', False):
            from ..features.flow_display import FlowDisplayHandler
            flow = FlowDisplayHandler(verbose=getattr(self.args, 'verbose', False))
            flow.display_workflow_start("Direct Prompt", ["DirectAgent"])
        
        agent = PraisonAgent(**agent_config)

        # Reasoning effort (mapped from --thinking on `run`/`code`) → core
        # extended-thinking budget, applied via the property setter. Default
        # is unchanged when the flag is omitted.
        if hasattr(self, 'args'):
            _thinking_budget = getattr(self.args, 'thinking_budget', None)
            if _thinking_budget is not None:
                agent.thinking_budget = _thinking_budget

        if hasattr(self, 'args') and getattr(self.args, 'cli_project_sessions', False):
            session_id = getattr(self.args, 'resume_session', None) or getattr(self.args, 'auto_save', None)
            auto_save = getattr(self.args, 'auto_save', None)
            if session_id:
                from ..state.project_sessions import apply_cli_session_continuity
                apply_cli_session_continuity(agent, session_id, auto_save=auto_save)
        
        # AutoRag - Automatic RAG retrieval decision
        if hasattr(self, 'args') and getattr(self.args, 'auto_rag', False):
            from praisonaiagents import AutoRagAgent
            
            auto_rag_config = {
                "retrieval_policy": getattr(self.args, 'rag_policy', 'auto'),
                "top_k": getattr(self.args, 'rag_top_k', 5),
                "hybrid": getattr(self.args, 'rag_hybrid', False),
                "rerank": getattr(self.args, 'rag_rerank', False),
            }
            
            auto_rag = AutoRagAgent(agent=agent, **auto_rag_config)
            print(f"[bold cyan]AutoRag enabled - policy: {auto_rag_config['retrieval_policy']}[/bold cyan]")
            
            # Run with AutoRag wrapper
            is_verbose = agent_config.get("verbose", False)
            if not is_verbose:
                from rich.live import Live
                from rich.spinner import Spinner
                from rich.panel import Panel
                
                with Live(Panel(Spinner("dots", text="Generating..."), border_style="cyan"), refresh_per_second=10, transient=True):
                    result = self._execute_agent_with_budget_handling(auto_rag, 'chat', prompt)
            else:
                result = self._execute_agent_with_budget_handling(auto_rag, 'chat', prompt)
        else:
            # Resolve display mode from CLI flags
            display_mode = self._resolve_display_mode()
            
            if display_mode == 'silent':
                # -qq: No output at all, exit code only
                if hasattr(agent, 'start'):
                    result = self._execute_agent_with_budget_handling(agent, 'start', prompt)
                else:
                    result = self._execute_agent_with_budget_handling(agent, 'chat', prompt)
            
            elif display_mode == 'quiet':
                # -q: Result only, no spinners or status
                if hasattr(agent, 'start'):
                    result = self._execute_agent_with_budget_handling(agent, 'start', prompt)
                else:
                    result = self._execute_agent_with_budget_handling(agent, 'chat', prompt)
                if result is not None:
                    output = getattr(result, 'output', None) or (str(result) if result else None)
                    if output:
                        print(output)
            
            elif display_mode == 'verbose':
                # -v: SDK StatusOutput with timestamps and metrics
                try:
                    from praisonaiagents.output.status import enable_status_output, disable_status_output
                    enable_status_output(show_timestamps=True, show_metrics=True)
                    if hasattr(agent, 'start'):
                        result = self._execute_agent_with_budget_handling(agent, 'start', prompt)
                    else:
                        result = self._execute_agent_with_budget_handling(agent, 'chat', prompt)
                    disable_status_output()
                except ImportError:
                    if hasattr(agent, 'start'):
                        result = self._execute_agent_with_budget_handling(agent, 'start', prompt)
                    else:
                        result = self._execute_agent_with_budget_handling(agent, 'chat', prompt)
            
            elif display_mode == 'debug':
                # -vv: SDK TraceOutput with markdown rendering
                try:
                    from praisonaiagents.output.trace import enable_trace_output, disable_trace_output
                    enable_trace_output(use_markdown=True)
                    if hasattr(agent, 'start'):
                        result = self._execute_agent_with_budget_handling(agent, 'start', prompt)
                    else:
                        result = self._execute_agent_with_budget_handling(agent, 'chat', prompt)
                    disable_trace_output()
                except ImportError:
                    if hasattr(agent, 'start'):
                        result = self._execute_agent_with_budget_handling(agent, 'start', prompt)
                    else:
                        result = self._execute_agent_with_budget_handling(agent, 'chat', prompt)
            
            elif display_mode == 'jsonl':
                # --output jsonl: JSONL structured output for CI/CD
                from ..features.display_jsonl import JsonlDisplay
                from praisonaiagents.main import register_display_callback as _reg_cb
                
                jsonl = JsonlDisplay()
                jsonl.on_init(model=agent_config.get('llm'))
                _reg_cb('tool_call', jsonl.on_tool_call)
                _reg_cb('llm_start', jsonl.on_llm_start)
                _reg_cb('autonomy_iteration', jsonl.on_autonomy_iteration)
                _reg_cb('autonomy_stage_change', jsonl.on_autonomy_stage_change)
                _reg_cb('autonomy_doom_loop', jsonl.on_autonomy_doom_loop)
                _reg_cb('autonomy_complete', lambda **kw: jsonl.on_complete(
                    reason=kw.get('completion_reason'),
                    iterations=kw.get('iterations'),
                    duration_ms=(kw.get('duration_seconds') or 0) * 1000,
                ))
                
                start_time = time.time()
                if hasattr(agent, 'start'):
                    result = self._execute_agent_with_budget_handling(agent, 'start', prompt)
                else:
                    result = self._execute_agent_with_budget_handling(agent, 'chat', prompt)
                
                # Emit final result
                reason = getattr(result, 'completion_reason', None) if hasattr(result, 'completion_reason') else 'complete'
                iters = getattr(result, 'iterations', None) if hasattr(result, 'iterations') else None
                jsonl.on_complete(reason=reason or 'complete', iterations=iters,
                                 duration_ms=(time.time() - start_time) * 1000)
                
                # Print result to stdout
                if hasattr(result, 'output') and result.output:
                    print(result.output)
                elif isinstance(result, str):
                    print(result)
            
            elif display_mode == 'json':
                # --output json: JSON envelope output
                import json as json_mod
                start_time = time.time()
                if hasattr(agent, 'start'):
                    result = self._execute_agent_with_budget_handling(agent, 'start', prompt)
                else:
                    result = self._execute_agent_with_budget_handling(agent, 'chat', prompt)
                
                output = result.output if hasattr(result, 'output') else str(result)
                envelope = {
                    'result': output,
                    'model': agent_config.get('llm'),
                    'duration_ms': round((time.time() - start_time) * 1000),
                }
                if hasattr(result, 'completion_reason'):
                    envelope['completion_reason'] = result.completion_reason
                if hasattr(result, 'iterations'):
                    envelope['iterations'] = result.iterations
                print(json_mod.dumps(envelope, indent=2))
            
            elif display_mode == 'flow':
                # --flow: SDK FlowDisplay - visual agent→tool chart
                try:
                    from praisonaiagents.flow_display import track_workflow
                    flow = track_workflow()
                    flow.start()
                    if hasattr(agent, 'start'):
                        result = self._execute_agent_with_budget_handling(agent, 'start', prompt)
                    else:
                        result = self._execute_agent_with_budget_handling(agent, 'chat', prompt)
                    flow.stop()
                except ImportError:
                    if hasattr(agent, 'start'):
                        result = self._execute_agent_with_budget_handling(agent, 'start', prompt)
                    else:
                        result = self._execute_agent_with_budget_handling(agent, 'chat', prompt)
            
            elif display_mode == 'editor':
                # --output editor: User-friendly step-by-step format
                # Uses SDK EditorOutput (Step 1: 📄 Creating file → ✓ Done)
                from praisonaiagents.output.editor import enable_editor_output, disable_editor_output
                editor = enable_editor_output(use_color=True)
                
                # Run agent
                if hasattr(agent, 'start'):
                    result = self._execute_agent_with_budget_handling(agent, 'start', prompt)
                else:
                    result = self._execute_agent_with_budget_handling(agent, 'chat', prompt)
                
                # SDK callbacks (interaction, llm_content) handle display —
                # no explicit editor.output() needed here.
                output = result.output if hasattr(result, 'output') else str(result)
                
                # Show summary
                elapsed = editor.elapsed_time()
                editor.summary("Completed", [
                    f"Duration: {elapsed:.1f}s",
                    f"Blocks: {len(editor.get_blocks())}",
                ])
                
                disable_editor_output()
            
            else:
                # Default: SDK status output — clean inline progress
                # Shows: spinner + tool calls, no panels, no timestamps
                try:
                    from praisonaiagents.output.status import enable_status_output, disable_status_output
                    enable_status_output(show_timestamps=False, show_metrics=False)
                    if hasattr(agent, 'start'):
                        result = self._execute_agent_with_budget_handling(agent, 'start', prompt)
                    else:
                        result = self._execute_agent_with_budget_handling(agent, 'chat', prompt)
                    disable_status_output()
                except ImportError:
                    if hasattr(agent, 'start'):
                        result = self._execute_agent_with_budget_handling(agent, 'start', prompt)
                    else:
                        result = self._execute_agent_with_budget_handling(agent, 'chat', prompt)
        
        # ===== POST-PROCESSING WITH NEW FEATURES =====
        
        # Guardrail - Output validation
        if hasattr(self, 'args') and getattr(self.args, 'guardrail', None):
            from ..features.guardrail import GuardrailHandler
            guardrail = GuardrailHandler(verbose=getattr(self.args, 'verbose', False))
            guardrail.post_process_result(result, self.args.guardrail)
        
        # Metrics - Display token usage
        if hasattr(self, 'args') and getattr(self.args, 'metrics', False):
            from ..features.metrics import MetricsHandler
            metrics = MetricsHandler(verbose=getattr(self.args, 'verbose', False))
            agent_metrics = metrics.extract_metrics_from_agent(agent)
            if agent_metrics:
                print(metrics.format_metrics(agent_metrics))
        
        # Auto Memory - Extract and store memories
        if hasattr(self, 'args') and getattr(self.args, 'auto_memory', False):
            from ..features.auto_memory import AutoMemoryHandler
            auto_mem = AutoMemoryHandler(verbose=getattr(self.args, 'verbose', False))
            auto_mem.post_process_result(
                result, 
                {'user_id': getattr(self.args, 'user_id', None), 'user_message': prompt}
            )
        
        # Todo - Generate todo list from response
        if hasattr(self, 'args') and getattr(self.args, 'todo', False):
            from ..features.todo import TodoHandler
            todo = TodoHandler(verbose=getattr(self.args, 'verbose', False))
            todo.post_process_result(result, True)
        
        # Telemetry - Display usage summary after execution
        if hasattr(self, 'args') and getattr(self.args, 'telemetry', False):
            from ..features.telemetry import TelemetryHandler
            telemetry = TelemetryHandler(verbose=getattr(self.args, 'verbose', False))
            telemetry.post_process_result(result, True)
        
        # Flow Display - End workflow
        if hasattr(self, 'args') and getattr(self.args, 'flow_display', False):
            from ..features.flow_display import FlowDisplayHandler
            flow = FlowDisplayHandler(verbose=getattr(self.args, 'verbose', False))
            flow.display_workflow_end(success=True)
        
        # Final Agent - Process output with a specialized agent
        if hasattr(self, 'args') and getattr(self.args, 'final_agent', None):
            final_instruction = self.args.final_agent
            print(f"\n[bold blue]📝 FINAL AGENT PROCESSING[/bold blue]")
            print(f"[dim]Instruction: {final_instruction}[/dim]\n")
            
            # Create a final agent with the same LLM config
            final_agent_config = {
                "name": "FinalAgent",
                "role": final_instruction,
                "goal": f"Process the provided content and {final_instruction.lower()}",
                "backstory": f"You are an expert at {final_instruction.lower()}. You take research content and transform it into polished, detailed output."
            }
            
            # Use same LLM config
            if agent_config.get("llm"):
                final_agent_config["llm"] = agent_config["llm"]
            
            final_prompt = f"""Based on the following research content, {final_instruction.lower()}.

## Research Content:

{result}

## Instructions:
- Be comprehensive and detailed
- Include all relevant information from the research
- Structure the output professionally
- Do not omit any important details

Now, {final_instruction.lower()}:"""
            
            final_agent = PraisonAgent(**final_agent_config)
            result = final_agent.start(final_prompt)
            print(f"\n[bold green]✅ Final agent processing complete[/bold green]\n")
        
        # Save output if --save is enabled
        if hasattr(self, 'args') and getattr(self.args, 'save', False):
            self._save_output(prompt, result)
        
        # Metrics JSON - Output structured cost data
        if hasattr(self, 'args') and getattr(self.args, 'metrics_json', False):
            try:
                from ..features.metrics import MetricsHandler
                _mh = MetricsHandler(verbose=getattr(self.args, 'verbose', False))
                # Extract from final_agent if it was used, otherwise from original agent
                active_agent = final_agent if 'final_agent' in locals() else agent
                agent_metrics = _mh.extract_metrics_from_agent(active_agent)
                # Resolve model name: prefer what the agent reported, fall back to config
                model_name = agent_metrics.get('model')
                if not model_name:
                    model_name = agent_config.get('llm', 'unknown')
                    if isinstance(model_name, dict):
                        model_name = model_name.get('model', 'unknown')
                metrics_out = {
                    "cost_usd": agent_metrics.get('cost', 0.0),
                    "tokens_in": agent_metrics.get('prompt_tokens', 0),
                    "tokens_out": agent_metrics.get('completion_tokens', 0),
                    "model": model_name or 'unknown',
                    "request_count": agent_metrics.get('llm_calls', 0),
                }
                print(json.dumps(metrics_out))
            except Exception as exc:
                print(f"[metrics-json] warning: could not extract metrics: {exc}", file=sys.stderr)
                # CRITICAL: Always emit JSON when --metrics-json is set
                print(json.dumps({"cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0, "model": "unknown", "request_count": 0}))
        
        return result
    elif _availability_flag("CREWAI_AVAILABLE") or _availability_flag("AUTOGEN_AVAILABLE"):
        # Route non-praisonai frameworks through the FrameworkAdapterRegistry so
        # the single source of truth for selection (priority + entry-point
        # plugins) and the full adapter contract (scoped_telemetry_disable,
        # _resolve_llm, expected_output, cli_config/callbacks) apply here too —
        # instead of a hardcoded chain that bypassed every adapter.
        return _run_direct_prompt_via_adapter(self, prompt)
    else:
        print("[red]ERROR: No framework is installed. Please install at least one framework:[/red]")
        print("\npip install \"praisonai-frameworks\\[crewai]\"  # For CrewAI")
        print("pip install \"praisonai-frameworks\\[autogen]\"  # For AutoGen")
        print("pip install \"praisonai-frameworks\\[crewai,autogen]\"  # Multiple frameworks\n")
        print("pip install praisonaiagents # For Agents\n")  
        sys.exit(1)
