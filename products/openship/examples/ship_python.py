"""OpenShip Python API example: ship, self-review, steward, and approval policy."""

from pathlib import Path

from praisonai_code.ship import ship
from praisonai_code.ship.approvals import evaluate_policy, load_policy
from praisonai_code.ship.review import review_diff
from praisonai_code.ship.steward_loop import watch_pr


def main() -> None:
    # 1. Dry-run ship on the current feature branch (changes nothing, never merges).
    res = ship(dry_run=True)
    print("Ship plan:\n", res.dry_run_plan)

    # 2. Run typed self-review on a unified diff string.
    sample_diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1,2 @@
 def greet(name):
+    return f"Hello, {name}!"
"""
    findings = review_diff(sample_diff, effort="low")
    print(f"Self-review findings: {len(findings)}")

    # 3. Evaluate declarative approval rules from .praisonai/approvals.yml.
    policy_path = Path(".praisonai/approvals.yml")
    if policy_path.is_file():
        policy = load_policy(policy_path.read_text(encoding="utf-8"))
        report = evaluate_policy(
            policy,
            changed_files=["src/app.py"],
            approvers=["alice"],
            passing_checks=["unit-tests"],
        )
        print("Approval policy report:", report)

    # 4. Run one PR steward check cycle against a PR number (never merges).
    # outcome = watch_pr("42", once=True)
    # print("Steward outcome:", outcome)
    _ = watch_pr


if __name__ == "__main__":
    main()
