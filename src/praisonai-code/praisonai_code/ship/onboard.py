"""Zero-friction OpenShip onboarding: ``ship init`` and ``ship check``."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Mapping, Optional, Tuple

from praisonaiagents.tools.path_safety import resolve_inside
from praisonai_code.ship import is_ship_disabled
from praisonai_code.ship.flow import ShipRefused
from praisonai_code.ship.review import EFFORTS

_MODEL_SAFE_RE = re.compile(r"^[A-Za-z0-9._:/@-]{1,128}$")
_API_KEY_VARS: Tuple[str, ...] = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
)

OPENSHIP_WORKFLOW_YAML = """\
name: OpenShip (Review, Steward & Policy)

on:
  pull_request:
    types: [opened, synchronize, reopened, labeled]
  pull_request_review:
    types: [submitted, dismissed]
  pull_request_review_comment:
    types: [created]
  issue_comment:
    types: [created]
  workflow_run:
    workflows: ["CI", "Tests", "Smoke"]
    types: [completed]

permissions:
  contents: write
  pull-requests: write

concurrency:
  group: openship-${{ github.event.pull_request.number || github.event.issue.number || github.event.workflow_run.pull_requests[0].number || github.run_id }}
  cancel-in-progress: false

env:
  # Works with ANY LLM provider supported by PraisonAI:
  # OpenAI (gpt-4o-mini), Anthropic (claude-sonnet-4-6), Gemini (gemini/gemini-2.5-flash),
  # OpenRouter (openrouter/...), or self-hosted/local Ollama (ollama/qwen3.5:9b).
  OPENSHIP_MODEL: ${{ vars.OPENSHIP_MODEL || 'gpt-4o-mini' }}
  OPENSHIP_EFFORT: ${{ vars.OPENSHIP_EFFORT || 'high' }}

jobs:
  # Pillar 1: Inline AI Code Review (reads REVIEW.md from default branch, adversarial verify)
  review:
    if: >-
      github.event_name == 'pull_request' &&
      github.event.action != 'labeled' &&
      !endsWith(github.actor, '[bot]') &&
      github.event.pull_request.head.repo.full_name == github.repository &&
      !contains(github.event.pull_request.labels.*.name, 'openship-stop')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.ref }}
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install PraisonAI Code (OpenShip)
        run: pip install --quiet praisonai-code
      - name: Run OpenShip inline self-review
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
        run: >-
          praisonai-code ship "${{ github.event.pull_request.number }}"
          --effort "${{ env.OPENSHIP_EFFORT }}"
          --model "${{ env.OPENSHIP_MODEL }}"
          --post-review

  # Pillar 2: PR Steward (fixes failing CI, merge conflicts, review threads & @praisonai directives; 3-try circuit breaker; never merges)
  steward:
    if: >-
      !endsWith(github.actor, '[bot]') &&
      (
        (github.event_name == 'workflow_run' && github.event.workflow_run.conclusion == 'failure' && github.event.workflow_run.pull_requests[0].number != null) ||
        (github.event_name == 'pull_request_review_comment' && github.event.pull_request.head.repo.full_name == github.repository && !contains(github.event.pull_request.labels.*.name, 'openship-stop')) ||
        (github.event_name == 'issue_comment' && github.event.issue.pull_request != null && contains(github.event.comment.body, '@praisonai') && !contains(github.event.comment.body, '@praisonai stop'))
      )
    runs-on: ubuntu-latest
    steps:
      - name: Resolve PR number & head ref
        id: pr
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          PR_NUM="${{ github.event.pull_request.number || github.event.issue.number || github.event.workflow_run.pull_requests[0].number }}"
          echo "number=$PR_NUM" >> "$GITHUB_OUTPUT"
          HEAD_REF="$(gh pr view "$PR_NUM" --json headRefName --jq .headRefName)"
          IS_FORK="$(gh pr view "$PR_NUM" --json isCrossRepository --jq .isCrossRepository)"
          echo "head_ref=$HEAD_REF" >> "$GITHUB_OUTPUT"
          echo "is_fork=$IS_FORK" >> "$GITHUB_OUTPUT"

      - uses: actions/checkout@v4
        if: steps.pr.outputs.is_fork == 'false'
        with:
          ref: ${{ steps.pr.outputs.head_ref }}
          fetch-depth: 0

      - uses: actions/setup-python@v5
        if: steps.pr.outputs.is_fork == 'false'
        with:
          python-version: "3.12"

      - name: Install PraisonAI Code (OpenShip)
        if: steps.pr.outputs.is_fork == 'false'
        run: pip install --quiet praisonai-code

      - name: Run one PR Steward cycle (stateless 3-attempt circuit breaker)
        if: steps.pr.outputs.is_fork == 'false'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
        run: >-
          praisonai-code steward "${{ steps.pr.outputs.number }}"
          --once
          --model "${{ env.OPENSHIP_MODEL }}"

  # Pillar 3: Declarative PR Approvals Policy Check (.praisonai/approvals.yml on default branch; observe or enforce)
  approvals:
    if: >-
      (github.event_name == 'pull_request' || github.event_name == 'pull_request_review') &&
      github.event.pull_request.head.repo.full_name == github.repository
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install PraisonAI Code (OpenShip)
        run: pip install --quiet praisonai-code
      - name: Evaluate .praisonai/approvals.yml
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          if git show "origin/${{ github.event.pull_request.base.ref }}:.praisonai/approvals.yml" >/dev/null 2>&1; then
            praisonai-code approvals "${{ github.event.pull_request.number }}"
          else
            echo "No .praisonai/approvals.yml on base branch; skipping policy check."
          fi
"""

APPROVALS_POLICY_YAML = """\
# Copy this file to .praisonai/approvals.yml on your default branch.
# OpenShip loads approval policy from the default branch so a PR cannot
# weaken its own rules.

mode: observe  # Switch to "enforce" once your team has verified rule matches

protected_paths:
  - ".praisonai/approvals.yml"
  - ".github/workflows/**"

rules:
  - name: core-source
    paths:
      - "src/**"
    seats: 1
    checks:
      - "unit-tests"

  - name: security-sensitive
    paths:
      - "security/**"
      - "**/auth/**"
    seats: 2
    reviewers:
      - "alice"
      - "bob"
    checks:
      - "unit-tests"
      - "security-scan"
"""

REVIEW_MD_TEMPLATE = """\
# Code Review Guidelines (OpenShip)

OpenShip reads this file from the default branch (`origin/<base>`) on every PR review.

## Always flag (important)
- Bugs, logic regressions, unhandled edge cases, and data-loss risks.
- Hard-coded secrets, path traversal, SSRF, SQL/command injection, or auth bypasses.
- Breaking public API changes without a backward-compatibility path.

## Skip
- Pure formatting or style preferences already enforced by linters.
"""


@dataclass
class ReadinessReport:
    repo_root: Optional[Path] = None
    branch: str = ""
    disabled_reason: Optional[str] = None
    gh_installed: bool = False
    gh_authed: bool = False
    llm_env_vars: List[str] = field(default_factory=list)
    ollama_installed: bool = False
    ui_installed: bool = False
    has_workflow: bool = False
    has_policy: bool = False
    has_review_md: bool = False

    @property
    def has_llm(self) -> bool:
        return bool(self.llm_env_vars) or self.ollama_installed


@dataclass
class InitResult:
    repo_root: Path
    created: List[str] = field(default_factory=list)
    would_create: List[str] = field(default_factory=list)
    kept: List[str] = field(default_factory=list)
    readiness: ReadinessReport = field(default_factory=ReadinessReport)


def render_workflow_yaml(model: Optional[str] = None, effort: str = "high") -> str:
    """Return ``openship.yml`` with optional validated default model and effort."""
    if effort not in EFFORTS:
        raise ValueError(f"unknown review effort {effort!r}; use one of {', '.join(EFFORTS)}")
    text = OPENSHIP_WORKFLOW_YAML
    if model:
        cleaned = model.strip()
        if not _MODEL_SAFE_RE.match(cleaned):
            raise ValueError(f"invalid model name {model!r}")
        text = text.replace("vars.OPENSHIP_MODEL || 'gpt-4o-mini'", f"vars.OPENSHIP_MODEL || '{cleaned}'", 1)
    if effort != "high":
        text = text.replace("vars.OPENSHIP_EFFORT || 'high'", f"vars.OPENSHIP_EFFORT || '{effort}'", 1)
    return text


def _detect_repo_root(cwd: Path, run: Callable) -> Tuple[Optional[Path], str]:
    proc = run(["git", "rev-parse", "--show-toplevel"], cwd=str(cwd), capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return None, ""
    root = Path(proc.stdout.strip()).resolve()
    br = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(root), capture_output=True, text=True, check=False)
    branch = (br.stdout or "").strip() if br.returncode == 0 else ""
    return root, branch


def check_readiness(
    cwd: Optional[Path] = None,
    *,
    run: Callable = subprocess.run,
    env: Optional[Mapping[str, str]] = None,
    which: Callable[[str], Optional[str]] = shutil.which,
    find_spec: Callable[[str], object] = importlib.util.find_spec,
) -> ReadinessReport:
    """Inspect local readiness across Terminal/CI, Visual Web UI, and GitHub Actions."""
    base = Path(cwd).expanduser().resolve() if cwd else Path.cwd().resolve()
    active_env = os.environ if env is None else env
    repo_root, branch = _detect_repo_root(base, run)

    gh_installed = bool(which("gh"))
    gh_authed = False
    if gh_installed:
        auth = run(["gh", "auth", "status"], cwd=str(repo_root or base), capture_output=True, text=True, check=False)
        gh_authed = auth.returncode == 0

    llm_vars = [k for k in _API_KEY_VARS if (active_env.get(k) or "").strip()]
    ollama_installed = bool(which("ollama"))
    ui_installed = find_spec("praisonaiui") is not None

    has_workflow = bool(repo_root and (repo_root / ".github" / "workflows" / "openship.yml").is_file())
    has_policy = bool(repo_root and (repo_root / ".praisonai" / "approvals.yml").is_file())
    has_review_md = bool(
        repo_root and ((repo_root / "REVIEW.md").is_file() or (repo_root / ".praisonai" / "REVIEW.md").is_file())
    )

    return ReadinessReport(
        repo_root=repo_root,
        branch=branch,
        disabled_reason=is_ship_disabled(),
        gh_installed=gh_installed,
        gh_authed=gh_authed,
        llm_env_vars=llm_vars,
        ollama_installed=ollama_installed,
        ui_installed=ui_installed,
        has_workflow=has_workflow,
        has_policy=has_policy,
        has_review_md=has_review_md,
    )


def format_readiness(report: ReadinessReport) -> str:
    """Format a compact, actionable checklist for Terminal/CI, Web UI, and GitHub."""
    mark = lambda ok: "[OK]" if ok else "[--]"
    lines = ["OpenShip readiness check:"]
    if report.disabled_reason:
        lines.append(f"  [!!] Kill switch active: {report.disabled_reason}")

    repo_desc = f"{report.repo_root} (branch: {report.branch or 'detached'})" if report.repo_root else "not in a git repo"
    gh_desc = "authenticated" if report.gh_authed else ("installed, run `gh auth login`" if report.gh_installed else "missing `gh` CLI")
    llm_parts = list(report.llm_env_vars) + (["ollama"] if report.ollama_installed else [])
    llm_desc = ", ".join(llm_parts) if llm_parts else "none set (export OPENAI_API_KEY or install Ollama)"
    ui_desc = "ready (`praisonai-code ship ui`)" if report.ui_installed else 'install with `pip install "praisonai-code[ui]"`'
    wf_desc = ".github/workflows/openship.yml" if report.has_workflow else "missing (run `praisonai-code ship init`)"
    pol_desc = ".praisonai/approvals.yml" if report.has_policy else "optional (run `praisonai-code ship init`)"
    rev_desc = "REVIEW.md" if report.has_review_md else "optional (run `praisonai-code ship init`)"

    lines.extend([
        f"  {mark(bool(report.repo_root))} Git repo:       {repo_desc}",
        f"  {mark(report.gh_authed)} GitHub CLI:     {gh_desc}",
        f"  {mark(report.has_llm)} LLM provider:   {llm_desc}",
        f"  {mark(report.ui_installed)} Visual Web UI:  {ui_desc}",
        f"  {mark(report.has_workflow)} GitHub Actions: {wf_desc}",
        f"  {mark(report.has_policy)} Policy file:    {pol_desc}",
        f"  {mark(report.has_review_md)} Review guide:   {rev_desc}",
    ])

    next_steps: List[str] = []
    if not report.gh_authed:
        next_steps.append("gh auth login")
    if not report.has_llm:
        next_steps.append("export OPENAI_API_KEY=...  # or: ollama pull qwen3.5")
    if not report.has_workflow:
        next_steps.append("praisonai-code ship init   # add GitHub Actions + approvals.yml + REVIEW.md")
    else:
        secret_var = report.llm_env_vars[0] if report.llm_env_vars else "OPENAI_API_KEY"
        next_steps.append(f'printf "%s" "${secret_var}" | gh secret set {secret_var}   # once per GitHub repo')
    if not report.ui_installed:
        next_steps.append('pip install "praisonai-code[ui]" && praisonai-code ship ui')
    else:
        next_steps.append("praisonai-code ship ui     # open visual dashboard at http://127.0.0.1:8765")

    lines.append("\nNext steps:")
    for step in next_steps:
        lines.append(f"  {step}")
    return "\n".join(lines)


def init_repo(
    cwd: Optional[Path] = None,
    *,
    dry_run: bool = False,
    model: Optional[str] = None,
    effort: str = "high",
    run: Callable = subprocess.run,
    env: Optional[Mapping[str, str]] = None,
    which: Callable[[str], Optional[str]] = shutil.which,
    find_spec: Callable[[str], object] = importlib.util.find_spec,
) -> InitResult:
    """Scaffold GitHub Actions workflow, declarative policy, and REVIEW.md (idempotent)."""
    base = Path(cwd).expanduser().resolve() if cwd else Path.cwd().resolve()
    repo_root, _ = _detect_repo_root(base, run)
    if repo_root is None:
        raise ShipRefused("not inside a git repository — run `git init` first")

    workflow_content = render_workflow_yaml(model=model, effort=effort)
    targets: List[Tuple[str, str]] = [
        (".github/workflows/openship.yml", workflow_content),
        (".praisonai/approvals.yml", APPROVALS_POLICY_YAML),
    ]
    if not (repo_root / ".praisonai" / "REVIEW.md").is_file():
        targets.append(("REVIEW.md", REVIEW_MD_TEMPLATE))

    result = InitResult(repo_root=repo_root)
    for rel, content in targets:
        dest = Path(resolve_inside(repo_root, rel))
        if dest.exists():
            result.kept.append(rel)
            continue
        if dry_run:
            result.would_create.append(rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        result.created.append(rel)

    result.readiness = check_readiness(
        repo_root, run=run, env=env, which=which, find_spec=find_spec
    )
    return result


def format_init_result(result: InitResult, *, dry_run: bool = False) -> str:
    """Render concise human output for ``ship init``."""
    lines = [f"OpenShip init ({result.repo_root}):"]
    for rel in result.created:
        lines.append(f"  + created {rel}")
    for rel in result.would_create:
        lines.append(f"  ~ would create {rel}")
    for rel in result.kept:
        lines.append(f"  = kept existing {rel}")
    if not (result.created or result.would_create):
        lines.append("  All OpenShip files already exist (nothing overwritten).")
    lines.append("")
    lines.append(format_readiness(result.readiness))
    if not dry_run and result.created:
        joined = " ".join(result.created)
        lines.append(f"  git add {joined} && git commit -m 'chore: enable OpenShip' && git push")
    return "\n".join(lines)
