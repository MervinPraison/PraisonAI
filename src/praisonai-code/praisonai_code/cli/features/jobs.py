"""
Jobs CLI Feature for PraisonAI.

Provides CLI commands for managing async jobs.

Commands:
- praisonai run submit <prompt>     # Submit a new job
- praisonai run status <job_id>     # Get job status
- praisonai run result <job_id>     # Get job result
- praisonai run cancel <job_id>     # Cancel a job
- praisonai run list                # List jobs
"""

import sys
import json
import time
from typing import Optional, List


class JobsHandler:
    """
    Handler for jobs CLI commands.
    
    Provides functionality to:
    - Submit jobs to the API
    - Check job status
    - Get job results
    - Cancel jobs
    - List jobs
    """
    
    def __init__(
        self,
        api_url: str = "http://127.0.0.1:8005",
        verbose: bool = False
    ):
        self.api_url = api_url.rstrip("/")
        self.verbose = verbose
    
    @property
    def feature_name(self) -> str:
        return "jobs"
    
    def _get_client(self):
        """Get HTTP client."""
        try:
            import httpx
            return httpx.Client(timeout=30.0)
        except ImportError:
            raise RuntimeError("httpx is required. Install with: pip install httpx")
    
    def submit(
        self,
        prompt: str,
        agent_file: Optional[str] = None,
        recipe_name: Optional[str] = None,
        recipe_config: Optional[dict] = None,
        framework: str = "praisonai",
        timeout: int = 3600,
        wait: bool = False,
        poll_interval: int = 5,
        idempotency_key: Optional[str] = None,
        idempotency_scope: str = "none",
        webhook_url: Optional[str] = None,
        session_id: Optional[str] = None,
        output_json: bool = False
    ) -> dict:
        """
        Submit a new job.
        
        Args:
            prompt: The prompt/task for the agent
            agent_file: Optional path to agents.yaml
            recipe_name: Optional recipe name (mutually exclusive with agent_file)
            recipe_config: Optional recipe configuration overrides
            framework: Framework to use
            timeout: Job timeout in seconds
            wait: If True, wait for completion
            poll_interval: Seconds between status polls
            idempotency_key: Key for deduplication
            idempotency_scope: Scope for deduplication (none, session, global)
            webhook_url: URL for completion webhook
            session_id: Session ID for conversation continuity
            output_json: If True, output JSON format
            
        Returns:
            Job submission response
        """
        # Validate mutually exclusive options
        if agent_file and recipe_name:
            raise ValueError("Cannot specify both --agent-file and --recipe. Choose one.")
        
        client = self._get_client()
        
        payload = {
            "prompt": prompt,
            "framework": framework,
            "timeout": timeout
        }
        
        if agent_file:
            payload["agent_file"] = agent_file
        if recipe_name:
            payload["recipe_name"] = recipe_name
        if recipe_config:
            payload["recipe_config"] = recipe_config
        if webhook_url:
            payload["webhook_url"] = webhook_url
        if session_id:
            payload["session_id"] = session_id
        if idempotency_key:
            payload["idempotency_key"] = idempotency_key
        if idempotency_scope and idempotency_scope != "none":
            payload["idempotency_scope"] = idempotency_scope
        
        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        
        try:
            response = client.post(
                f"{self.api_url}/api/v1/runs",
                json=payload,
                headers=headers if headers else None
            )
            response.raise_for_status()
            result = response.json()
            
            if output_json:
                print(json.dumps(result, indent=2))
            else:
                self._print_success(f"Job submitted: {result['job_id']}")
                self._print_info(f"Status URL: {result['poll_url']}")
            
            if wait:
                return self._wait_for_completion(result['job_id'], poll_interval, output_json)
            
            return result
            
        except Exception as e:
            self._print_error(f"Failed to submit job: {e}")
            raise
    
    def status(self, job_id: str) -> dict:
        """
        Get job status.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job status response
        """
        client = self._get_client()
        
        try:
            response = client.get(f"{self.api_url}/api/v1/runs/{job_id}")
            response.raise_for_status()
            result = response.json()
            
            self._print_job_status(result)
            return result
            
        except Exception as e:
            self._print_error(f"Failed to get status: {e}")
            raise
    
    def result(self, job_id: str) -> dict:
        """
        Get job result.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job result response
        """
        client = self._get_client()
        
        try:
            response = client.get(f"{self.api_url}/api/v1/runs/{job_id}/result")
            response.raise_for_status()
            result = response.json()
            
            self._print_job_result(result)
            return result
            
        except Exception as e:
            self._print_error(f"Failed to get result: {e}")
            raise
    
    def cancel(self, job_id: str) -> dict:
        """
        Cancel a job.
        
        Args:
            job_id: Job ID
            
        Returns:
            Updated job status
        """
        client = self._get_client()
        
        try:
            response = client.post(f"{self.api_url}/api/v1/runs/{job_id}/cancel")
            response.raise_for_status()
            result = response.json()
            
            self._print_success(f"Job cancelled: {job_id}")
            return result
            
        except Exception as e:
            self._print_error(f"Failed to cancel job: {e}")
            raise
    
    def list_jobs(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> dict:
        """
        List jobs.
        
        Args:
            status: Optional status filter
            page: Page number
            page_size: Jobs per page
            
        Returns:
            Job list response
        """
        client = self._get_client()
        
        params = {"page": page, "page_size": page_size}
        if status:
            params["status"] = status
        
        try:
            response = client.get(
                f"{self.api_url}/api/v1/runs",
                params=params
            )
            response.raise_for_status()
            result = response.json()
            
            self._print_job_list(result)
            return result
            
        except Exception as e:
            self._print_error(f"Failed to list jobs: {e}")
            raise
    
    def _wait_for_completion(self, job_id: str, poll_interval: int = 5, output_json: bool = False) -> dict:
        """Wait for a job to complete."""
        client = self._get_client()
        
        if not output_json:
            self._print_info("Waiting for job completion...")
        
        while True:
            try:
                response = client.get(f"{self.api_url}/api/v1/runs/{job_id}")
                response.raise_for_status()
                result = response.json()
                
                status = result.get("status")
                progress = result.get("progress", {}).get("percentage", 0)
                
                if not output_json:
                    self._print_progress(status, progress)
                
                if status in ("succeeded", "failed", "cancelled"):
                    if output_json:
                        # Get full result for succeeded jobs
                        if status == "succeeded":
                            res = client.get(f"{self.api_url}/api/v1/runs/{job_id}/result")
                            res.raise_for_status()
                            print(json.dumps(res.json(), indent=2))
                        else:
                            print(json.dumps(result, indent=2))
                        return result
                    else:
                        if status == "succeeded":
                            return self.result(job_id)
                        else:
                            return result
                
                # Honor Retry-After header if present
                retry_after = result.get("retry_after") or poll_interval
                time.sleep(retry_after)
                
            except KeyboardInterrupt:
                if not output_json:
                    self._print_info("\nInterrupted. Job continues running in background.")
                return result
            except Exception as e:
                if not output_json:
                    self._print_error(f"Error polling status: {e}")
                time.sleep(poll_interval)
    
    def stream(self, job_id: str, output_json: bool = False) -> None:
        """
        Stream job progress via SSE.
        
        Args:
            job_id: Job ID
            output_json: If True, output raw JSON events
        """
        try:
            import httpx
            
            with httpx.stream(
                "GET",
                f"{self.api_url}/api/v1/runs/{job_id}/stream",
                timeout=None
            ) as response:
                response.raise_for_status()
                
                for line in response.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data == "[DONE]":
                            if not output_json:
                                self._print_success("Stream completed")
                            break
                        try:
                            event = json.loads(data)
                            if output_json:
                                print(json.dumps(event))
                            else:
                                event_type = event.get("event", "unknown")
                                if event_type == "progress":
                                    pct = event.get("data", {}).get("percentage", 0)
                                    step = event.get("data", {}).get("current_step", "")
                                    self._print_progress(f"{step}", pct)
                                elif event_type == "complete":
                                    status = event.get("data", {}).get("status", "")
                                    if status == "succeeded":
                                        self._print_success(f"Job completed: {status}")
                                    else:
                                        self._print_error(f"Job ended: {status}")
                                elif event_type == "error":
                                    self._print_error(event.get("data", {}).get("error", "Unknown error"))
                        except json.JSONDecodeError:
                            if not output_json:
                                print(data)
                    elif line.startswith(":"):
                        # Heartbeat comment, ignore
                        pass
                        
        except Exception as e:
            self._print_error(f"Stream error: {e}")
            raise
    
    def _print_job_status(self, job: dict):
        """Print job status."""
        try:
            from rich.console import Console
            from rich.panel import Panel
            
            console = Console()
            
            status = job.get("status", "unknown")
            status_color = {
                "queued": "dim",
                "running": "yellow",
                "succeeded": "green",
                "failed": "red",
                "cancelled": "dim"
            }.get(status, "white")
            
            progress = job.get("progress", {})
            
            content = f"""
[bold]Job ID:[/bold] {job.get('job_id')}
[bold]Status:[/bold] [{status_color}]{status}[/{status_color}]
[bold]Progress:[/bold] {progress.get('percentage', 0):.0f}%
[bold]Step:[/bold] {progress.get('current_step') or '-'}
[bold]Created:[/bold] {job.get('created_at')}
[bold]Started:[/bold] {job.get('started_at') or '-'}
"""
            if job.get("error"):
                content += f"[bold]Error:[/bold] [red]{job.get('error')}[/red]\n"
            
            console.print(Panel(content.strip(), title="Job Status"))
        except ImportError:
            print(f"Job: {job.get('job_id')}")
            print(f"  Status: {job.get('status')}")
            print(f"  Progress: {job.get('progress', {}).get('percentage', 0):.0f}%")
    
    def _print_job_result(self, job: dict):
        """Print job result."""
        try:
            from rich.console import Console
            from rich.panel import Panel
            from rich.markdown import Markdown
            
            console = Console()
            
            status = job.get("status")
            
            if status == "succeeded":
                result = job.get("result", "")
                if isinstance(result, str):
                    console.print(Panel(Markdown(result), title="Result"))
                else:
                    console.print(Panel(json.dumps(result, indent=2), title="Result"))
            else:
                console.print(f"[red]Job {status}: {job.get('error')}[/red]")
                
        except ImportError:
            print(f"Result: {job.get('result')}")
    
    def _print_job_list(self, response: dict):
        """Print job list."""
        try:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            jobs = response.get("jobs", [])
            
            if not jobs:
                console.print("[yellow]No jobs found[/yellow]")
                return
            
            table = Table(title=f"Jobs (Page {response.get('page')}/{(response.get('total', 0) + response.get('page_size', 20) - 1) // response.get('page_size', 20)})")
            table.add_column("ID", style="cyan")
            table.add_column("Status", style="yellow")
            table.add_column("Progress", style="blue")
            table.add_column("Created", style="dim")
            
            for job in jobs:
                status = job.get("status", "unknown")
                status_color = {
                    "queued": "dim",
                    "running": "yellow",
                    "succeeded": "green",
                    "failed": "red",
                    "cancelled": "dim"
                }.get(status, "white")
                
                progress = job.get("progress", {}).get("percentage", 0)
                
                table.add_row(
                    job.get("job_id", "?"),
                    f"[{status_color}]{status}[/{status_color}]",
                    f"{progress:.0f}%",
                    job.get("created_at", "")[:19]
                )
            
            console.print(table)
            console.print(f"Total: {response.get('total', 0)} jobs")
            
        except ImportError:
            print("Jobs:")
            for job in response.get("jobs", []):
                print(f"  {job.get('job_id')} - {job.get('status')}")
    
    def _print_progress(self, status: str, percentage: float):
        """Print progress update."""
        try:
            from rich.console import Console
            console = Console()
            console.print(f"  Status: {status} | Progress: {percentage:.0f}%", end="\r")
        except ImportError:
            print(f"  Status: {status} | Progress: {percentage:.0f}%", end="\r")
    
    def _print_success(self, message: str):
        """Print success message."""
        try:
            from rich.console import Console
            Console().print(f"[green]✓[/green] {message}")
        except ImportError:
            print(f"✓ {message}")
    
    def _print_error(self, message: str):
        """Print error message."""
        try:
            from rich.console import Console
            Console().print(f"[red]✗[/red] {message}")
        except ImportError:
            print(f"✗ {message}")
    
    def _print_info(self, message: str):
        """Print info message."""
        try:
            from rich.console import Console
            Console().print(f"[blue]ℹ[/blue] {message}")
        except ImportError:
            print(f"ℹ {message}")


def handle_run_command(args: List[str], verbose: bool = False):
    """
    Handle run CLI commands.
    
    Usage:
        praisonai run submit "Your prompt here" [--wait] [--agent-file agents.yaml]
        praisonai run status <job_id>
        praisonai run result <job_id>
        praisonai run cancel <job_id>
        praisonai run list [--status <status>]
    """
    import argparse
    
    parser = argparse.ArgumentParser(prog="praisonai run", description="Manage async jobs")
    subparsers = parser.add_subparsers(dest="subcommand", help="Available commands")
    
    # Submit command
    submit_parser = subparsers.add_parser("submit", help="Submit a new job")
    submit_parser.add_argument("prompt", help="The prompt/task for the agent")
    submit_parser.add_argument("--agent-file", help="Path to agents.yaml")
    submit_parser.add_argument("--recipe", dest="recipe_name", help="Recipe name to execute (mutually exclusive with --agent-file)")
    submit_parser.add_argument("--recipe-config", help="Recipe config as JSON string")
    submit_parser.add_argument("--framework", default="praisonai", help="Framework to use")
    submit_parser.add_argument("--timeout", type=int, default=3600, help="Timeout in seconds")
    submit_parser.add_argument("--wait", action="store_true", help="Wait for completion")
    submit_parser.add_argument("--stream", action="store_true", help="Stream job progress after submission")
    submit_parser.add_argument("--idempotency-key", help="Idempotency key to prevent duplicates")
    submit_parser.add_argument("--idempotency-scope", default="none", choices=["none", "session", "global"], help="Idempotency scope")
    submit_parser.add_argument("--webhook-url", help="Webhook URL for completion callback")
    submit_parser.add_argument("--session-id", help="Session ID for grouping jobs")
    submit_parser.add_argument("--metadata", action="append", metavar="KEY=VALUE", help="Custom metadata (can be used multiple times)")
    submit_parser.add_argument("--json", dest="output_json", action="store_true", help="Output JSON for scripting")
    submit_parser.add_argument("--api-url", default="http://127.0.0.1:8005", help="API server URL")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Get job status")
    status_parser.add_argument("job_id", help="Job ID")
    status_parser.add_argument("--json", dest="output_json", action="store_true", help="Output JSON")
    status_parser.add_argument("--api-url", default="http://127.0.0.1:8005", help="API server URL")
    
    # Result command
    result_parser = subparsers.add_parser("result", help="Get job result")
    result_parser.add_argument("job_id", help="Job ID")
    result_parser.add_argument("--json", dest="output_json", action="store_true", help="Output JSON")
    result_parser.add_argument("--api-url", default="http://127.0.0.1:8005", help="API server URL")
    
    # Cancel command
    cancel_parser = subparsers.add_parser("cancel", help="Cancel a job")
    cancel_parser.add_argument("job_id", help="Job ID")
    cancel_parser.add_argument("--json", dest="output_json", action="store_true", help="Output JSON")
    cancel_parser.add_argument("--api-url", default="http://127.0.0.1:8005", help="API server URL")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List jobs")
    list_parser.add_argument("--status", help="Filter by status")
    list_parser.add_argument("--page", type=int, default=1, help="Page number")
    list_parser.add_argument("--page-size", type=int, default=20, help="Jobs per page")
    list_parser.add_argument("--json", dest="output_json", action="store_true", help="Output JSON")
    list_parser.add_argument("--api-url", default="http://127.0.0.1:8005", help="API server URL")
    
    # Stream command
    stream_parser = subparsers.add_parser("stream", help="Stream job progress via SSE")
    stream_parser.add_argument("job_id", help="Job ID")
    stream_parser.add_argument("--json", dest="output_json", action="store_true", help="Output raw JSON events")
    stream_parser.add_argument("--api-url", default="http://127.0.0.1:8005", help="API server URL")
    
    if not args:
        parser.print_help()
        return
    
    parsed = parser.parse_args(args)
    
    if not parsed.subcommand:
        parser.print_help()
        return
    
    handler = JobsHandler(
        api_url=getattr(parsed, "api_url", "http://127.0.0.1:8005"),
        verbose=verbose
    )
    
    try:
        if parsed.subcommand == "submit":
            # Parse recipe config if provided
            recipe_config = None
            if getattr(parsed, "recipe_config", None):
                try:
                    recipe_config = json.loads(parsed.recipe_config)
                except json.JSONDecodeError:
                    print("Error: --recipe-config must be valid JSON")
                    sys.exit(1)
            
            handler.submit(
                prompt=parsed.prompt,
                agent_file=parsed.agent_file,
                recipe_name=getattr(parsed, "recipe_name", None),
                recipe_config=recipe_config,
                framework=parsed.framework,
                timeout=parsed.timeout,
                wait=parsed.wait,
                idempotency_key=getattr(parsed, "idempotency_key", None),
                idempotency_scope=getattr(parsed, "idempotency_scope", "none"),
                webhook_url=getattr(parsed, "webhook_url", None),
                session_id=getattr(parsed, "session_id", None),
                output_json=getattr(parsed, "output_json", False)
            )
        elif parsed.subcommand == "status":
            result = handler.status(parsed.job_id)
            if getattr(parsed, "output_json", False):
                print(json.dumps(result, indent=2))
        elif parsed.subcommand == "result":
            result = handler.result(parsed.job_id)
            if getattr(parsed, "output_json", False):
                print(json.dumps(result, indent=2))
        elif parsed.subcommand == "cancel":
            result = handler.cancel(parsed.job_id)
            if getattr(parsed, "output_json", False):
                print(json.dumps(result, indent=2))
        elif parsed.subcommand == "list":
            result = handler.list_jobs(
                status=parsed.status,
                page=parsed.page,
                page_size=parsed.page_size
            )
            if getattr(parsed, "output_json", False):
                print(json.dumps(result, indent=2))
        elif parsed.subcommand == "stream":
            handler.stream(
                job_id=parsed.job_id,
                output_json=getattr(parsed, "output_json", False)
            )
    except Exception:
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
