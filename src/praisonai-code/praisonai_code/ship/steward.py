"""``praisonai steward``: read a pull request's state and pick the next action.

Read-only. The action order follows Claude's PR steward: a merge conflict,
then failing checks, then unanswered review threads. Each item gets at most
``max_attempts`` tries, so a failure the agent cannot fix does not loop forever.
"""

import json
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

_FAILED = {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE", "ERROR"}
_THREADS_QUERY = (
    "query($owner:String!,$name:String!,$number:Int!){viewer{login} repository(owner:$owner,name:$name)"
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


@dataclass
class Action:
    kind: str  # stop, merge_base, fix_check, answer_thread, wait
    key: str = ""
    detail: str = ""


def _gh(run: Callable, *args: str) -> dict:
    return json.loads(run(["gh", *args], capture_output=True, text=True, check=True).stdout)


def read_pr_state(pr: Optional[str] = None, run: Callable = subprocess.run) -> PRState:
    """Read the PR (the current branch's when ``pr`` is None) with ``gh``. Never writes."""
    view = _gh(run, "pr", "view", *([pr] if pr else []), "--json",
               "number,url,state,mergeable,headRefName,baseRefName,statusCheckRollup")
    failing = list(dict.fromkeys(c.get("name") or c.get("context") for c in view.get("statusCheckRollup") or []
                                 if (c.get("conclusion") or c.get("state")) in _FAILED))
    # owner/name from the PR's own URL, not gh's {owner}/{repo} (the cwd repo), so a PR URL from another repo works.
    owner, name = view["url"].split("/")[3:5]
    data = _gh(run, "api", "graphql", "-f", f"query={_THREADS_QUERY}", "-F", f"owner={owner}",
               "-F", f"name={name}", "-F", f"number={view['number']}")["data"]
    me = data["viewer"]["login"]
    threads = []
    for node in data["repository"]["pullRequest"]["reviewThreads"]["nodes"]:
        if not node["comments"]["nodes"]:
            continue
        last = node["comments"]["nodes"][-1]
        author = (last.get("author") or {}).get("login", "")
        if not node["isResolved"] and not node["isOutdated"] and author != me:
            threads.append(Thread(node["id"], node["path"], node.get("line"), author, last.get("body", "")))
    return PRState(view["number"], view["url"], view["state"], view["mergeable"],
                   view["headRefName"], view["baseRefName"], failing, threads)


def next_action(state: PRState, attempts: Dict[str, int], max_attempts: int = 3) -> Action:
    """The next thing to do, skipping items already tried ``max_attempts`` times."""
    if state.state != "OPEN":
        return Action("stop", detail=f"pull request is {state.state.lower()}")
    todo = [Action("merge_base", "conflict", f"merge {state.base} in")] if state.mergeable == "CONFLICTING" else []
    todo += [Action("fix_check", f"check:{name}", name) for name in state.failing]
    todo += [Action("answer_thread", f"thread:{t.id}", t.body) for t in state.threads]
    stuck = [a.key for a in todo if attempts.get(a.key, 0) >= max_attempts]
    for action in todo:
        if action.key not in stuck:
            return action
    return Action("wait", detail=f"gave up on: {', '.join(stuck)}" if stuck else "nothing to do")
