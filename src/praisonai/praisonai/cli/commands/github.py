import os
import re
import sys
import json
import time
import threading
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any

import typer
from rich import print

app = typer.Typer(help="GitHub integration commands (triage, tracking).")


# ---------------------------------------------------------------------------
# GitHub REST helper
# ---------------------------------------------------------------------------

def fetch_github_api(url: str, token: Optional[str] = None, method: str = "GET", data: Optional[dict] = None) -> dict:
    """Minimal stdlib GitHub REST API wrapper."""
    req = urllib.request.Request(url, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(data).encode("utf-8")
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status == 204:
                return {}
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[red]GitHub API Error: {e.code} – {e.read().decode('utf-8')}[/red]")
        raise


# ---------------------------------------------------------------------------
# Sticky-comment state machine (mirrors Claude Code behaviour)
# ---------------------------------------------------------------------------

class StickyComment:
    """
    Manages the single live-updated GitHub comment.

    Lifecycle mirrors Claude Code:
      1. Posted immediately: spinner title + empty todo list
      2. On TodoWrite: replace todo list with agent's own items (with checkboxes)
      3. On tool_call_start / agent_start: mark current todo 🔄, update spinner
      4. On tool_call_end / agent_end:  mark completed todo ✅
      5. On finish: update title to ✅ / ❌, show result summary
    """

    SPINNER = "🔴"
    DONE    = "✅"
    FAIL    = "❌"
    WORKING = "🔄"

    def __init__(self, api_base: str, issue: int, token: str,
                 task_type: str, title: str, run_url: str,
                 repo_name: str = ""):
        self._api_base  = api_base
        self._issue     = issue
        self._token     = token
        self._task_type = task_type
        self._title     = title
        self._run_url   = run_url
        self._repo_name = repo_name
        self._comment_id: Optional[int] = None

        # Branch and PR tracking
        self._branch_name: Optional[str] = None
        self._pr_url: Optional[str] = None
        self._pr_number: Optional[int] = None
        self._summary_lines: List[str] = []

        # Todo list: list of dicts {content, status}  status ∈ pending/in_progress/completed
        self._todos: List[Dict[str, Any]] = []
        # Free-form activity log shown below the todo list (last N lines)
        self._logs: List[str] = []
        self._current_agent: Optional[str] = None
        self._current_tool:  Optional[str] = None

        # Throttle: max one GitHub PATCH per 3 s
        self._last_push = 0.0
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        # Populated by _load_yaml_steps_as_todos: role_name.lower() -> step index
        self._step_agent_map: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def post_initial(self) -> None:
        """Create the initial 'working…' comment and remember its ID."""
        body = self._build_body()
        resp = fetch_github_api(
            f"{self._api_base}/issues/{self._issue}/comments",
            token=self._token, method="POST", data={"body": body},
        )
        self._comment_id = resp["id"]
        print(f"[green]✅ Tracking comment created (id={self._comment_id})[/green]")

    def set_todos(self, todos: List[Dict[str, Any]]) -> None:
        """Called when agent emits a TodoWrite with its plan."""
        with self._lock:
            self._todos = [
                {"content": t.get("content", ""), "status": t.get("status", "pending")}
                for t in todos
            ]
            self._logs.append("📋 Todo list created")
        self._schedule_push()

    def update_todo_statuses(self, todos: List[Dict[str, Any]]) -> None:
        """Called on every subsequent TodoWrite (status updates)."""
        with self._lock:
            content_map = {t["content"]: t["status"] for t in todos if "content" in t}
            for item in self._todos:
                new_status = content_map.get(item["content"])
                if new_status:
                    item["status"] = new_status
        self._schedule_push()

    def on_agent_start(self, agent_name: str) -> None:
        with self._lock:
            self._current_agent = agent_name
            self._logs.append(f"🤖 Agent starting: **{agent_name}**")
            # Mark matching step as in_progress
            idx = self._step_agent_map.get(agent_name.lower())
            if idx is not None and idx < len(self._todos):
                for t in self._todos:
                    if t["status"] == "in_progress":
                        t["status"] = "completed"
                self._todos[idx]["status"] = "in_progress"
        self._schedule_push()

    def on_agent_end(self, agent_name: str) -> None:
        with self._lock:
            self._logs.append(f"✅ Agent completed: **{agent_name}**")
            self._current_agent = None
            # Mark matching step as completed
            idx = self._step_agent_map.get(agent_name.lower())
            if idx is not None and idx < len(self._todos):
                self._todos[idx]["status"] = "completed"
                # Mark next step as in_progress if it exists
                if idx + 1 < len(self._todos) and self._todos[idx + 1]["status"] == "pending":
                    self._todos[idx + 1]["status"] = "in_progress"
        self._schedule_push()

    def on_tool_start(self, agent_name: str, tool_name: str, tool_args: dict) -> None:
        with self._lock:
            self._current_tool = tool_name
            label = self._tool_label(tool_name, tool_args)
            self._logs.append(f"🔧 {label}")
        self._schedule_push()

    def on_tool_end(self, agent_name: str, tool_name: str) -> None:
        with self._lock:
            self._current_tool = None
        # no extra log for tool end – keeps comment clean

    def set_branch(self, branch_name: str) -> None:
        """Called when a branch is successfully created."""
        with self._lock:
            self._branch_name = branch_name
        self._schedule_push()

    def set_pr(self, pr_url: str, pr_number: Optional[int] = None) -> None:
        """Called when a PR is explicitly created."""
        with self._lock:
            self._pr_url = pr_url
            self._pr_number = pr_number
        self._schedule_push()

    def add_summary_line(self, line: str) -> None:
        """Append a line to the Summary section."""
        with self._lock:
            self._summary_lines.append(line)
        self._schedule_push()

    def finalize(self, success: bool, summary: str) -> None:
        """Push the final state synchronously."""
        if self._timer:
            self._timer.cancel()
            self._timer = None
        with self._lock:
            # Mark all in_progress todos as completed
            for t in self._todos:
                if t["status"] == "in_progress":
                    t["status"] = "completed"
            if summary:
                self._summary_lines.append(summary)
        self._push_now(final=success)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tool_label(tool_name: str, tool_args: dict) -> str:
        """Human-readable one-liner for a tool call."""
        if tool_name == "execute_command":
            cmd = tool_args.get("command", "")
            return f"`{cmd[:80]}`" if cmd else "Running command"
        if tool_name in ("github_create_branch",):
            return f"Creating branch `{tool_args.get('branch_name', '')}`"
        if tool_name in ("github_commit_and_push",):
            return f"Committing: {tool_args.get('commit_message', '')[:60]}"
        if tool_name in ("github_create_pull_request",):
            return f"Opening PR: {tool_args.get('title', '')[:60]}"
        # Generic
        first_val = next(iter(tool_args.values()), "") if tool_args else ""
        if isinstance(first_val, str) and first_val:
            return f"`{tool_name}` – {first_val[:60]}"
        return f"`{tool_name}`"

    def _build_body(self, final: Optional[bool] = None) -> str:
        """Render the full Markdown comment body (Claude Code style)."""
        if final is True:
            status_icon = self.DONE
            verb = "finished"
        elif final is False:
            status_icon = self.FAIL
            verb = "failed on"
        else:
            status_icon = self.SPINNER
            verb = "is working on"

        lines: List[str] = []

        # --- Header line (Claude Code style) ---
        meta_parts: List[str] = []
        if self._run_url:
            meta_parts.append(f"[View job]({self._run_url})")
        if self._branch_name and self._repo_name:
            branch_url = f"https://github.com/{self._repo_name}/tree/{self._branch_name}"
            meta_parts.append(f"[`{self._branch_name}`]({branch_url})")
            if self._pr_url:
                meta_parts.append(f"[View PR →]({self._pr_url})")
            else:
                compare_url = f"https://github.com/{self._repo_name}/compare/main...{self._branch_name}?quick_pull=1"
                meta_parts.append(f"[Create PR →]({compare_url})")

        header = f"**PraisonAI {verb} #{self._issue}** {status_icon}"
        lines.append(" · ".join([header] + meta_parts) if meta_parts else header)
        lines.append("")
        lines.append(f"**{self._task_type} #{self._issue}: {self._title}**")
        lines.append("")

        # --- Todo list ---
        if self._todos:
            lines.append("**Todo List**")
            lines.append("")
            for t in self._todos:
                s = t["status"]
                box = "- [x]" if s == "completed" else "- [ ]"
                content = t["content"]
                if s == "in_progress":
                    content = f"{content} 🔄"
                lines.append(f"{box} {content}")
            lines.append("")

        # --- Summary section ---
        if self._summary_lines:
            lines.append("**Summary**")
            lines.append("")
            for entry in self._summary_lines[-10:]:
                lines.append(f"{entry}")
            lines.append("")

        # --- Activity log (only while running, last 8 items) ---
        if final is None and self._logs:
            lines.append("**Activity**")
            lines.append("")
            for entry in self._logs[-8:]:
                lines.append(f"- {entry}")

        return "\n".join(lines)

    def _push_now(self, final: Optional[bool] = None) -> None:
        if self._comment_id is None:
            return
        body = self._build_body(final=final)
        try:
            fetch_github_api(
                f"{self._api_base}/issues/comments/{self._comment_id}",
                token=self._token, method="PATCH", data={"body": body},
            )
        except Exception:
            pass
        self._last_push = time.time()

    def _schedule_push(self) -> None:
        with self._lock:
            if self._timer is not None:
                return  # already scheduled
            elapsed = time.time() - self._last_push
            delay = max(0.0, 3.0 - elapsed)
            self._timer = threading.Timer(delay, self._deferred_push)
            self._timer.daemon = True
            self._timer.start()

    def _deferred_push(self) -> None:
        with self._lock:
            self._timer = None
        self._push_now()


# ---------------------------------------------------------------------------
# ContextTraceEmitter sink that feeds StickyComment
# ---------------------------------------------------------------------------

def _make_context_sink(sticky: StickyComment):
    """Return a ContextTraceSinkProtocol that routes events to the StickyComment."""
    try:
        from praisonaiagents.trace.context_events import ContextTraceSinkProtocol
    except ImportError:
        return None

    class GithubContextSink(ContextTraceSinkProtocol):
        def emit(self, event) -> None:
            try:
                et = event.event_type
                et_val = et.value if hasattr(et, "value") else str(et)
                data = event.data or {}

                if et_val == "agent_start":
                    sticky.on_agent_start(event.agent_name or "agent")

                elif et_val == "agent_end":
                    sticky.on_agent_end(event.agent_name or "agent")

                elif et_val == "tool_call_start":
                    tool_name = data.get("tool_name", "")
                    tool_args = data.get("tool_args") or {}
                    agent_name = event.agent_name or ""

                    if tool_name == "TodoWrite":
                        todos = tool_args.get("todos", [])
                        if todos:
                            if sticky._todos:
                                sticky.update_todo_statuses(todos)
                            else:
                                sticky.set_todos(todos)
                    else:
                        sticky.on_tool_start(agent_name, tool_name, tool_args)
                        # Capture branch name eagerly from args
                        if tool_name == "github_create_branch":
                            bn = tool_args.get("branch_name", "")
                            if bn:
                                sticky.set_branch(bn)

                elif et_val == "tool_call_end":
                    tool_name = data.get("tool_name", "")
                    tool_result = data.get("result") or data.get("tool_result") or {}
                    result_str = str(tool_result)
                    if tool_name != "TodoWrite":
                        sticky.on_tool_end(event.agent_name or "", tool_name)
                    # Capture branch from push result (fallback)
                    if tool_name == "github_commit_and_push" and not sticky._branch_name:
                        m = re.search(r"branch '([^']+)'", result_str)
                        if m:
                            sticky.set_branch(m.group(1))
                    # Capture PR URL only when explicitly created
                    if tool_name == "github_create_pull_request":
                        m = re.search(r'https://github\.com/[^\s"\)]+/pull/\d+', result_str)
                        if m:
                            pr_url = m.group(0)
                            pr_num = re.search(r'/pull/(\d+)', pr_url)
                            sticky.set_pr(pr_url, int(pr_num.group(1)) if pr_num else None)
                        if isinstance(tool_result, dict):
                            url = tool_result.get("url") or tool_result.get("html_url", "")
                            if url and "/pull/" in url:
                                pr_num = re.search(r'/pull/(\d+)', url)
                                sticky.set_pr(url, int(pr_num.group(1)) if pr_num else None)

            except Exception:
                pass

        def flush(self) -> None:
            pass

        def close(self) -> None:
            pass

    return GithubContextSink()


# ---------------------------------------------------------------------------
# YAML step → todo pre-loader
# ---------------------------------------------------------------------------

def _load_yaml_steps_as_todos(agent_file: str, sticky: StickyComment) -> None:
    """Parse the agent YAML and populate todos from step names/agents."""
    try:
        import yaml  # type: ignore
    except ImportError:
        return
    try:
        with open(agent_file) as f:
            cfg = yaml.safe_load(f)
    except Exception:
        return
    if not isinstance(cfg, dict):
        return

    steps = cfg.get("steps", [])
    roles = cfg.get("roles", {})
    if not steps:
        return

    todos = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        # Prefer explicit step name; fall back to role display name or agent key
        step_name = step.get("name", "")
        agent_key = step.get("agent", "")
        if not step_name and agent_key:
            role_cfg = roles.get(agent_key, {})
            step_name = role_cfg.get("role", agent_key).title()
        if step_name:
            # Humanize snake_case → Title Case
            human_name = step_name.replace("_", " ").title()
            todos.append({"content": human_name, "status": "pending"})

    if todos:
        # Mark first as in_progress
        todos[0]["status"] = "in_progress"
        with sticky._lock:
            sticky._todos = todos

    # Build a reverse map: role name / step name / agent key → step index
    sticky._step_agent_map = {}
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        agent_key = step.get("agent", "")
        step_name = step.get("name", "")
        role_cfg = roles.get(agent_key, {})
        role_name = role_cfg.get("role", agent_key)
        for name in (role_name, step_name, agent_key):
            if name:
                sticky._step_agent_map[name.lower()] = i


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

@app.command("triage")
def github_triage(
    issue: int = typer.Option(..., help="Issue or PR number to triage"),
    repo: Optional[str] = typer.Option(None, help="Repository (owner/repo). Defaults to GITHUB_REPOSITORY env var."),
    agent_file: str = typer.Option("agents.yaml", help="Path to the agents YAML file to run."),
):
    """Triage a GitHub Issue/PR with live sticky-comment tracking."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("[red]Error: GITHUB_TOKEN or GH_TOKEN environment variable required.[/red]")
        raise typer.Exit(1)

    repo_name = repo or os.environ.get("GITHUB_REPOSITORY")
    if not repo_name:
        print("[red]Error: --repo must be provided if GITHUB_REPOSITORY is not set.[/red]")
        raise typer.Exit(1)

    print(f"[cyan]🚀 PraisonAI triage for {repo_name}#{issue}…[/cyan]")

    # ------------------------------------------------------------------
    # 1. Fetch issue / PR context
    # ------------------------------------------------------------------
    api_base = f"https://api.github.com/repos/{repo_name}"
    issue_data = fetch_github_api(f"{api_base}/issues/{issue}", token=token)

    is_pr    = "pull_request" in issue_data
    task_type = "Pull Request" if is_pr else "Issue"
    ctx_title = issue_data.get("title", f"#{issue}")

    context_md = f"# GitHub {task_type} #{issue}: {ctx_title}\n\n{issue_data.get('body', '')}\n"

    if is_pr:
        print("[yellow]Detected Pull Request – fetching diff…[/yellow]")
        pr_req = urllib.request.Request(f"{api_base}/pulls/{issue}", method="GET")
        pr_req.add_header("Accept", "application/vnd.github.v3.diff")
        pr_req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(pr_req) as r:
                diff_text = r.read().decode("utf-8")
                context_md += f"\n## Code Diff\n```diff\n{diff_text[:20000]}\n```"
        except urllib.error.HTTPError:
            pass

    os.makedirs(".github", exist_ok=True)
    with open(".github/triage-context.md", "w") as f:
        f.write(context_md)
    print("[green]✅ Context saved to .github/triage-context.md[/green]")

    # ------------------------------------------------------------------
    # 2. Build run URL and post the initial sticky comment
    # ------------------------------------------------------------------
    run_url = ""
    if os.environ.get("GITHUB_RUN_ID"):
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        run_url = f"{server}/{repo_name}/actions/runs/{os.environ['GITHUB_RUN_ID']}"

    sticky = StickyComment(
        api_base=api_base, issue=issue, token=token,
        task_type=task_type, title=ctx_title, run_url=run_url,
        repo_name=repo_name,
    )
    sticky._logs.append(f"Context fetched for {task_type} #{issue}")

    # Pre-populate todo list from YAML steps
    _load_yaml_steps_as_todos(agent_file, sticky)

    sticky.post_initial()

    # ------------------------------------------------------------------
    # 3. Wire ContextTraceEmitter sink
    # ------------------------------------------------------------------
    ctx_token = None
    try:
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter,
            set_context_emitter,
        )
        sink = _make_context_sink(sticky)
        if sink is not None:
            emitter = ContextTraceEmitter(sink=sink, session_id=f"github-triage-{issue}", enabled=True)
            ctx_token = set_context_emitter(emitter)
            print("[green]✅ Live trace sink registered[/green]")
    except Exception as exc:
        print(f"[yellow]Warning: could not register trace sink: {exc}[/yellow]")

    # ------------------------------------------------------------------
    # 4. Run the agent workflow
    # ------------------------------------------------------------------
    print(f"[cyan]▶️  Running agent file: {agent_file}[/cyan]")
    success = True
    error_msg = ""
    try:
        from praisonai.cli.main import PraisonAI

        original_argv = sys.argv[:]
        sys.argv = ["praisonai", "workflow", "run", agent_file, "--var", f"ISSUE_NUMBER={issue}"]
        if os.environ.get("PRAISONAI_AUTO_APPROVE", "").lower() in ("true", "1", "yes"):
            sys.argv.append("--trust")
        try:
            PraisonAI().main()
        except SystemExit:
            pass
        finally:
            sys.argv = original_argv

    except Exception as exc:
        success = False
        error_msg = str(exc)
        print(f"[red]Agent run failed: {exc}[/red]")

    # ------------------------------------------------------------------
    # 5. Restore context emitter and finalise comment
    # ------------------------------------------------------------------
    if ctx_token is not None:
        try:
            from praisonaiagents.trace.context_events import reset_context_emitter
            reset_context_emitter(ctx_token)
        except Exception:
            pass

    if success:
        summary = f"✅ Completed – {task_type} #{issue} triaged successfully."
    else:
        summary = f"❌ Failed – {error_msg[:200]}"

    sticky.finalize(success=success, summary=summary)
    print("[green]✅ Final sticky comment updated.[/green]")
