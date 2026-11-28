"""``praisonai steward``: read a pull request's state and pick the next action.

Read-only. Action priority follows Claude's PR steward: stop signals first
(``openship-stop`` label or ``@praisonai stop`` comment), then merge conflict,
then failing checks, then unanswered review threads, then ``@praisonai``
steering directives. Prior attempts recorded in PR comments hydrate the
circuit breaker across stateless CI (``--once``) runs.
"""

import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

_FAILED = {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE", "ERROR"}
_STOP_LABELS = frozenset({"openship-stop", "steward-stop"})
_SELF_CHECK_NAMES = frozenset({"openship/approvals", "openship/review"})
_SELF_CHECK_PREFIX = "OpenShip ("
_BOT_LOGINS = frozenset({"github-actions", "github-actions[bot]", "openship[bot]"})
_ATTEMPT_RE = re.compile(
    r"Steward (?:pushed `[^`]+` \([^,)]+, |attempted \()(?P<key>(?:conflict|check:[^)]+|thread:[^)]+|directive:[^)]+))\)"
)
_MENTION_RE = re.compile(r"(?:^|\s)@praisonai\b(.*)$", re.IGNORECASE | re.DOTALL)
_THREADS_QUERY = (
    "query($owner:String!,$name:String!,$number:Int!){viewer{login} repository(owner:$owner,name:$name)"
    "{pullRequest(number:$number){reviewThreads(first:100){nodes{id isResolved isOutdated path line "
    "comments(last:1){nodes{author{login} body}}}}}}}"
)
_THREADS_QUERY_NO_VIEWER = (
    "query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name)"
    "{pullRequest(number:$number){reviewThreads(first:100){nodes{id isResolved isOutdated path line "
    "comments(last:1){nodes{author{login} body}}}}}}}"
)


@dataclass
class Thread:
    id: str
    path: str
    line: Optional[int]
    author: str
    body: str


@dataclass
class PRState:
    number: int
    url: str
    state: str  # OPEN, MERGED, CLOSED
    mergeable: str  # MERGEABLE, CONFLICTING, UNKNOWN
    head: str
    base: str
    failing: List[str] = field(default_factory=list)
    threads: List[Thread] = field(default_factory=list)
    stopped: bool = False
    stop_reason: str = ""
    prior_attempts: Dict[str, int] = field(default_factory=dict)
    directives: List[Tuple[str, str]] = field(default_factory=list)  # (id, instruction)


@dataclass
class Action:
    kind: str  # stop, merge_base, fix_check, answer_thread, answer_directive, wait
    key: str = ""
    detail: str = ""


def _gh(run: Callable, *args: str) -> dict:
    return json.loads(run(["gh", *args], capture_output=True, text=True, check=True).stdout)


def _check_key(check: dict) -> Optional[str]:
    """Stable key for a CheckRun or StatusContext, prefixed with workflowName when present."""
    name = (check.get("name") or check.get("context") or "").strip()
    if not name:
        return None
    workflow = (check.get("workflowName") or "").strip()
    return f"{workflow}/{name}" if workflow else name


def _parse_pr_comments(comments: list) -> Tuple[bool, str, Dict[str, int], List[Tuple[str, str]]]:
    """Extract stop state, stateless CI attempt counts, and pending @praisonai directives."""
    stopped, stop_reason = False, ""
    attempts: Dict[str, int] = {}
    directives: List[Tuple[str, str]] = []
    for idx, item in enumerate(comments or []):
        if not isinstance(item, dict):
            continue
        body = (item.get("body") or "").strip()
        if not body:
            continue
        for match in _ATTEMPT_RE.finditer(body):
            key = match.group("key").strip()
            attempts[key] = attempts.get(key, 0) + 1
        # Ignore our own steward status comments when scanning for @praisonai commands
        if body.startswith("Steward "):
            continue
        mention = _MENTION_RE.search(body)
        if not mention:
            continue
        cmd = mention.group(1).strip()
        first = (cmd.split(None, 1)[0].lower() if cmd else "")
        if first in ("stop", "pause", "halt"):
            stopped, stop_reason = True, "stopped by @praisonai stop comment"
        elif first in ("resume", "start", "steward"):
            stopped, stop_reason = False, ""
        elif first == "review":
            # Owned by Pillar 1 (on-demand code review), not a PR Steward code-editing directive
            continue
        elif cmd:
            cid = str(item.get("id") or f"c{idx}")
            directives.append((cid, cmd))
    # Only keep directives that have not yet been attempted/handled
    pending = [(cid, txt) for cid, txt in directives if attempts.get(f"directive:{cid}", 0) == 0]
    return stopped, stop_reason, attempts, pending


def read_pr_state(pr: Optional[str] = None, run: Callable = subprocess.run) -> PRState:
    """Read the PR (the current branch's when ``pr`` is None) with ``gh``. Never writes."""
    view = _gh(
        run,
        "pr",
        "view",
        *([pr] if pr else []),
        "--json",
        "number,url,state,mergeable,headRefName,baseRefName,statusCheckRollup,labels,comments",
    )
    keys = [
        _check_key(c) for c in view.get("statusCheckRollup") or []
        if isinstance(c, dict) and (c.get("conclusion") or c.get("state")) in _FAILED
    ]
    failing = list(
        dict.fromkeys(
            k for k in keys
            if k and k not in _SELF_CHECK_NAMES and not k.startswith(_SELF_CHECK_PREFIX)
        )
    )
    labels = {
        (lb.get("name") or "").strip().lower()
        for lb in (view.get("labels") or [])
        if isinstance(lb, dict) and lb.get("name")
    }
    stopped, stop_reason, prior_attempts, directives = _parse_pr_comments(view.get("comments") or [])
    if hit := (labels & _STOP_LABELS):
        stopped = True
        stop_reason = f"stopped by '{sorted(hit)[0]}' label"

    # owner/name from the PR's own URL, not gh's {owner}/{repo} (the cwd repo), so a PR URL from another repo works.
    owner, name = view["url"].split("/")[3:5]
    gql_args = ("api", "graphql", "-F", f"owner={owner}", "-F", f"name={name}", "-F", f"number={view['number']}")
    proc = run(["gh", "api", "graphql", "-f", f"query={_THREADS_QUERY}", *gql_args[2:]], capture_output=True, text=True)
    data = None
    if proc.returncode == 0 and (proc.stdout or "").strip():
        parsed = json.loads(proc.stdout)
        if isinstance(parsed.get("data"), dict) and parsed["data"].get("repository"):
            data = parsed["data"]
    if data is None:
        # Installation tokens (GitHub Actions GITHUB_TOKEN) cannot query `viewer`; retry without `viewer`.
        data = _gh(run, "api", "graphql", "-f", f"query={_THREADS_QUERY_NO_VIEWER}", *gql_args[2:])["data"]
    viewer_login = ((data.get("viewer") or {}).get("login") or "").strip()
    skip_authors = ({viewer_login} if viewer_login else set(_BOT_LOGINS))
    threads = []
    for node in data["repository"]["pullRequest"]["reviewThreads"]["nodes"]:
        if not node["comments"]["nodes"]:
            continue
        last = node["comments"]["nodes"][-1]
        author = (last.get("author") or {}).get("login", "")
        last_body = (last.get("body") or "").strip()
        if not node["isResolved"] and not node["isOutdated"] and author not in skip_authors and not last_body.startswith("Steward "):
            threads.append(Thread(node["id"], node["path"], node.get("line"), author, last.get("body", "")))
    return PRState(
        view["number"],
        view["url"],
        view["state"],
        view["mergeable"],
        view["headRefName"],
        view["baseRefName"],
        failing,
        threads,
        stopped=stopped,
        stop_reason=stop_reason,
        prior_attempts=prior_attempts,
        directives=directives,
    )


def next_action(state: PRState, attempts: Dict[str, int], max_attempts: int = 3) -> Action:
    """The next thing to do, skipping items already tried ``max_attempts`` times."""
    if state.state != "OPEN":
        return Action("stop", detail=f"pull request is {state.state.lower()}")
    if state.stopped:
        return Action("stop", detail=state.stop_reason or "stopped by @praisonai stop")
    todo = [Action("merge_base", "conflict", f"merge {state.base} in")] if state.mergeable == "CONFLICTING" else []
    todo += [Action("fix_check", f"check:{name}", name) for name in state.failing]
    todo += [Action("answer_thread", f"thread:{t.id}", t.body) for t in state.threads]
    todo += [Action("answer_directive", f"directive:{cid}", txt) for cid, txt in state.directives]
    stuck = [a.key for a in todo if attempts.get(a.key, 0) >= max_attempts]
    for action in todo:
        if action.key not in stuck:
            return action
    return Action("wait", detail=f"gave up on: {', '.join(stuck)}" if stuck else "nothing to do")
