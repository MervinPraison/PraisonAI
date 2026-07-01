"""
Ollama CLI Handler

CLI support for Ollama provider and Weak-Model-Proof execution.
"""

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class OllamaHandler:
    """
    Handler for Ollama CLI commands.
    
    Supports:
    - --provider ollama
    - --weak-model-proof / --wmp
    - --ollama-host
    - --ollama-model
    """
    
    def __init__(
        self,
        model: str = "llama3.2:3b",
        host: Optional[str] = None,
        weak_model_proof: bool = True,
        verbose: bool = False,
        **kwargs
    ):
        """
        Initialize Ollama handler.
        
        Args:
            model: Ollama model name
            host: Ollama server host
            weak_model_proof: Enable WMP
            verbose: Verbose output
            **kwargs: Additional options
        """
        self.model = model
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.weak_model_proof = weak_model_proof
        self.verbose = verbose
        self.extra_kwargs = kwargs
        
        self._provider = None
        self._wmp_hooks = None
    
    @property
    def provider(self):
        """Lazy-load Ollama provider."""
        if self._provider is None:
            try:
                from praisonai.providers import OllamaProvider
                self._provider = OllamaProvider(
                    model=self.model,
                    host=self.host,
                    weak_model_proof=self.weak_model_proof,
                    **self.extra_kwargs
                )
            except ImportError as e:
                logger.error(f"Failed to import OllamaProvider: {e}")
                raise
        return self._provider
    
    @property
    def wmp_hooks(self):
        """Lazy-load WMP hooks."""
        if self._wmp_hooks is None and self.weak_model_proof:
            try:
                from praisonai.wmp import WMPHooks, WeakModelProofConfig
                
                # Auto-configure based on model
                config = WeakModelProofConfig.for_ollama(
                    self._detect_model_size()
                )
                
                self._wmp_hooks = WMPHooks(
                    config=config,
                    llm_fn=self._llm_fn,
                )
            except ImportError as e:
                logger.warning(f"WMP not available: {e}")
                self._wmp_hooks = None
        return self._wmp_hooks
    
    def _detect_model_size(self) -> str:
        """Detect model size from name."""
        model_lower = self.model.lower()
        
        if any(x in model_lower for x in ["70b", "72b", "65b"]):
            return "large"
        elif any(x in model_lower for x in ["13b", "14b", "7b", "8b"]):
            return "medium"
        else:
            return "small"
    
    def _llm_fn(self, prompt: str) -> str:
        """LLM function for WMP."""
        response = self.provider.chat(prompt)
        return response.content
    
    def chat(
        self,
        message: str,
        system: Optional[str] = None,
        stream: bool = False,
    ) -> str:
        """
        Send a chat message.
        
        Args:
            message: User message
            system: System prompt
            stream: Enable streaming
            
        Returns:
            Response text
        """
        if self.weak_model_proof and self.wmp_hooks:
            # Use WMP execution
            self.wmp_hooks.on_task_start(message)
            
            messages = [{"role": "user", "content": message}]
            if system:
                messages.insert(0, {"role": "system", "content": system})
            
            enhanced_messages = self.wmp_hooks.on_before_llm_call(messages)
            
            # Call Ollama
            response = self.provider.chat(
                messages=enhanced_messages,
                stream=stream,
            )
            
            if stream:
                # Collect streamed response
                full_response = ""
                for chunk in response:
                    full_response += chunk
                    if self.verbose:
                        print(chunk, end="", flush=True)
                if self.verbose:
                    print()
                response_text = full_response
            else:
                response_text = response.content
            
            # Post-process with WMP
            response_text = self.wmp_hooks.on_after_llm_call(response_text)
            
            return response_text
        else:
            # Direct Ollama call
            response = self.provider.chat(
                messages=message,
                system=system,
                stream=stream,
            )
            
            if stream:
                full_response = ""
                for chunk in response:
                    full_response += chunk
                    if self.verbose:
                        print(chunk, end="", flush=True)
                if self.verbose:
                    print()
                return full_response
            else:
                return response.content
    
    def execute(
        self,
        task: str,
        tools: Optional[List] = None,
    ) -> Dict[str, Any]:
        """
        Execute a task with WMP.
        
        Args:
            task: Task description
            tools: Available tools
            
        Returns:
            Execution result
        """
        if self.weak_model_proof:
            try:
                from praisonai.wmp import WMPExecutor, WeakModelProofConfig
                
                config = WeakModelProofConfig.for_ollama(
                    self._detect_model_size()
                )
                
                executor = WMPExecutor(config=config)
                result = executor.execute(
                    task=task,
                    llm_fn=self._llm_fn,
                    tools=tools,
                )
                
                return result.to_dict()
                
            except ImportError:
                logger.warning("WMP not available, falling back to direct execution")
        
        # Direct execution
        response = self.chat(task)
        return {
            "success": True,
            "result": response,
            "wmp_enabled": False,
        }
    
    def list_models(self) -> List[Dict[str, Any]]:
        """List available Ollama models."""
        return self.provider.list_models()
    
    def pull_model(self, model: str) -> None:
        """Pull a model from Ollama registry."""
        if self.verbose:
            print(f"Pulling model: {model}")
        
        for progress in self.provider.pull_model(model, stream=True):
            if self.verbose and hasattr(progress, 'status'):
                print(f"  {progress.status}", end="\r")
        
        if self.verbose:
            print(f"\nModel {model} pulled successfully")
    
    def is_available(self) -> bool:
        """Check if Ollama is available."""
        return self.provider.is_available()


def handle_ollama_command(args, unknown_args: List[str] = None) -> int:
    """
    Handle Ollama CLI commands.
    
    Args:
        args: Parsed arguments
        unknown_args: Unknown arguments
        
    Returns:
        Exit code
    """
    from rich.console import Console
    console = Console()
    
    # Get options from args
    model = getattr(args, 'ollama_model', None) or getattr(args, 'model', 'llama3.2:3b')
    host = getattr(args, 'ollama_host', None)
    wmp = getattr(args, 'weak_model_proof', True)
    verbose = getattr(args, 'verbose', False)
    
    try:
        handler = OllamaHandler(
            model=model,
            host=host,
            weak_model_proof=wmp,
            verbose=verbose,
        )
        
        # Check availability
        if not handler.is_available():
            console.print("[red]Error: Ollama server not available[/red]")
            console.print(f"Make sure Ollama is running at {handler.host}")
            return 1
        
        # Get command/prompt
        prompt = getattr(args, 'command', None) or getattr(args, 'direct_prompt', None)
        
        if not prompt:
            console.print("[yellow]No prompt provided[/yellow]")
            return 1
        
        # Execute
        if wmp:
            console.print(f"[dim]Using Ollama with Weak-Model-Proof ({model})[/dim]")
        else:
            console.print(f"[dim]Using Ollama ({model})[/dim]")
        
        result = handler.execute(prompt)
        
        if result.get("success"):
            console.print(result.get("result", ""))
            
            if verbose and result.get("wmp_enabled"):
                console.print(f"\n[dim]Steps: {result.get('steps_executed', 0)}, "
                            f"Retries: {result.get('retries', 0)}[/dim]")
        else:
            console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
            return 1
        
        return 0
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        return 1


def add_ollama_arguments(parser) -> None:
    """
    Add Ollama-related arguments to parser.
    
    Args:
        parser: ArgumentParser instance
    """
    parser.add_argument(
        "--provider",
        type=str,
        choices=["ollama", "litellm", "openai"],
        help="LLM provider to use"
    )
    parser.add_argument(
        "--ollama-model",
        type=str,
        default="llama3.2:3b",
        help="Ollama model name (e.g., llama3.2:3b, mistral, qwen2.5:7b)"
    )
    parser.add_argument(
        "--ollama-host",
        type=str,
        help="Ollama server host (default: http://localhost:11434)"
    )
    parser.add_argument(
        "--weak-model-proof", "--wmp",
        action="store_true",
        default=None,
        dest="weak_model_proof",
        help="Enable Weak-Model-Proof execution (default: auto for Ollama)"
    )
    parser.add_argument(
        "--no-wmp",
        action="store_false",
        dest="weak_model_proof",
        help="Disable Weak-Model-Proof execution"
    )
    parser.add_argument(
        "--wmp-strict",
        action="store_true",
        help="Use strict WMP mode (more retries, stricter validation)"
    )
    parser.add_argument(
        "--wmp-fast",
        action="store_true",
        help="Use fast WMP mode (fewer retries, faster execution)"
    )
    parser.add_argument(
        "--step-budget",
        type=int,
        default=10,
        help="Maximum steps for WMP execution (default: 10)"
    )
