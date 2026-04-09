import os
import typer
import json
import asyncio
from typing import Optional
from rich import print
import subprocess
import time
import urllib.request
import urllib.error

app = typer.Typer(help="GitHub integration commands (triage, tracking).")

def fetch_github_api(url, token=None, method="GET", data=None):
    """Simple no-dependency wrapper for GitHub REST API."""
    req = urllib.request.Request(url, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(data).encode("utf-8")
        
    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 204:
                return {}
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[red]GitHub API Error: {e.code} - {e.read().decode('utf-8')}[/red]")
        raise

@app.command("triage")
def github_triage(
    issue: int = typer.Option(..., help="Issue or PR number to triage"),
    repo: Optional[str] = typer.Option(None, help="Repository (e.g. owner/repo). Defaults to GITHUB_REPOSITORY env var."),
    agent_file: str = typer.Option("agents.yaml", help="Path to the agents.yaml file to run."),
):
    """
    Triage a GitHub Issue/PR with PraisonAI native tracking and context injection.
    """
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("[red]Error: GITHUB_TOKEN or GH_TOKEN environment variable required.[/red]")
        raise typer.Exit(1)
        
    repo_name = repo or os.environ.get("GITHUB_REPOSITORY")
    if not repo_name:
        print("[red]Error: --repo must be provided if GITHUB_REPOSITORY is not set.[/red]")
        raise typer.Exit(1)
        
    print(f"[cyan]🚀 Starting PraisonAI Native Fetch & Triage for {repo_name}#{issue}...[/cyan]")
    
    # 1. Fetch Context
    api_base = f"https://api.github.com/repos/{repo_name}"
    issue_data = fetch_github_api(f"{api_base}/issues/{issue}", token=token)
    
    context_md = f"# GitHub Issue #{issue}: {issue_data.get('title')}\n\n{issue_data.get('body', '')}\n"
    
    if "pull_request" in issue_data:
        # Fetch PR diff
        print("[yellow]Detected Pull Request. Fetching diff Context...[/yellow]")
        req = urllib.request.Request(f"{api_base}/pulls/{issue}", method="GET")
        req.add_header("Accept", "application/vnd.github.v3.diff")
        req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req) as diff_resp:
                diff_text = diff_resp.read().decode("utf-8")
                context_md += f"\n## Code Diff\n```diff\n{diff_text}\n```"
        except urllib.error.HTTPError:
            pass

    # Save to file so agent YAML can read without bash escaping issues
    os.makedirs(".github", exist_ok=True)
    with open(".github/triage-context.md", "w") as f:
        f.write(context_md)
    print("[green]✅ Context saved to .github/triage-context.md[/green]")
    
    # 2. Drop Initial Tracking Comment
    run_url = ""
    if os.environ.get("GITHUB_RUN_ID"):
        run_url = f"[View Live Execution]({os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo_name}/actions/runs/{os.environ.get('GITHUB_RUN_ID')})"
        
    initial_body = f"🚀 **PraisonAI is working**...\n{run_url}\n\n- [ ] Fetching Context...\n- [ ] Running Agents..."
    comment_resp = fetch_github_api(f"{api_base}/issues/{issue}/comments", token=token, method="POST", data={"body": initial_body})
    comment_id = comment_resp["id"]
    print(f"[green]✅ Created Tracking Comment ID: {comment_id}[/green]")

    # 3. Setup Observer Sink to EventBus
    try:
        from praisonaiagents.bus.bus import get_default_bus
    except ImportError as e:
        print(f"[red]PraisonAIAgents SDK not found: {e}[/red]")
        raise typer.Exit(1)

    import threading
    bus = get_default_bus()
    agent_logs = []
    last_update_time = [time.time()]
    update_timer = [None]
    
    def _sync_push_comment():
        md_body = f"🚀 **PraisonAI is working**...\n{run_url}\n\n"
        for log in agent_logs[-15:]: # keep last 15 steps
            md_body += f"- {log}\n"
            
        try:
            fetch_github_api(f"{api_base}/issues/comments/{comment_id}", token=token, method="PATCH", data={"body": md_body})
        except:
            pass
        finally:
            last_update_time[0] = time.time()
            update_timer[0] = None

    def trigger_comment_update():
        if update_timer[0] is not None:
            return # already scheduled
        
        elapsed = time.time() - last_update_time[0]
        if elapsed >= 3.0:
            # Execute inline if throttle expired
            _sync_push_comment()
        else:
            # Schedule deferred update
            delay = 3.0 - elapsed
            update_timer[0] = threading.Timer(delay, _sync_push_comment)
            update_timer[0].start()
            
    async def track_agent_step(event):
        try:
            if event.type == "agent_start":
                agent_logs.append(f"🤖 Agent starting: {event.data.get('agent_name', 'Agent')}")
            elif event.type == "tool_start":
                agent_logs.append(f"🔧 Using tool: {event.data.get('tool_name')}")
            elif event.type == "agent_complete":
                agent_logs.append(f"✅ Agent completed: {event.data.get('agent_name')}")
            else:
                return # skip spam
            trigger_comment_update()
        except:
            pass

    bus.subscribe(track_agent_step)
    
    # 4. Trigger Normal PraisonAI Execution
    print(f"[cyan]▶️ Starting YAML Agent via `praisonai workflow run` equivalent...[/cyan]")
    try:
        from praisonai.cli.main import PraisonAI
        import sys
        
        original_argv = sys.argv
        sys.argv = ['praisonai', 'workflow', 'run', agent_file, '--var', f'ISSUE_NUMBER={issue}']
        try:
            praison = PraisonAI()
            praison.main()
        except SystemExit:
            pass
        finally:
            sys.argv = original_argv

        final_body = f"✅ **PraisonAI Triager Completed Successfully!**\n{run_url}\n\nResolved natively using PraisonAI Event Hooks."
    except Exception as e:
        final_body = f"❌ **PraisonAI Triager Failed**\n{run_url}\n\nError: {e}"

    # 5. Final Update
    try:
        fetch_github_api(f"{api_base}/issues/comments/{comment_id}", token=token, method="PATCH", data={"body": final_body})
        print(f"[green]✅ Final tracking comment updated![/green]")
    except:
        pass
