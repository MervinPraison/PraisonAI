"""
Chat command group for PraisonAI CLI.

Provides interactive chat commands.
"""

from typing import List, Optional

import typer

app = typer.Typer(help="Interactive chat mode")


@app.callback(invoke_without_command=True)
def chat_main(
    ctx: typer.Context,
    prompt: Optional[str] = typer.Argument(None, help="Initial prompt for chat"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    memory: bool = typer.Option(False, "--memory", help="Enable memory"),
    tools: Optional[str] = typer.Option(None, "--tools", "-t", help="Tools file path"),
    user_id: Optional[str] = typer.Option(None, "--user-id", help="User ID for memory isolation"),
    session_id: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID to resume"),
    continue_session: bool = typer.Option(False, "--continue", "-c", help="Continue last session"),
    file: Optional[List[str]] = typer.Option(None, "--file", "-f", help="Attach file(s) to prompt"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
):
    """
    Start interactive chat mode.
    
    Examples:
        praisonai chat
        praisonai chat "Hello, how are you?"
        praisonai chat --model gpt-4o --memory
        praisonai chat --continue  # Resume last session
        praisonai chat "Summarize this" --file README.md
    """
    import asyncio
    
    # Use unified InteractiveCore
    try:
        from praisonai.cli.interactive import InteractiveCore, InteractiveConfig
        from praisonai.cli.interactive.frontends import RichFrontend
        
        config = InteractiveConfig(
            model=model,
            session_id=session_id,
            continue_session=continue_session,
            workspace=workspace or None,
            verbose=verbose,
            memory=memory,
            files=list(file) if file else [],
        )
        
        core = InteractiveCore(config=config)
        
        if prompt:
            # Single prompt mode
            async def run_prompt():
                if continue_session:
                    core.continue_session()
                response = await core.prompt(prompt)
                print(response)
            
            asyncio.run(run_prompt())
        else:
            # Interactive REPL mode
            frontend = RichFrontend(core=core, config=config)
            asyncio.run(frontend.run())
            
    except ImportError:
        # Fallback to legacy handler
        from praisonai.cli.main import PraisonAI
        import sys
        
        argv = ['chat']
        if prompt:
            argv.append(prompt)
        if model:
            argv.extend(['--model', model])
        if verbose:
            argv.append('--verbose')
        if memory:
            argv.append('--memory')
        if tools:
            argv.extend(['--tools', tools])
        if user_id:
            argv.extend(['--user-id', user_id])
        
        original_argv = sys.argv
        sys.argv = ['praisonai'] + argv
        
        try:
            praison = PraisonAI()
            praison.main()
        except SystemExit:
            pass
        finally:
            sys.argv = original_argv
