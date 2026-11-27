"""OpenShip Python API example: ship, self-review, steward, and approval policy."""

from pathlib import Path

from praisonai_code.ship import evaluate_policy, review_diff, ship, watch_pr


def main() -> None:
    # 1. Dry-run ship on the current feature branch (changes nothing, never merges).
    plan = ship(dry_run=True)
    print("Ship plan:\n", plan)

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
        decision = evaluate_policy(policy_path, changed_files=["src/app.py"])
        print("Approval policy decision:", decision)

    # 4. Run one PR steward check cycle against a PR number (never merges).
    # outcome = watch_pr(pr_number=42, once=True)
    # print("Steward outcome:", outcome)
    _ = watch_pr


if __name__ == "__main__":
    main()
