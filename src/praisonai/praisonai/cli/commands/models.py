"""
Models command group for PraisonAI CLI.

Provides commands to list and describe available LLM models.
"""

from typing import Optional, List, Dict, Any
import typer
import json

from ..output.console import get_output_controller

app = typer.Typer(help="List and describe available models")


@app.command(name="list")
def list_models(
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Filter by provider name"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    search: Optional[str] = typer.Argument(None, help="Filter by model name pattern"),
):
    """
    List available models with capabilities and limits.
    
    Examples:
        praisonai models list
        praisonai models list --provider openai
        praisonai models list gpt
        praisonai models list --json
    """
    output = get_output_controller()
    
    try:
        from ...llm.catalogue import ModelCatalogue
        catalogue = ModelCatalogue()
        models = catalogue.list_models(provider=provider, search=search)
        
        if json_output:
            output.print(json.dumps(models, indent=2))
            return
        
        if not models:
            output.print_info("No models found matching your criteria")
            return
        
        # Group models by provider for better display
        by_provider: Dict[str, List[Dict[str, Any]]] = {}
        for model in models:
            provider_name = model.get("provider", "unknown")
            if provider_name not in by_provider:
                by_provider[provider_name] = []
            by_provider[provider_name].append(model)
        
        # Display models in a table format
        from rich.table import Table
        from rich.console import Console
        
        console = Console()
        
        for provider_name, provider_models in sorted(by_provider.items()):
            table = Table(title=f"\n{provider_name.upper()} Models", show_header=True, header_style="bold cyan")
            table.add_column("Model ID", style="green")
            table.add_column("Context", justify="right")
            table.add_column("Output", justify="right")
            table.add_column("Capabilities", style="yellow")
            table.add_column("Cost (1K)", justify="right", style="dim")
            
            for model in sorted(provider_models, key=lambda x: x.get("id", "")):
                # Format capabilities
                capabilities = []
                if model.get("supports_tools"):
                    capabilities.append("🔧 tools")
                if model.get("supports_vision"):
                    capabilities.append("👁️ vision")
                if model.get("supports_reasoning"):
                    capabilities.append("🧠 reasoning")
                cap_str = " ".join(capabilities) if capabilities else "-"
                
                # Format costs
                cost_str = "-"
                if model.get("input_cost") is not None and model.get("output_cost") is not None:
                    cost_str = f"${model['input_cost']:.4f}/${model['output_cost']:.4f}"
                
                # Format context/output limits
                context = str(model.get("max_context", "-"))
                output_limit = str(model.get("max_output", "-"))
                
                table.add_row(
                    model.get("id", "-"),
                    context,
                    output_limit,
                    cap_str,
                    cost_str
                )
            
            console.print(table)
        
    except ImportError:
        output.print_warning("Model catalogue not available. Install litellm for full model listing:")
        output.print("  pip install 'praisonai[litellm]'")
        
        # Show basic fallback models
        fallback_models = [
            {"provider": "OpenAI", "models": ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]},
            {"provider": "Anthropic", "models": ["claude-3-5-sonnet-latest", "claude-3-opus-latest", "claude-3-haiku-latest"]},
            {"provider": "Google", "models": ["gemini-1.5-pro", "gemini-1.5-flash"]},
            {"provider": "Groq", "models": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"]},
        ]
        
        if provider:
            fallback_models = [p for p in fallback_models if p["provider"].lower() == provider.lower()]
        
        for prov in fallback_models:
            output.print_subheader(f"{prov['provider']} Models")
            for model in prov['models']:
                if not search or search.lower() in model.lower():
                    output.print(f"  • {model}")
    except Exception as e:
        output.print_error(f"Error listing models: {e}")
        raise typer.Exit(1)


@app.command(name="describe")
def describe_model(
    model: str = typer.Argument(..., help="Model ID to describe (e.g., gpt-4o, claude-3-5-sonnet)"),
):
    """
    Show detailed information for a specific model.
    
    Examples:
        praisonai models describe gpt-4o
        praisonai models describe claude-3-5-sonnet
        praisonai models describe gemini-1.5-pro
    """
    output = get_output_controller()
    
    try:
        from ...llm.catalogue import ModelCatalogue
        catalogue = ModelCatalogue()
        info = catalogue.describe_model(model)
        
        if not info:
            output.print_error(f"Model '{model}' not found")
            
            # Try to suggest similar models
            suggestions = catalogue.get_suggestions(model)
            if suggestions:
                output.print_info("Did you mean one of these?")
                for suggestion in suggestions[:5]:
                    output.print(f"  • {suggestion}")
            raise typer.Exit(1)
        
        # Display model details
        output.print_subheader(f"Model: {info.get('id', model)}")
        
        if info.get("provider"):
            output.print(f"Provider: {info['provider']}")
        
        if info.get("description"):
            output.print(f"Description: {info['description']}")
        
        # Capabilities
        output.print("\nCapabilities:")
        output.print(f"  • Tool calling: {'✅' if info.get('supports_tools') else '❌'}")
        output.print(f"  • Vision: {'✅' if info.get('supports_vision') else '❌'}")
        output.print(f"  • Reasoning: {'✅' if info.get('supports_reasoning') else '❌'}")
        output.print(f"  • Streaming: {'✅' if info.get('supports_streaming', True) else '❌'}")
        
        # Limits
        output.print("\nLimits:")
        if info.get("max_context"):
            output.print(f"  • Context window: {info['max_context']:,} tokens")
        if info.get("max_output"):
            output.print(f"  • Max output: {info['max_output']:,} tokens")
        
        # Costs
        if info.get("input_cost") is not None:
            output.print("\nCosts (per 1K tokens):")
            output.print(f"  • Input: ${info['input_cost']:.6f}")
            if info.get("output_cost") is not None:
                output.print(f"  • Output: ${info['output_cost']:.6f}")
        
        # Notes
        if info.get("notes"):
            output.print(f"\nNotes: {info['notes']}")
        
    except ImportError:
        output.print_warning("Model catalogue not available. Install litellm for detailed model info:")
        output.print("  pip install 'praisonai[litellm]'")
    except Exception as e:
        output.print_error(f"Error describing model: {e}")
        raise typer.Exit(1)


@app.command(name="validate")
def validate_model(
    model: str = typer.Argument(..., help="Model ID to validate"),
):
    """
    Validate if a model ID is valid and available.
    
    Examples:
        praisonai models validate gpt-4o
        praisonai models validate invalid-model
    """
    output = get_output_controller()
    
    try:
        from ...llm.catalogue import ModelCatalogue
        catalogue = ModelCatalogue()
        
        if catalogue.is_valid_model(model):
            output.print_success(f"✅ '{model}' is a valid model")
            
            # Show basic info if available
            info = catalogue.describe_model(model)
            if info:
                caps = []
                if info.get("supports_tools"):
                    caps.append("tool-calling")
                if info.get("supports_vision"):
                    caps.append("vision")
                if info.get("supports_reasoning"):
                    caps.append("reasoning")
                if caps:
                    output.print(f"Capabilities: {', '.join(caps)}")
        else:
            output.print_error(f"❌ '{model}' is not a valid model")
            
            # Suggest alternatives
            suggestions = catalogue.get_suggestions(model)
            if suggestions:
                output.print_info("Did you mean one of these?")
                for suggestion in suggestions[:5]:
                    output.print(f"  • {suggestion}")
            raise typer.Exit(1)
            
    except ImportError:
        output.print_warning("Model catalogue not available. Install litellm for model validation:")
        output.print("  pip install 'praisonai[litellm]'")
    except Exception as e:
        output.print_error(f"Error validating model: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()