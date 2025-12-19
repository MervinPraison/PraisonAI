"""
Git Integration Example for PraisonAI CLI.

Auto-commit with AI messages, diff viewing, undo.
Docs: https://docs.praison.ai/cli/git-integration
"""

from praisonai.cli.features import GitIntegrationHandler

# Initialize
handler = GitIntegrationHandler(verbose=True)
git = handler.initialize(repo_path=".")

# Check if it's a git repo
if not git.is_repo:
    print("Not a git repository!")
    exit(1)

# Show status
print("=== Git Status ===")
status = handler.show_status()
print(f"Branch: {status.branch}")
print(f"Staged: {len(status.staged_files)}")
print(f"Modified: {len(status.modified_files)}")
print(f"Untracked: {len(status.untracked_files)}")

# Show diff (if any changes)
if status.has_changes:
    print("\n=== Diff ===")
    diff = handler.show_diff()
    if diff:
        print(diff[:300] + "..." if len(diff) > 300 else diff)

# Show recent commits
print("\n=== Recent Commits ===")
commits = handler.show_log(count=5)
for c in commits:
    print(f"  {c.short_hash} {c.message[:50]}")

# To commit with AI message:
# commit = handler.commit()  # Auto-generates message
# commit = handler.commit(message="Custom message")

# To undo last commit:
# handler.undo(soft=True)  # Keeps changes staged
