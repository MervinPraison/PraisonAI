"""
Legacy compatibility adapter for PraisonAI CLI.

Provides backward compatibility with the original argparse-based CLI.
Maps legacy usage patterns to Typer commands or existing feature handlers.
"""

import sys
from typing import List, Tuple


# Legacy commands that should be routed to existing handlers
LEGACY_COMMANDS = {
    'chat', 'code', 'call', 'realtime', 'train', 'ui', 'context', 'research',
    'memory', 'rules', 'workflow', 'hooks', 'knowledge', 'session', 'tools',
    'todo', 'docs', 'mcp', 'commit', 'serve', 'schedule', 'skills', 'profile',
    'eval', 'agents', 'run', 'thinking', 'compaction', 'output', 'deploy',
    'templates', 'recipe', 'endpoints', 'audio', 'embed', 'images', 'moderate',
    'files', 'batches', 'vector-stores', 'rerank', 'ocr', 'assistants',
    'fine-tuning', 'completions', 'messages', 'guardrails', 'rag', 'videos',
    'a2a', 'containers', 'passthrough', 'responses', 'search', 'realtime-api',
    'doctor', 'registry', 'package', 'install', 'uninstall', 'acp', 'debug',
    'lsp', 'diag', 'persistence', 'browser',
    # Bot/Gateway/Sandbox commands (added for resident agent features)
    'bot', 'gateway', 'sandbox', 'wizard', 'migrate', 'security',
}

# Typer commands that have been implemented
TYPER_COMMANDS = {
    # Core commands
    'config', 'traces', 'env', 'session', 'completion', 'version',
    'debug', 'lsp', 'diag', 'doctor', 'acp', 'mcp', 'serve', 'schedule', 'run',
    'tui', 'queue', 'profile', 'benchmark',
    # Previously legacy-only commands (now in Typer)
    'chat', 'code', 'call', 'realtime', 'train', 'ui', 'context', 'research',
    'memory', 'workflow', 'tools', 'knowledge', 'deploy', 'agents', 'skills',
    'eval', 'templates', 'recipe', 'todo', 'docs', 'commit', 'hooks', 'rules',
    'registry', 'package', 'endpoints', 'test', 'examples', 'batch',
    # Replay commands
    'replay',
    # Standardisation commands
    'standardise', 'standardize',
    # Moltbot-inspired commands (bots, browser, plugins, sandbox)
    'bot', 'browser', 'plugins', 'sandbox', 'loop',
    # RAG commands
    'rag', 'index', 'query', 'search',
}



def is_legacy_invocation(argv: List[str]) -> bool:
    """
    Check if the command line represents a legacy invocation.
    
    Legacy patterns:
    - praisonai "prompt"  (direct prompt)
    - praisonai agents.yaml  (file path)
    - praisonai --legacy-flag value  (legacy-only flags)
    - praisonai <legacy_command>  (commands not yet in Typer)
    """
    if not argv:
        return False
    
    # Global Typer options that should NOT trigger legacy mode
    typer_global_options = {
        '--json', '--output-format', '-o', '--no-color', '--quiet', '-q',
        '--verbose', '-v', '--screen-reader', '--help', '-h', '--version', '-V',
    }
    
    # Filter out global options to find the actual command
    filtered_argv = []
    skip_next = False
    for i, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if arg in typer_global_options:
            # Skip options that take a value
            if arg in ('--output-format', '-o'):
                skip_next = True
            continue
        filtered_argv.append(arg)
    
    first_arg = filtered_argv[0] if filtered_argv else ""
    
    # Check for legacy-only flags (not in Typer)
    # NOTE: --interactive and --chat-mode have been removed - use 'praisonai chat' instead
    legacy_flags = [
        '--framework', '--ui', '--auto', '--init', '--deploy', '--schedule',
        '--provider', '--model', '--llm', '--hf', '--ollama', '--dataset',
        '--realtime', '--call', '--public', '--merge', '--claudecode',
        '--file', '--url', '--goal', '--auto-analyze', '--research',
        '--query-rewrite', '--expand-prompt', '--tools', '--no-tools',
        '--save', '--web-search', '--web-fetch', '--prompt-caching',
        '--planning', '--memory', '--user-id', '--auto-save', '--history',
        '--workflow', '--guardrail', '--metrics', '--image', '--telemetry',
        '--mcp', '--fast-context', '--handoff', '--auto-memory', '--todo',
        '--router', '--flow-display', '--n8n', '--serve', '--port', '--host',
        '-p', '--autonomy', '--trust',
        '--sandbox', '--external-agent', '--compare', '--interval', '--timeout',
        '--max-cost', '--rpm', '--tpm', '--temperature',
    ]
    
    for arg in argv:
        if arg in legacy_flags:
            return True
    
    # Check if first arg is a legacy command not in Typer
    if first_arg in LEGACY_COMMANDS and first_arg not in TYPER_COMMANDS:
        return True
    
    # Check if first arg looks like a prompt (not a command, not a flag)
    if first_arg and not first_arg.startswith('-'):
        # If it's not a known Typer command, treat as legacy
        if first_arg not in TYPER_COMMANDS:
            # Could be a file path or prompt
            return True
    
    return False


def route_to_legacy(argv: List[str]) -> int:
    """
    Route to the legacy argparse CLI.
    
    Returns:
        Exit code from legacy CLI
    """
    from praisonai.cli.main import PraisonAI
    
    # Restore sys.argv for argparse
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        result = praison.main()
        return 0 if result is None else (1 if result is False else 0)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 0
    finally:
        sys.argv = original_argv


def translate_to_typer(argv: List[str]) -> Tuple[List[str], bool]:
    """
    Attempt to translate legacy argv to Typer format.
    
    Returns:
        Tuple of (translated_argv, was_translated)
    """
    if not argv:
        return argv, False
    
    first_arg = argv[0]
    
    # Direct mapping for commands that exist in both
    if first_arg in TYPER_COMMANDS:
        return argv, False  # Already Typer-compatible
    
    # Translate common patterns
    translations = {
        # Legacy flag patterns
        '--version': ['version', 'show'],
        '-V': ['version', 'show'],
    }
    
    if first_arg in translations:
        return translations[first_arg] + argv[1:], True
    
    return argv, False


def main_with_legacy_support():
    """
    Main entry point with legacy support.
    
    Routes to Typer CLI for new commands, legacy argparse CLI for old commands.
    """
    argv = sys.argv[1:]
    
    # Handle empty args - show help via Typer
    if not argv:
        try:
            from praisonai.cli.app import app
            app()
            return
        except SystemExit:
            return
    
    # Check for version flags first (handle specially)
    if '--version' in argv or '-V' in argv:
        from praisonai.version import __version__
        print(f"PraisonAI version {__version__}")
        return
    
    # Handle 'browser' command directly - delegate to browser Typer app
    # This must be done BEFORE is_legacy_invocation to avoid argparse capturing --help/--engine
    if argv and argv[0] == 'browser':
        try:
            from praisonai.browser.cli import app as browser_app
            # Browser Typer app expects 'run', 'sessions', etc as first arg, not 'browser'
            sys.argv = ['praisonai-browser'] + argv[1:]
            browser_app()
            return
        except SystemExit as e:
            sys.exit(e.code if isinstance(e.code, int) else 0)
    
    # IMPORTANT: Check for legacy invocation FIRST before trying Typer
    # This ensures legacy commands like 'chat' and flags like '--framework' work
    if is_legacy_invocation(argv):
        exit_code = route_to_legacy(argv)
        sys.exit(exit_code)
    
    # Global Typer options that should NOT trigger legacy mode
    typer_global_options = {
        '--json', '--output-format', '-o', '--no-color', '--quiet', '-q',
        '--verbose', '-v', '--screen-reader', '--help', '-h',
    }
    
    # Find the actual command (skip global options)
    actual_command = None
    skip_next = False
    for arg in argv:
        if skip_next:
            skip_next = False
            continue
        if arg in typer_global_options:
            if arg in ('--output-format', '-o'):
                skip_next = True
            continue
        if not arg.startswith('-'):
            actual_command = arg
            break
    
    # Route to Typer for known Typer commands
    if actual_command in TYPER_COMMANDS:
        try:
            from praisonai.cli.app import app
            sys.argv = ['praisonai'] + argv
            app()
            return
        except SystemExit as e:
            sys.exit(e.code if isinstance(e.code, int) else 0)
    
    # Check for help flags - route to Typer for help
    if '--help' in argv or '-h' in argv:
        try:
            from praisonai.cli.app import app
            sys.argv = ['praisonai'] + argv
            app()
            return
        except SystemExit:
            return
    
    # Default: try Typer, fall back to legacy on error
    try:
        from praisonai.cli.app import app
        sys.argv = ['praisonai'] + argv
        app()
    except SystemExit as e:
        sys.exit(e.code if isinstance(e.code, int) else 0)


if __name__ == "__main__":
    main_with_legacy_support()
