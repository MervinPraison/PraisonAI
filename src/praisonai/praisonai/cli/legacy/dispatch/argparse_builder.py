"""ArgumentParser schema for legacy CLI (C8.4)."""

from __future__ import annotations

import argparse
import os
import sys

from praisonai.cli.legacy.framework_run import fw_registry_module as _fw_registry_module


def build_argument_parser(in_test_env: bool):
    """Build ArgumentParser and parse argv. Returns (args, unknown_args, special_commands)."""
    special_commands = ['chat', 'code', 'call', 'realtime', 'train', 'ui', 'context', 'research', 'memory', 'rules', 'workflow', 'hooks', 'knowledge', 'session', 'tools', 'todo', 'docs', 'mcp', 'commit', 'serve', 'schedule', 'skills', 'profile', 'eval', 'agents', 'run', 'thinking', 'compaction', 'output', 'deploy', 'templates', 'recipe', 'endpoints', 'audio', 'embed', 'embedding', 'images', 'moderate', 'files', 'batches', 'vector-stores', 'rerank', 'ocr', 'assistants', 'fine-tuning', 'completions', 'messages', 'guardrails', 'rag', 'videos', 'a2a', 'containers', 'passthrough', 'responses', 'search', 'realtime-api', 'doctor', 'registry', 'package', 'install', 'uninstall', 'acp', 'debug', 'lsp', 'diag', 'browser', 'replay', 'bot', 'gateway', 'sandbox', 'wizard', 'migrate', 'security', 'persistence', 'paths', 'claw', 'github', 'managed', 'flow', 'dashboard', 'backends', 'audit']

    parser = argparse.ArgumentParser(prog="praisonai", description="praisonAI command-line interface")
    try:
        list_framework_choices = _fw_registry_module().list_framework_choices
        _framework_choices = list_framework_choices(include_unavailable=True) or [
            "ag2", "autogen", "crewai", "praisonai",
        ]
    except ImportError:
        # Only fall back to the static list when the adapter layer itself
        # cannot be imported; genuine registry discovery errors should surface.
        _framework_choices = ["ag2", "autogen", "crewai", "praisonai"]
    parser.add_argument(
        "--framework",
        choices=_framework_choices,
        help="Specify the agent framework (discovered from installed adapters)",
    )
    parser.add_argument("--ui", choices=["chainlit", "gradio"], help="Specify the UI framework (gradio or chainlit).")
    parser.add_argument("--auto", nargs=argparse.REMAINDER, help="Enable auto mode and pass arguments for it")
    parser.add_argument("--init", nargs=argparse.REMAINDER, help="Initialize agents with optional topic")
    parser.add_argument("command", nargs="?", help="Agent YAML file, subcommand, or a direct natural-language prompt to run as a one-shot task")
    parser.add_argument("--deploy", action="store_true", help="Deploy the application")
    parser.add_argument("--schedule", type=str, help="Schedule deployment (e.g., 'daily', 'hourly', '*/6h', '3600')")
    parser.add_argument("--schedule-config", type=str, help="Path to scheduling configuration file")
    parser.add_argument("--provider", type=str, default="gcp", help="Deployment provider (gcp, aws, azure)")
    parser.add_argument("--max-retries", type=int, default=3, help="Maximum retry attempts for scheduled deployments")
    parser.add_argument("--model", type=str, help="Model name")
    parser.add_argument("--llm", type=str, help="LLM model to use for direct prompts")
    parser.add_argument("--hf", type=str, help="Hugging Face model name")
    parser.add_argument("--ollama", type=str, help="Ollama model name")
    parser.add_argument("--dataset", type=str, help="Dataset name for training", default="yahma/alpaca-cleaned")
    parser.add_argument("--realtime", action="store_true", help="Start the realtime voice interaction interface")
    parser.add_argument("--call", action="store_true", help="Start the PraisonAI Call server")
    parser.add_argument("--public", action="store_true", help="Use ngrok to expose the server publicly (only with --call)")
    parser.add_argument("--merge", action="store_true", help="Merge existing agents.yaml with auto-generated agents instead of overwriting")
    parser.add_argument("--claudecode", action="store_true", help="Enable Claude Code integration for file modifications and coding tasks")
    parser.add_argument("--file", "-f", type=str, help="Read input from a file and append it to the prompt")
    parser.add_argument("--url", type=str, help="Repository URL for context analysis")
    parser.add_argument("--goal", type=str, help="Goal for context engineering")
    parser.add_argument("--auto-analyze", action="store_true", help="Enable automatic analysis in context engineering")
    parser.add_argument("--research", action="store_true", help="Run deep research on a topic")
    parser.add_argument("--query-rewrite", action="store_true", help="Rewrite query for better results (works with any command)")
    parser.add_argument("--rewrite-tools", type=str, help="Tools for query rewriter (e.g., 'internet_search' or path to tools.py)")
    parser.add_argument("--expand-prompt", action="store_true", help="Expand short prompt into detailed prompt (works with any command)")
    parser.add_argument("--expand-tools", type=str, help="Tools for prompt expander (e.g., 'internet_search' or path to tools.py)")
    parser.add_argument("--tools", "-t", type=str, help="Path to tools.py file for research agent")
    parser.add_argument("--toolset", type=str, help="Named toolset groups (comma-separated, e.g., web,files,research)")
    parser.add_argument("--no-tools", action="store_true", help="Disable default built-in tools (for models that don't support tool calling)")
    parser.add_argument("--no-acp", action="store_true", help="Disable ACP tools (agentic file operations with plan/approve/apply)")
    parser.add_argument("--no-lsp", action="store_true", help="Disable LSP tools (code intelligence: symbols, definitions, references)")
    parser.add_argument("--no-context", action="store_true", help="Disable auto-loading of project context files (AGENTS.md/CLAUDE.md) into the system prompt")
    parser.add_argument("--save", "-s", action="store_true", help="Save research output to file (output/research/)")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                      help="Increase verbosity (-v=verbose, -vv=debug)")
    parser.add_argument("-q", "--quiet", action="count", default=0,
                      help="Decrease verbosity (-q=quiet, -qq=silent)")
    parser.add_argument("--output", type=str, choices=["json", "jsonl", "editor"], dest="output_format",
                      help="Output format (json, jsonl, or editor for user-friendly conversation-style)")
    parser.add_argument("--flow", action="store_true",
                      help="Show visual agent→tool flow chart")
    parser.add_argument("--web", "--web-search", action="store_true", help="Enable native web search (OpenAI, Gemini, Anthropic, xAI, Perplexity)")
    parser.add_argument("--web-fetch", action="store_true", help="Enable web fetch to retrieve URL content (Anthropic only)")
    parser.add_argument("--prompt-caching", action="store_true", help="Enable prompt caching to reduce costs (OpenAI, Anthropic, Bedrock, Deepseek)")
    parser.add_argument("--stream", action="store_true", help="Enable real-time streaming for agent responses")
    parser.add_argument("--stream-metrics", action="store_true", help="Enable streaming with token metrics display")

    # Planning Mode arguments
    parser.add_argument("--planning", action="store_true", help="Enable planning mode - create plan before execution")
    parser.add_argument("--planning-tools", type=str, help="Tools for planning research (path to tools.py or comma-separated tool names)")
    parser.add_argument("--planning-reasoning", action="store_true", help="Enable chain-of-thought reasoning in planning")
    parser.add_argument("--auto-approve-plan", action="store_true", help="Auto-approve generated plans without user confirmation")
    parser.add_argument("--max-tokens", type=int, default=16000, help="Maximum output tokens for agent responses (default: 16000)")
    parser.add_argument("--final-agent", type=str, help="Final agent instruction to process the output (e.g., 'Write a detailed blog post')")

    # Memory arguments
    parser.add_argument("--memory", action="store_true", help="Enable file-based memory for agent")
    parser.add_argument("--user-id", type=str, help="User ID for memory isolation")
    parser.add_argument("--message-steering", action="store_true", help="Enable real-time message steering for agents during execution")

    # Session management arguments
    parser.add_argument("--auto-save", type=str, metavar="NAME", help="Auto-save session with given name after each run")
    parser.add_argument("--history", type=int, metavar="N", help="Load history from last N sessions into context")

    # Rules arguments
    parser.add_argument("--include-rules", type=str, help="Include manual rules by name (comma-separated)")
    parser.add_argument("--no-rules", action="store_true", help="Disable automatic project rule injection")

    # Workflow arguments (uses global --memory, --save, --verbose, --planning flags)
    parser.add_argument("--workflow", type=str, help="Run inline workflow steps (format: 'step1:action1,step2:action2')")
    parser.add_argument("--workflow-var", action="append", help="Workflow variable in key=value format (can be used multiple times)")

    # Claude Memory Tool arguments
    parser.add_argument("--claude-memory", action="store_true", help="Enable Claude Memory Tool (Anthropic models only)")

    # New CLI Feature arguments (from cli_features module)
    # Guardrail - output validation
    parser.add_argument("--guardrail", type=str, help="Validate output with LLM guardrail (provide description)")

    # Metrics - token/cost tracking
    parser.add_argument("--metrics", action="store_true", help="Display token usage and cost metrics")
    parser.add_argument("--metrics-json", action="store_true", help="Output structured cost and token data as JSON")

    # Image Description (Vision) - analyze existing images
    parser.add_argument("--image", type=str, help="Path to image file for vision-based description/analysis")

    # Image Generation - create new images from text
    parser.add_argument("--image-generate", action="store_true", dest="image_generate", 
                      help="Generate an image from the text prompt (use with --llm for model selection)")

    # Telemetry - usage monitoring
    parser.add_argument("--telemetry", action="store_true", help="Enable usage monitoring and analytics")

    # Profiling - unified execution profiling
    parser.add_argument("--profile", action="store_true", help="Enable profiling with timing breakdown")
    parser.add_argument("--profile-deep", action="store_true", dest="profile_deep", help="Enable deep profiling with call graph (higher overhead)")
    parser.add_argument("--profile-format", type=str, choices=["text", "json"], default="text", dest="profile_format", help="Profile output format")

    # MCP - Model Context Protocol
    parser.add_argument("--mcp", type=str, help="MCP server command (e.g., 'npx -y @modelcontextprotocol/server-filesystem .')")
    parser.add_argument("--mcp-env", type=str, help="MCP environment variables (KEY=value,KEY2=value2)")

    # Fast Context - codebase search
    parser.add_argument("--fast-context", type=str, help="Path to search for relevant code context")

    # Handoff - agent delegation with unified HandoffConfig
    parser.add_argument("--handoff", type=str, help="Comma-separated agent roles for task delegation")
    parser.add_argument("--handoff-policy", type=str, choices=["full", "summary", "none", "last_n"],
                      help="Context sharing policy for handoffs (default: summary)")
    parser.add_argument("--handoff-timeout", type=float, help="Timeout in seconds for handoff execution")
    parser.add_argument("--handoff-max-depth", type=int, help="Maximum handoff chain depth (default: 10)")
    parser.add_argument("--handoff-max-concurrent", type=int, help="Maximum concurrent handoffs (default: 3)")
    parser.add_argument("--handoff-detect-cycles", type=str, choices=["true", "false"],
                      help="Enable cycle detection in handoff chains (default: true)")

    # Auto Memory - automatic memory extraction
    parser.add_argument("--auto-memory", action="store_true", help="Enable automatic memory extraction")

    # Todo - task list generation
    parser.add_argument("--todo", action="store_true", help="Generate todo list from task")

    # Router - smart model selection
    parser.add_argument("--router", action="store_true", help="Auto-select best model based on task complexity")
    parser.add_argument("--router-provider", type=str, help="Preferred provider for router (openai, anthropic, google)")

    # AutoRag - automatic RAG retrieval decision
    parser.add_argument("--auto-rag", action="store_true", help="Enable automatic RAG retrieval (decides when to retrieve vs direct chat)")
    parser.add_argument("--rag-policy", type=str, choices=["auto", "always", "never"], default="auto",
                      help="RAG retrieval policy: auto (decide per query), always, never")
    parser.add_argument("--rag-top-k", type=int, default=5, help="Number of results to retrieve (default: 5)")
    parser.add_argument("--rag-hybrid", action="store_true", help="Enable hybrid retrieval (semantic + keyword)")
    parser.add_argument("--rag-rerank", action="store_true", help="Enable result reranking")

    # Flow Display - visual workflow
    parser.add_argument("--flow-display", action="store_true", help="Enable visual workflow tracking")

    # n8n Integration - export workflow to n8n
    parser.add_argument("--n8n", action="store_true", help="Export workflow to n8n and open in browser")
    parser.add_argument("--n8n-url", type=str, default="http://localhost:5678", help="n8n instance URL (default: http://localhost:5678)")
    parser.add_argument("--api-url", type=str, help="PraisonAI API URL for n8n to call (default: auto-detected; for Docker Desktop on macOS/Windows with N8N_DOCKER=1 use http://host.docker.internal:8005)")

    # Serve - start API server for agents
    parser.add_argument("--serve", action="store_true", help="Start API server for agents (use with agents.yaml)")
    parser.add_argument("--port", type=int, default=8005, help="Server port (default: 8005)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Server host (default: 127.0.0.1)")

    # Session management
    parser.add_argument("--resume", type=str, dest="resume_session", metavar="SESSION", help="Resume a session (use 'last' for most recent, or session ID)")

    # Direct prompt flag - alternative to positional command
    parser.add_argument("-p", "--prompt", type=str, dest="prompt_flag", help="Direct prompt to execute (alternative to positional argument)")

    # Autonomy Mode - full_auto by default for multi-turn autonomous execution
    # ACP tools disabled by default for speed; use --acp to enable
    parser.add_argument("--autonomy", type=str, choices=["suggest", "auto_edit", "full_auto", "disable"], 
                      default=None, help="Set autonomy mode. Only use for multi-turn tasks that need iterative execution.")
    parser.add_argument("--acp", action="store_true", 
                      help="Enable ACP tools in autonomy mode (slower but more powerful file operations)")
    parser.add_argument("--lsp", action="store_true", 
                      help="Enable LSP tools in autonomy mode (slower but provides code intelligence)")


    # P8/G11: Tool timeout - prevent slow tools from blocking
    parser.add_argument("--tool-timeout", type=int, default=60,
                      help="Timeout in seconds for each tool call (default: 60)")

    # Tool retry policy - handle transient failures with exponential backoff
    parser.add_argument("--tool-retry-attempts", type=int, default=3,
                      help="Maximum retry attempts for tool failures (default: 3)")
    parser.add_argument("--tool-retry-delay", type=int, default=1000,
                      help="Initial retry delay in milliseconds (default: 1000)")
    parser.add_argument("--tool-retry-backoff", type=float, default=2.0,
                      help="Retry backoff multiplier (default: 2.0)")
    parser.add_argument("--tool-retry-on", type=str, default="timeout,rate_limit,connection_error",
                      help="Error types to retry (comma-separated, default: timeout,rate_limit,connection_error)")

    # Tool Approval - control tool execution approval
    parser.add_argument("--trust", action="store_true", help="Auto-approve all tool executions (skip approval prompts)")
    parser.add_argument("--approve-level", type=str, choices=["low", "medium", "high", "critical"], 
                      help="Auto-approve tools up to this risk level (e.g., --approve-level high approves low/medium/high but prompts for critical)")
    parser.add_argument("--approval", type=str, 
                      help="Approval backend: console, slack, telegram, discord, webhook, http, agent, auto, none")
    parser.add_argument("--approve-all-tools", action="store_true",
                      help="Require approval for ALL tool calls, not just dangerous tools (default: dangerous only)")
    parser.add_argument("--approval-timeout", type=str, default=None,
                      help="Seconds to wait for approval response. Use 'none' for indefinite wait (default: backend default)")

    # Sandbox Execution - secure command execution
    parser.add_argument("--sandbox", type=str, choices=["off", "basic", "strict"], help="Enable sandboxed command execution")

    # Backend group - mutually exclusive external agent and CLI backend options
    backend_group = parser.add_mutually_exclusive_group()
    backend_group.add_argument("--external-agent", type=str, choices=["claude", "gemini", "codex", "cursor"],
                      help="Use external AI CLI tool (claude, gemini, codex, cursor)")

    # CLI Backend - delegate agent turns to CLI backend
    # Dynamically populate choices from registered backends
    try:
        from praisonai_code.cli_backends import list_cli_backends
        cli_backend_choices = list_cli_backends() or None
    except ImportError:
        cli_backend_choices = None

    backend_group.add_argument("--cli-backend", type=str, choices=cli_backend_choices,
                      help="Delegate agent turns to a CLI backend (see praisonai backends list)")

    # External agent direct mode (not mutually exclusive with backend choice)
    parser.add_argument("--external-agent-direct", action="store_true",
                      help="Use external agent as direct proxy (skip manager Agent delegation)")

    # Compare - compare different CLI modes
    parser.add_argument("--compare", type=str, help="Compare CLI modes (comma-separated: basic,tools,research,planning)")
    parser.add_argument("--compare-output", type=str, help="Save comparison results to file")

    # Context Management - context budgeting, optimization, and monitoring
    parser.add_argument("--context-auto-compact", action="store_true", dest="context_auto_compact", 
                      help="Enable automatic context compaction (default in interactive mode)")
    parser.add_argument("--no-context-auto-compact", action="store_false", dest="context_auto_compact",
                      help="Disable automatic context compaction")
    parser.add_argument("--context-strategy", type=str, choices=["truncate", "sliding_window", "prune_tools", "summarize", "smart"],
                      help="Context optimization strategy (default: smart)")
    parser.add_argument("--context-threshold", type=float, metavar="0.0-1.0",
                      help="Trigger compaction at this utilization (default: 0.8)")
    parser.add_argument("--context-monitor", action="store_true", dest="context_monitor",
                      help="Enable real-time context monitoring (writes to context.txt)")
    parser.add_argument("--context-monitor-path", type=str, metavar="PATH",
                      help="Path for context monitor output (default: ./context.txt)")
    parser.add_argument("--context-monitor-format", type=str, choices=["human", "json"],
                      help="Context monitor output format (default: human)")
    parser.add_argument("--context-monitor-frequency", type=str, choices=["turn", "tool_call", "manual", "overflow"],
                      help="Context monitor update frequency (default: turn)")
    parser.add_argument("--context-redact", action="store_true", dest="context_redact",
                      help="Redact sensitive data in context monitor output (default: true)")
    parser.add_argument("--no-context-redact", action="store_false", dest="context_redact",
                      help="Disable sensitive data redaction in context monitor")
    parser.add_argument("--context-output-reserve", type=int, metavar="TOKENS",
                      help="Reserve tokens for model output (default: 8000)")

    # Agent Scheduler - for schedule command
    parser.add_argument("--interval", dest="schedule_interval", type=str, help="Schedule interval (e.g., 'hourly', '*/30m', 'daily')")
    parser.add_argument("--schedule-max-retries", dest="schedule_max_retries", type=int, help="Maximum retry attempts for scheduled execution")
    parser.add_argument("--timeout", type=int, help="Maximum execution time per run in seconds")
    parser.add_argument('--max-cost', type=float, help='Maximum total cost budget in USD')
    parser.add_argument('--daemon', action='store_true', help=argparse.SUPPRESS)  # Hidden flag for daemon mode

    # Rate Limiter - control API request rate
    parser.add_argument("--rpm", type=int, help="Rate limit: requests per minute for LLM calls")
    parser.add_argument("--tpm", type=int, help="Rate limit: tokens per minute for LLM calls (optional)")

    # Configurable Model - runtime model switching
    parser.add_argument("--configurable-model", action="store_true", help="Enable runtime model switching via config parameter")
    parser.add_argument("--temperature", type=float, help="Override temperature for LLM calls")
    parser.add_argument("--llm-provider", type=str, help="Override LLM provider (openai, anthropic, google, etc.)")

    # Ollama Provider - native Ollama integration
    parser.add_argument("--ollama-model", type=str, help="Ollama model name (e.g., llama3.2:3b, mistral, qwen2.5:7b)")
    parser.add_argument("--ollama-host", type=str, help="Ollama server host (default: http://localhost:11434)")

    # Tool calling reliability - for weak/local models like Ollama
    parser.add_argument("--max-tool-repairs", type=int, default=None,
                      help="Max tool call repair attempts (default: 2 for Ollama, 0 for others)")
    parser.add_argument("--force-tool-usage", type=str, choices=["auto", "always", "never"], default=None,
                      help="Force tool usage mode: auto (default for Ollama), always, never")

    # If we're in a test environment, parse with empty args to avoid pytest interference
    if in_test_env:
        args, unknown_args = parser.parse_known_args([])
    else:
        args, unknown_args = parser.parse_known_args()
    return args, unknown_args, special_commands
