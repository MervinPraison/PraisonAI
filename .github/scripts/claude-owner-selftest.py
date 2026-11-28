"""Exercise the dispatch handlers with real Git and local Claude/GitHub doubles."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().with_name("claude-owner.sh")

GH = r"""
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
with Path(os.environ["GH_LOG"]).open("a") as log:
    log.write(json.dumps(args) + "\n")
command = args[:2]
if command == ["pr", "list"] or command == ["auth", "setup-git"]:
    pass
elif command == ["pr", "create"]:
    print("https://example.invalid/draft")
elif command == ["api", "--method"]:
    print("https://example.invalid/review")
elif command == ["api", "--paginate"]:
    pass
elif args[1].endswith("/pulls/17"):
    head = os.environ["PR_HEAD"]
    if "--jq" in args:
        print(head)
    else:
        print(json.dumps({"state": "open", "head": {"sha": head},
                          "base": {"sha": os.environ["GITHUB_SHA"], "ref": "main"}}))
elif args[1].endswith("/issues/17"):
    print("open" if "--jq" in args else json.dumps({"state": "open", "title": "Test issue"}))
else:
    raise SystemExit(f"Unexpected gh invocation: {args}")
"""

CLAUDE = r"""
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
data = {"args": args, "cwd": str(Path.cwd()), "prompt": sys.stdin.read()}
Path(os.environ["CLAUDE_LOG"]).write_text(json.dumps(data))
assert "GH_TOKEN" not in os.environ
assert "--restricted" in args and "--strict-mcp-config" in args
if os.environ["CLAUDE_MODE"] == "fix-issue":
    assert set(args[args.index("--tools") + 1].split(",")) == {"Read", "Edit", "Write", "Glob", "Grep"}
    assert not Path(".git").exists()
    permissions = json.loads(args[args.index("--settings") + 1])["permissions"]
    assert all(permissions[f"block{operation}OutsideWorkingDirectories"] for operation in ("Reads", "Writes"))
    Path(os.environ.get("FIX_PATH", "app.py")).write_text("fixed\n")
    print("Status: PATCH_READY\nSuggested test: pytest tests/unit.")
else:
    print(os.environ.get("CLAUDE_RESULT", "SDK value: Strong") + "\nProvides a simpler API.")
"""


class OwnerClaudeTest(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name).resolve()
        self.origin = self.root / "origin.git"
        self.checkout = self.root / "checkout"
        self.verifier = self.root / "verifier"
        self.publisher = self.root / "publisher"
        self.handoff = self.root / "handoff"
        self.git("init", "--bare", "--initial-branch=main", str(self.origin), cwd=self.root)
        self.git("clone", str(self.origin), str(self.checkout), cwd=self.root)
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        (self.checkout / "AGENTS.md").write_text("Trusted main rules\n")
        (self.checkout / "app.py").write_text("original\n")
        self.git("add", ".")
        self.git("commit", "-m", "main")
        self.git("push", "origin", "main")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.git("switch", "-c", "contributor")
        (self.checkout / "AGENTS.md").write_text("Instructions from PR head\n")
        self.git("commit", "-am", "pr")
        self.pr_head = self.git("rev-parse", "HEAD").strip()
        self.git("push", "origin", "HEAD:refs/pull/17/head")
        self.git("switch", "main")
        self.git("clone", str(self.origin), str(self.verifier), cwd=self.root)
        self.git("clone", str(self.origin), str(self.publisher), cwd=self.root)

        programs = self.root / "bin"
        programs.mkdir()
        for name, code in (("gh", GH), ("claude", CLAUDE)):
            program = programs / name
            program.write_text(f"#!{sys.executable}\n" + code)
            program.chmod(0o755)
        self.env = {
            "PATH": f"{programs}{os.pathsep}{os.environ['PATH']}",
            "GITHUB_REPOSITORY": "MervinPraison/PraisonAI",
            "GITHUB_SHA": self.base,
            "GITHUB_OUTPUT": str(self.root / "output"),
            "GITHUB_STEP_SUMMARY": str(self.root / "summary"),
            "GITHUB_RUN_ID": "42",
            "HANDOFF": str(self.handoff),
            "TARGET_NUMBER": "17",
            "OWNER_INSTRUCTIONS": "Preserve this exact instruction.",
            "PR_HEAD": self.pr_head,
            "REVIEW_HEAD": self.pr_head,
            "GH_LOG": str(self.root / "gh.jsonl"),
            "CLAUDE_LOG": str(self.root / "claude.json"),
        }

    def git(self, *args, cwd=None):
        return subprocess.check_output(["git", *args], cwd=cwd or self.checkout, text=True, stderr=subprocess.PIPE)

    def run_handler(self, mode, operation, *, cwd=None, expected=0, **overrides):
        result = subprocess.run(
            ["bash", str(SCRIPT), operation],
            cwd=cwd or self.checkout,
            env={**self.env, "CLAUDE_MODE": mode, **overrides},
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, expected, result.stderr + result.stdout)
        return result

    def calls(self):
        return [json.loads(line) for line in (self.root / "gh.jsonl").read_text().splitlines()]

    def test_review_uses_main_and_posts_comment_for_exact_head(self):
        self.run_handler("review-pr", "prepare")
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.base)
        self.assertIn(f"head_sha={self.pr_head}", (self.root / "output").read_text())
        self.run_handler("review-pr", "run")
        self.run_handler("review-pr", "stage")
        call = json.loads((self.root / "claude.json").read_text())
        self.assertEqual(call["args"][call["args"].index("--tools") + 1], "")
        self.assertEqual(call["cwd"], str(self.handoff))
        policy, diff = call["prompt"].split("--- PR diff ---")
        self.assertIn("Trusted main rules", policy)
        self.assertIn("Preserve this exact instruction.", policy)
        self.assertNotIn("Instructions from PR head", policy)
        self.assertIn("+Instructions from PR head", diff)
        result = self.run_handler("review-pr", "publish-review", cwd=self.publisher)
        self.assertIn("https://example.invalid/review", result.stdout)
        post = next(args for args in self.calls() if "POST" in args)
        self.assertIn("event=COMMENT", post)
        self.assertIn(f"commit_id={self.pr_head}", post)
        self.assertIn("SDK value: Strong", (self.handoff / "review-body.md").read_text())

    def test_moved_head_and_missing_grade_are_rejected(self):
        self.run_handler("review-pr", "prepare")
        self.run_handler("review-pr", "run", CLAUDE_RESULT="No grade")
        self.run_handler("review-pr", "stage", expected=1)
        self.run_handler("review-pr", "run")
        self.run_handler("review-pr", "stage")
        self.run_handler("review-pr", "publish-review", cwd=self.publisher, expected=1, PR_HEAD=self.base)
        self.assertFalse(any("POST" in call for call in self.calls()))

    def test_issue_patch_publishes_on_new_branch_as_draft(self):
        self.run_handler("fix-issue", "prepare")
        self.run_handler("fix-issue", "run")
        self.run_handler("fix-issue", "stage")
        self.assertEqual((self.checkout / "app.py").read_text(), "original\n")
        self.run_handler(
            "fix-issue", "verify-fix", cwd=self.verifier,
            VALIDATION_COMMAND='test "$(cat app.py)" = fixed && test -z "${GH_TOKEN:-}${CLAUDE_CODE_OAUTH_TOKEN:-}"',
        )
        result = self.run_handler("fix-issue", "publish-fix", cwd=self.publisher, PACKAGE_VALIDATION_RAN="true")
        self.assertIn("https://example.invalid/draft", result.stdout)
        self.assertEqual(self.git("show", "main:app.py", cwd=self.origin), "original\n")
        self.assertEqual(self.git("show", "claude/issue-17-42:app.py", cwd=self.origin), "fixed\n")
        create = next(args for args in self.calls() if args[:2] == ["pr", "create"])
        self.assertIn("--draft", create)
        self.assertEqual(create[create.index("--base") + 1], "main")
        self.assertIn("maintainer-provided command passed", (self.handoff / "fix-body.md").read_text())

    def test_failed_validation_does_not_publish(self):
        self.run_handler("fix-issue", "prepare")
        self.run_handler("fix-issue", "run")
        self.run_handler("fix-issue", "stage")
        self.run_handler("fix-issue", "verify-fix", cwd=self.verifier, expected=23, VALIDATION_COMMAND="exit 23")
        self.assertFalse(any(call[:2] == ["pr", "create"] for call in self.calls()))

    def test_issue_cannot_publish_agent_instructions(self):
        self.run_handler("fix-issue", "prepare")
        self.run_handler("fix-issue", "run", FIX_PATH="AGENTS.md")
        self.run_handler("fix-issue", "stage")
        self.run_handler("fix-issue", "verify-fix", cwd=self.verifier, expected=1, VALIDATION_COMMAND="exit 23")
        result = self.run_handler("fix-issue", "publish-fix", cwd=self.publisher, expected=1)
        self.assertIn("Maintainer review required", result.stderr)
        self.assertFalse(any(call[:2] == ["pr", "create"] for call in self.calls()))


if __name__ == "__main__":
    unittest.main()
