"""``praisonai ship`` (S-7): declarative PR approvals engine for ``.praisonai/approvals.yml``."""

import json, re, subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, List, Optional
import yaml
from praisonai_code.ship.flow import ShipRefused

DEFAULT_PROTECTED = (".praisonai/approvals.yml", ".github/workflows/**")
_POLICY_FILE = ".praisonai/approvals.yml"
_COMMENT_MARKER = "<!-- openship-approvals -->"
_ISSUE_COMMENT_ID_RE = re.compile(r"#issuecomment-(\d+)$")
_GLOB_TOK = re.compile(r"\*\*/|/\*\*|\*\*|\*|\?|[^*?]+")
_GLOB_MAP = {"**/": "(?:.*/)?", "/**": "/.*", "**": ".*", "*": "[^/]*", "?": "[^/]"}
@dataclass
class ApprovalRule:
    name: str
    paths: List[str] = field(default_factory=list)
    seats: int = 1
    reviewers: List[str] = field(default_factory=list)
    checks: List[str] = field(default_factory=list)
@dataclass
class ApprovalPolicy:
    mode: str = "observe"
    protected_paths: List[str] = field(default_factory=lambda: list(DEFAULT_PROTECTED))
    rules: List[ApprovalRule] = field(default_factory=list)
@dataclass
class RuleVerdict:
    rule: str
    passed: bool
    reasons: List[str] = field(default_factory=list)
@dataclass
class PolicyReport:
    passed: bool
    mode: str
    protected_touched: List[str] = field(default_factory=list)
    verdicts: List[RuleVerdict] = field(default_factory=list)
    summary: str = ""
    @property
    def blocking(self) -> bool: return not self.passed and self.mode == "enforce"

def _glob_match(path: str, pattern: str) -> bool:
    rx = "".join(_GLOB_MAP.get(m.group(0), re.escape(m.group(0))) for m in _GLOB_TOK.finditer(pattern.lstrip("./")))
    return bool(re.fullmatch(rx, path.lstrip("./")))

def _str_list(val, name: str) -> List[str]:
    if not isinstance(val, list) or not all(isinstance(x, str) for x in val): raise ValueError(f"{name} must be a list of strings")
    return list(val)

def load_policy(text: str) -> ApprovalPolicy:
    """Parse and validate ``.praisonai/approvals.yml`` via ``yaml.safe_load``."""
    try: raw = yaml.safe_load(text)
    except yaml.YAMLError as exc: raise ValueError(f"invalid approvals YAML: {exc}") from exc
    if not isinstance(raw, dict): raise ValueError("approvals policy must be a YAML mapping")
    mode = raw.get("mode", "observe")
    if mode not in ("observe", "enforce"): raise ValueError(f"invalid mode {mode!r}; expected 'observe' or 'enforce'")
    protected, raw_rules = _str_list(raw.get("protected_paths", list(DEFAULT_PROTECTED)), "protected_paths"), raw.get("rules", [])
    if not isinstance(raw_rules, list): raise ValueError("rules must be a list")
    rules = []
    for item in raw_rules:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise ValueError("each rule must be a mapping with a non-empty string 'name'")
        seats = item.get("seats", 1)
        if isinstance(seats, bool) or not isinstance(seats, int) or seats < 0: raise ValueError(f"rule {item['name']!r}: seats must be int >= 0")
        rules.append(ApprovalRule(item["name"].strip(), _str_list(item.get("paths", []), "paths"), seats,
                                  _str_list(item.get("reviewers", []), "reviewers"), _str_list(item.get("checks", []), "checks")))
    return ApprovalPolicy(mode, protected, rules)

def evaluate_policy(policy: ApprovalPolicy, *, changed_files: List[str], approvers: List[str], passing_checks: Iterable[str] = ()) -> PolicyReport:
    """Deterministically evaluate ``policy`` against changed files, approvers, and passing checks."""
    aset, cset = {a.strip().lower() for a in approvers if a and a.strip()}, set(passing_checks)
    protected = [f for f in changed_files if any(_glob_match(f, p) for p in policy.protected_paths)]
    verdicts = []
    for r in policy.rules:
        if r.paths and not any(_glob_match(f, p) for f in changed_files for p in r.paths): continue
        eligible = aset & {u.strip().lower() for u in r.reviewers} if r.reviewers else aset
        reasons = ([f"needs {r.seats} approval(s), has {len(eligible)}"] if len(eligible) < r.seats else [])
        if missing := [c for c in r.checks if c not in cset]: reasons.append(f"missing passing check(s): {', '.join(missing)}")
        verdicts.append(RuleVerdict(r.name, not reasons, reasons))
    if protected and not {a for a in aset if not a.endswith("[bot]")}:
        verdicts.append(RuleVerdict("protected_paths", False, [f"touches {', '.join(protected)}; requires human approval"]))
    passed = all(v.passed for v in verdicts)
    return PolicyReport(passed, policy.mode, protected, verdicts, f"passed ({policy.mode})" if passed else f"failed ({policy.mode}): {', '.join(v.rule for v in verdicts if not v.passed)}")

def check_pr_policy(pr: Optional[str] = None, *, policy_path: Optional[str] = None, run: Callable = subprocess.run) -> PolicyReport:
    """Read PR metadata via ``gh`` and evaluate ``.praisonai/approvals.yml`` from the base branch."""
    proc = run(["gh", "pr", "view", *([pr.lstrip("#") if pr.startswith("#") else pr] if pr else []), "--json", "files,reviews,statusCheckRollup,baseRefName,number"], capture_output=True, text=True)
    if proc.returncode != 0: raise ShipRefused(f"gh pr view failed: {(proc.stderr or proc.stdout).strip()}")
    view = json.loads(proc.stdout)
    base = view["baseRefName"]
    policy_text = (Path(policy_path).read_text(encoding="utf-8") if Path(policy_path).is_file() else None) if policy_path is not None else next(
        (s.stdout for ref in (f"origin/{base}", base) if (s := run(["git", "show", f"{ref}:{_POLICY_FILE}"], capture_output=True, text=True)).returncode == 0), None)
    if policy_text is None: raise ShipRefused(f"policy file not found: {policy_path}" if policy_path is not None else f"no {_POLICY_FILE} found on base branch '{base}'")
    latest = {((r.get("author") or {}).get("login") or "").strip().lower(): (r.get("state") or "").upper()
              for r in view.get("reviews") or [] if ((r.get("author") or {}).get("login") or "").strip() and (r.get("state") or "").upper() in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED")}
    passing = {k for c in view.get("statusCheckRollup") or [] if isinstance(c, dict) and (c.get("conclusion") or c.get("state")) == "SUCCESS"
               for name in ((c.get("name") or c.get("context") or "").strip(),) if name for wf in ((c.get("workflowName") or "").strip(),) for k in ({name, f"{wf}/{name}"} if wf else {name})}
    return evaluate_policy(load_policy(policy_text), changed_files=[f["path"] for f in view.get("files") or [] if isinstance(f, dict) and f.get("path")], approvers=[u for u, s in latest.items() if s == "APPROVED"], passing_checks=passing)


def format_policy_comment(report: PolicyReport) -> str:
    """Render an upserted PR status comment matching Claude Approvals' observe/enforce clarity."""
    status = "Passed" if report.passed else ("Blocking" if report.blocking else "Pending")
    lines = [
        _COMMENT_MARKER,
        f"### OpenShip Approvals ({report.mode} mode) — {status}",
        "",
        "| Rule | Status | Details |",
        "|---|---|---|",
    ]
    if report.verdicts:
        for v in report.verdicts:
            badge = "PASS" if v.passed else "PENDING"
            detail = "; ".join(v.reasons) if v.reasons else "Satisfied"
            lines.append(f"| `{v.rule}` | {badge} | {detail} |")
    else:
        lines.append("| *(no matching rules)* | PASS | No path-scoped rules matched this PR |")
    lines.extend(["", "_Loaded from default branch `.praisonai/approvals.yml` · OpenShip never auto-merges or auto-approves._"])
    return "\n".join(lines)


def post_policy_comment(pr: Optional[str], report: PolicyReport, *, run: Callable = subprocess.run) -> bool:
    """Upsert a single OpenShip Approvals status comment on the PR (never spams)."""
    pr_arg = [pr.lstrip("#") if pr.startswith("#") else pr] if pr else []
    body = format_policy_comment(report)
    view_proc = run(["gh", "pr", "view", *pr_arg, "--json", "number,url,comments"], capture_output=True, text=True)
    if view_proc.returncode == 0 and (view_proc.stdout or "").strip():
        try:
            view = json.loads(view_proc.stdout)
            url_parts = str(view.get("url", "")).split("/")
            owner, name = url_parts[3], url_parts[4]
            for c in reversed(view.get("comments") or []):
                if not isinstance(c, dict) or not (c.get("body") or "").lstrip().startswith(_COMMENT_MARKER):
                    continue
                cid = str(c.get("databaseId") or "")
                if not cid and (m := _ISSUE_COMMENT_ID_RE.search(str(c.get("url") or ""))):
                    cid = m.group(1)
                if cid:
                    upd = run(
                        ["gh", "api", f"repos/{owner}/{name}/issues/comments/{cid}", "--method", "PATCH", "-f", f"body={body}"],
                        capture_output=True,
                        text=True,
                    )
                    if upd.returncode == 0:
                        return True
        except (ValueError, KeyError, IndexError):
            pass
    return run(["gh", "pr", "comment", *pr_arg, "--body", body], capture_output=True, text=True).returncode == 0
