"""
n8n CLI Commands

CLI commands for n8n workflow integration.
"""

import typer
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="n8n",
    help="n8n visual workflow editor integration commands",
    no_args_is_help=True,
    rich_markup_mode="rich"
)

@app.command()
def export(
    yaml_path: Path = typer.Argument(..., help="Path to YAML workflow file"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSON file path"),
    format: str = typer.Option("n8n", "--format", help="Export format (currently only n8n supported)")
):
    """Export PraisonAI YAML workflow to n8n JSON format.
    
    Example:
        praisonai n8n export my-workflow.yaml --output workflow.json
    """
    if format != 'n8n':
        typer.echo(f"Error: Unsupported format '{format}'. Only 'n8n' is supported.", err=True)
        raise typer.Exit(1)
    
    try:
        from praisonai.n8n import YAMLToN8nConverter
        import yaml as yaml_lib
        import json
        
        # Load YAML workflow
        with open(yaml_path, 'r') as f:
            yaml_workflow = yaml_lib.safe_load(f)
        
        # Convert to n8n format
        converter = YAMLToN8nConverter()
        n8n_json = converter.convert(yaml_workflow)
        
        # Determine output path
        if output is None:
            output = yaml_path.with_suffix('.json')
        
        # Write JSON file
        with open(output, 'w') as f:
            json.dump(n8n_json, f, indent=2)
        
        typer.echo(f"✅ Exported workflow to: {output}")
        typer.echo(f"💡 Import this file into n8n or use 'praisonai n8n preview {yaml_path}' to open directly")
        
    except ImportError:
        typer.echo("Error: n8n dependencies not installed. Run: pip install 'praisonai[n8n]'", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@app.command(name="import")
def import_workflow(
    json_path: Path = typer.Argument(..., help="Path to n8n JSON workflow file"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output YAML file path"),
    format: str = typer.Option("n8n", "--format", help="Import format (currently only n8n supported)")
):
    """Import n8n JSON workflow to PraisonAI YAML format.
    
    Example:
        praisonai n8n import workflow.json --output my-workflow.yaml
    """
    if format != 'n8n':
        typer.echo(f"Error: Unsupported format '{format}'. Only 'n8n' is supported.", err=True)
        raise typer.Exit(1)
    
    try:
        from praisonai.n8n import N8nToYAMLConverter
        import yaml as yaml_lib
        import json
        
        # Load n8n JSON workflow
        with open(json_path, 'r') as f:
            n8n_workflow = json.load(f)
        
        # Convert to YAML format
        converter = N8nToYAMLConverter()
        yaml_workflow = converter.convert(n8n_workflow)
        
        # Determine output path
        if output is None:
            output = json_path.with_suffix('.yaml')
        
        # Write YAML file
        with open(output, 'w') as f:
            yaml_lib.dump(yaml_workflow, f, default_flow_style=False, sort_keys=False)
        
        typer.echo(f"✅ Imported workflow to: {output}")
        typer.echo(f"💡 Run 'praisonai run {output}' to execute the workflow")
        
    except ImportError:
        typer.echo("Error: n8n dependencies not installed. Run: pip install 'praisonai[n8n]'", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@app.command()
def preview(
    yaml_path: Path = typer.Argument(..., help="Path to YAML workflow file"),
    n8n_url: str = typer.Option("http://localhost:5678", "--n8n-url", help="n8n instance URL"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="n8n API key (or set N8N_API_KEY env var)"),
    no_open: bool = typer.Option(False, "--no-open", help="Do not automatically open browser")
):
    """Preview PraisonAI workflow in n8n visual editor.
    
    This command converts your YAML workflow to n8n format and opens it
    in the n8n visual editor for preview and editing.
    
    Example:
        praisonai n8n preview my-workflow.yaml
        praisonai n8n preview my-workflow.yaml --n8n-url http://n8n.example.com
    """
    try:
        from praisonai.n8n import preview_workflow
        
        # Preview workflow in n8n
        editor_url = preview_workflow(
            yaml_path=str(yaml_path),
            n8n_url=n8n_url,
            api_key=api_key,
            auto_open=not no_open
        )
        
        typer.echo(f"✅ Workflow created in n8n")
        typer.echo(f"🌐 Editor URL: {editor_url}")
        
        if no_open:
            typer.echo(f"💡 Open the URL above to view/edit your workflow visually")
        else:
            typer.echo(f"💡 Browser should open automatically. If not, visit the URL above")
            
    except ImportError:
        typer.echo("Error: n8n dependencies not installed. Run: pip install 'praisonai[n8n]'", err=True)
        raise typer.Exit(1)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except ConnectionError as e:
        typer.echo(f"Connection Error: {e}", err=True)
        typer.echo("💡 Make sure n8n is running. Start with: npx n8n start")
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@app.command()
def pull(
    workflow_id: str = typer.Argument(..., help="n8n workflow ID"),
    output_path: Path = typer.Argument(..., help="Path where to save YAML file"),
    n8n_url: str = typer.Option("http://localhost:5678", "--n8n-url", help="n8n instance URL"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="n8n API key (or set N8N_API_KEY env var)")
):
    """Pull workflow from n8n and convert to YAML.
    
    Example:
        praisonai n8n pull abc123 my-workflow.yaml
    """
    try:
        from praisonai.n8n import export_from_n8n
        
        # Export from n8n to YAML
        export_from_n8n(
            workflow_id=workflow_id,
            output_path=str(output_path),
            n8n_url=n8n_url,
            api_key=api_key
        )
        
        typer.echo(f"✅ Pulled workflow {workflow_id} to: {output_path}")
        typer.echo(f"💡 Run 'praisonai run {output_path}' to execute the workflow")
        
    except ImportError:
        typer.echo("Error: n8n dependencies not installed. Run: pip install 'praisonai[n8n]'", err=True)
        raise typer.Exit(1)
    except ConnectionError as e:
        typer.echo(f"Connection Error: {e}", err=True)
        typer.echo("💡 Make sure n8n is running and accessible")
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@app.command()
def push(
    yaml_path: Path = typer.Argument(..., help="Path to YAML workflow file"),
    workflow_id: str = typer.Argument(..., help="Existing n8n workflow ID to update"),
    n8n_url: str = typer.Option("http://localhost:5678", "--n8n-url", help="n8n instance URL"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="n8n API key (or set N8N_API_KEY env var)")
):
    """Push YAML workflow updates to existing n8n workflow.
    
    Example:
        praisonai n8n push my-workflow.yaml abc123
    """
    try:
        from praisonai.n8n import sync_workflow
        
        # Sync workflow with n8n
        editor_url = sync_workflow(
            yaml_path=str(yaml_path),
            workflow_id=workflow_id,
            n8n_url=n8n_url,
            api_key=api_key
        )
        
        typer.echo(f"✅ Synced workflow {workflow_id}")
        typer.echo(f"🌐 Editor URL: {editor_url}")
        
    except ImportError:
        typer.echo("Error: n8n dependencies not installed. Run: pip install 'praisonai[n8n]'", err=True)
        raise typer.Exit(1)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except ConnectionError as e:
        typer.echo(f"Connection Error: {e}", err=True)
        typer.echo("💡 Make sure n8n is running and accessible")
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@app.command(name="test")
def test_connection(
    n8n_url: str = typer.Option("http://localhost:5678", "--n8n-url", help="n8n instance URL"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="n8n API key (or set N8N_API_KEY env var)")
):
    """Test connection to n8n instance.
    
    Example:
        praisonai n8n test
        praisonai n8n test --n8n-url http://n8n.example.com
    """
    try:
        from praisonai.n8n import N8nClient
        
        client = N8nClient(base_url=n8n_url, api_key=api_key)
        
        if client.test_connection():
            typer.echo(f"✅ Connected to n8n at {n8n_url}")
            
            # Try to list workflows to test API access
            try:
                workflows = client.list_workflows()
                typer.echo(f"📊 Found {len(workflows)} workflows")
            except Exception as e:
                typer.echo(f"⚠️  Connection successful but API access failed: {e}")
                typer.echo("💡 Check your API key or n8n permissions")
        else:
            typer.echo(f"❌ Cannot connect to n8n at {n8n_url}")
            typer.echo("💡 Make sure n8n is running. Start with: npx n8n start")
            raise typer.Exit(1)
            
        client.close()
        
    except ImportError:
        typer.echo("Error: n8n dependencies not installed. Run: pip install 'praisonai[n8n]'", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@app.command(name="list")
def list_workflows(
    n8n_url: str = typer.Option("http://localhost:5678", "--n8n-url", help="n8n instance URL"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="n8n API key (or set N8N_API_KEY env var)")
):
    """List workflows in n8n instance.
    
    Example:
        praisonai n8n list
    """
    try:
        from praisonai.n8n import N8nClient
        
        client = N8nClient(base_url=n8n_url, api_key=api_key)
        
        workflows = client.list_workflows()
        
        if not workflows:
            typer.echo("No workflows found in n8n")
        else:
            typer.echo(f"Found {len(workflows)} workflows:")
            typer.echo()
            
            for workflow in workflows:
                workflow_id = workflow.get('id', 'Unknown')
                name = workflow.get('name', 'Untitled')
                active = workflow.get('active', False)
                status = "✅ Active" if active else "⏸️  Inactive"
                
                typer.echo(f"  {workflow_id}: {name} ({status})")
        
        client.close()
        
    except ImportError:
        typer.echo("Error: n8n dependencies not installed. Run: pip install 'praisonai[n8n]'", err=True)
        raise typer.Exit(1)
    except ConnectionError as e:
        typer.echo(f"Connection Error: {e}", err=True)
        typer.echo("💡 Make sure n8n is running and accessible")
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
