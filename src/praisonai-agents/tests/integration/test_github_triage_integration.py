"""
Integration tests for GitHub triage workflow.

These tests validate the PraisonAI GitHub triage command:
- Issue analysis and code change detection
- Branch creation and commit/push
- Conditional PR creation (only when explicitly requested in issue body)
- Sticky comment updates with branch links

Usage:
    cd /Users/praison/praisonai-package
    GITHUB_TOKEN=$(gh auth token) GITHUB_REPOSITORY=MervinPraison/PraisonAI \
        PRAISONAI_AUTO_APPROVE=true praisonai github triage \
        --issue 1347 --agent-file .github/praisonai-issue-triage.yaml

Manual verification steps:
1. Create a test issue without "create PR" in the body
2. Run triage command
3. Verify branch is created and pushed
4. Verify NO PR is created automatically
5. Verify sticky comment shows "Create PR →" link
6. Click the link to manually create PR if needed
"""
import os
import subprocess
import pytest


class TestGitHubTriageIntegration:
    """Integration tests for GitHub triage workflow."""

    def test_triage_yaml_structure(self):
        """Verify the triage YAML has correct 2-step structure with conditional PR."""
        import yaml
        
        yaml_path = "/Users/praison/praisonai-package/.github/praisonai-issue-triage.yaml"
        assert os.path.exists(yaml_path), f"YAML file not found: {yaml_path}"
        
        with open(yaml_path) as f:
            config = yaml.safe_load(f)
        
        # Should have process: workflow
        assert config.get("process") == "workflow", "Must use workflow process"
        
        # Should have exactly 2 steps
        steps = config.get("steps", [])
        assert len(steps) == 2, f"Should have 2 steps, got {len(steps)}"
        
        # Steps should be Analyze Issue and Implement Fix
        step_names = [s.get("name", "").lower() for s in steps]
        assert "analyze" in step_names[0], "First step should be analysis"
        assert "implement" in step_names[1], "Second step should be implementation"
        
        # Software engineer should have github_create_pull_request tool
        roles = config.get("roles", {})
        engineer = roles.get("software_engineer", {})
        tools = engineer.get("tools", [])
        assert "github_create_pull_request" in tools, "Engineer needs PR tool"
        
        # Implementation step action should mention conditional PR creation
        impl_step = steps[1]
        action = impl_step.get("action", "")
        assert "create pull request" in action.lower() or "create PR" in action, \
            "Should mention conditional PR creation in action"

    def test_github_triage_command_runs(self):
        """Test that the triage command can be invoked (requires GITHUB_TOKEN)."""
        # Skip if no token available
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            pytest.skip("GITHUB_TOKEN not available")
        
        # Just verify the command exists and shows help
        result = subprocess.run(
            ["praisonai", "github", "triage", "--help"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        assert "triage" in result.stdout.lower()

    def test_sticky_comment_has_branch_and_pr_links(self):
        """Verify sticky comment renders branch link and Create PR link correctly."""
        from praisonai.cli.commands.github import StickyComment
        
        sticky = StickyComment(
            api_base="https://api.github.com",
            issue=123,
            token="fake-token",
            task_type="Issue",
            title="Test issue",
            run_url="",
            repo_name="owner/repo"
        )
        
        # Set branch
        sticky.set_branch("praisonai/issue-123")
        
        # Build body - should have branch link and Create PR link (not View PR)
        body = sticky._build_body(final=True)
        
        # Should contain branch link
        assert "praisonai/issue-123" in body
        assert "https://github.com/owner/repo/tree/praisonai/issue-123" in body
        
        # Should have "Create PR →" link to compare URL (not an actual PR URL)
        assert "Create PR →" in body
        assert "compare/main...praisonai/issue-123" in body
        
        # Should NOT have "View PR →" since no PR was created
        assert "View PR →" not in body

    def test_sticky_comment_shows_view_pr_when_pr_created(self):
        """Verify sticky comment shows View PR when PR is explicitly created."""
        from praisonai.cli.commands.github import StickyComment
        
        sticky = StickyComment(
            api_base="https://api.github.com",
            issue=123,
            token="fake-token",
            task_type="Issue",
            title="Test issue",
            run_url="",
            repo_name="owner/repo"
        )
        
        # Set branch and PR
        sticky.set_branch("praisonai/issue-123")
        sticky.set_pr("https://github.com/owner/repo/pull/456", pr_number=456)
        
        # Build body
        body = sticky._build_body(final=True)
        
        # Should now show "View PR →" not "Create PR →"
        assert "View PR →" in body
        assert "https://github.com/owner/repo/pull/456" in body
        assert "Create PR →" not in body


@pytest.mark.manual
class TestGitHubTriageManual:
    """
    Manual integration tests for GitHub triage.
    
    These require:
    - GITHUB_TOKEN with repo access
    - A real GitHub repository
    - OpenAI API key for the agents
    
    Run with:
        cd /Users/praison/praisonai-package
        GITHUB_TOKEN=$(gh auth token) \
        OPENAI_API_KEY=sk-... \
        GITHUB_REPOSITORY=MervinPraison/PraisonAI \
        PRAISONAI_AUTO_APPROVE=true \
        praisonai github triage --issue <ISSUE_NUM> \
            --agent-file .github/praisonai-issue-triage.yaml
    """
    
    def test_no_pr_created_without_explicit_request(self):
        """
        Test issue #1347 style: branch created, pushed, NO PR auto-created.
        
        Steps:
        1. Create issue without "create PR" in body
        2. Run triage
        3. Verify branch exists: git branch -r | grep issue-XXX
        4. Verify NO PR exists: gh pr list --head praisonai/issue-XXX
        5. Verify sticky comment has "Create PR →" link
        """
        pytest.skip("Manual test - requires real GitHub issue and API keys")

    def test_pr_created_when_explicitly_requested(self):
        """
        Test issue with "create pull request" in body: PR auto-created.
        
        Steps:
        1. Create issue with "create pull request" or "create PR" in body
        2. Run triage
        3. Verify branch exists
        4. Verify PR IS created: gh pr list --head praisonai/issue-XXX
        5. Verify sticky comment has "View PR →" link
        """
        pytest.skip("Manual test - requires real GitHub issue and API keys")

    def test_triage_command_full_workflow(self):
        """
        Full manual test command:
        
        cd /Users/praison/praisonai-package && 
        GITHUB_TOKEN=$(gh auth token) 
        GITHUB_REPOSITORY=MervinPraison/PraisonAI 
        PRAISONAI_AUTO_APPROVE=true 
        praisonai github triage 
            --issue 1347 
            --agent-file .github/praisonai-issue-triage.yaml 2>&1 | 
        tee /tmp/triage-1347b.log
        
        Then verify:
        - Exit code is 0
        - Branch praisonai/issue-1347 exists remotely
        - No PR was auto-created
        - Sticky comment updated with Create PR link
        """
        pytest.skip("Manual test - run the command above and verify output")
