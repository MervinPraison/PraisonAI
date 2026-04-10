"""
Integration tests for enhanced GitHub sticky comment functionality.

Tests the improved PraisonAI comment format with:
- Progress bar with percentage
- File tracking from commands
- Feature extraction from output
- Usage examples
- Enhanced visual formatting
"""
import pytest
import sys
import time
from pathlib import Path

# Add praisonai wrapper to path
PRAISONAI_ROOT = Path(__file__).parent.parent.parent.parent.parent / "src" / "praisonai"
if str(PRAISONAI_ROOT) not in sys.path:
    sys.path.insert(0, str(PRAISONAI_ROOT))


class TestEnhancedStickyComment:
    """Test enhanced StickyComment functionality."""

    def test_progress_bar_calculation(self):
        """Verify progress percentage is calculated correctly."""
        from praisonai.cli.commands.github import StickyComment
        
        sticky = StickyComment(
            api_base="https://api.github.com",
            issue=123,
            token="fake",
            task_type="Issue",
            title="Test",
            run_url="",
            repo_name="owner/repo"
        )
        
        # Set up todos
        sticky.set_todos([
            {"content": "Step 1", "status": "completed"},
            {"content": "Step 2", "status": "completed"},
            {"content": "Step 3", "status": "in_progress"},
            {"content": "Step 4", "status": "pending"},
        ])
        
        sticky._update_progress()
        assert sticky._progress_percent == 50.0  # 2/4 completed
        
        # Mark all complete
        for t in sticky._todos:
            t["status"] = "completed"
        sticky._update_progress()
        assert sticky._progress_percent == 100.0

    def test_file_extraction_from_commands(self):
        """Verify file paths are extracted from shell commands."""
        from praisonai.cli.commands.github import StickyComment
        
        sticky = StickyComment(
            api_base="https://api.github.com",
            issue=123,
            token="fake",
            task_type="Issue",
            title="Test",
            run_url="",
            repo_name="owner/repo"
        )
        
        # Test various command patterns
        commands = [
            "python3 -c \"open('src/test.py').read()\"",
            "sed -i 's/old/new/g' src/config.yaml",
            "cat > output.txt << 'EOF'\ncontent\nEOF",
            "echo 'hello' > greeting.md",
        ]
        
        for cmd in commands:
            sticky._extract_file_from_command(cmd)
        
        # Verify files were extracted (paths may vary based on extraction pattern)
        paths = [f["path"] for f in sticky._files_modified]
        assert any("test.py" in p for p in paths)
        assert any("config.yaml" in p for p in paths)
        assert "output.txt" in paths
        assert "greeting.md" in paths

    def test_feature_extraction_from_output(self):
        """Verify features are extracted from agent output."""
        from praisonai.cli.commands.github import StickyComment
        
        sticky = StickyComment(
            api_base="https://api.github.com",
            issue=123,
            token="fake",
            task_type="Issue",
            title="Test",
            run_url="",
            repo_name="owner/repo"
        )
        
        # Test various output patterns
        outputs = [
            "- ✅ Added logging support",
            "Implemented: error handling",
            "**Authentication** – Added OAuth2 flow",
            "Created: User profile page",
            "Fixed: Memory leak in cache",
        ]
        
        for output in outputs:
            sticky._extract_features_from_output(output)
        
        # Verify features were extracted
        assert "Added logging support" in sticky._features
        assert "error handling" in sticky._features
        assert "Authentication" in sticky._features
        assert "User profile page" in sticky._features
        assert "Memory leak in cache" in sticky._features

    def test_enhanced_body_structure(self):
        """Verify enhanced comment body contains all sections."""
        from praisonai.cli.commands.github import StickyComment
        
        sticky = StickyComment(
            api_base="https://api.github.com",
            issue=456,
            token="fake",
            task_type="Feature",
            title="Add cool feature",
            run_url="https://github.com/owner/repo/actions/runs/123",
            repo_name="owner/repo"
        )
        
        # Set up data
        sticky.set_todos([
            {"content": "Analyze requirements", "status": "completed"},
            {"content": "Implement feature", "status": "completed"},
        ])
        sticky.set_branch("feature/cool-thing")
        sticky.add_file_modified("src/feature.py", "Added main implementation")
        sticky.add_file_modified("tests/test_feature.py", "Added tests")
        sticky.add_feature("Cool new functionality")
        sticky.add_feature("Better UX")
        sticky.add_usage_example("from praisonai import cool_feature\ncool_feature.run()")
        sticky._summary_lines.append("Successfully implemented the feature")
        
        # Build body
        body = sticky._build_body(final=True)
        
        # Verify all sections present
        assert "Progress:" in body  # Progress bar
        assert "████" in body or "░░░░" in body  # Progress bar characters
        assert "🤖 PraisonAI completed" in body  # Header
        assert "COMPLETE" in body  # Status
        assert "📊 Workflow Visualization" in body  # Mermaid header
        assert "flowchart LR" in body  # Mermaid diagram
        assert "✅ Tasks Completed" in body  # Todo section
        assert "📝 Files Modified" in body  # Files section
        assert "`src/feature.py`" in body  # File path
        assert "⭐ Key Features Implemented" in body  # Features section
        assert "Cool new functionality" in body  # Feature text
        assert "💡 Usage" in body  # Usage section
        assert "```python" in body  # Code block
        assert "📝 Summary" in body  # Summary section
        assert "Powered by [PraisonAI]" in body  # Footer

    def test_progressive_sections_appear(self):
        """Verify sections appear progressively as data is added."""
        from praisonai.cli.commands.github import StickyComment
        
        sticky = StickyComment(
            api_base="https://api.github.com",
            issue=789,
            token="fake",
            task_type="Bug",
            title="Fix bug",
            run_url="",
            repo_name="owner/repo"
        )
        
        # Initial state - only basic structure
        body = sticky._build_body()
        assert "Progress:" not in body  # No todos yet
        assert "📝 Files Modified" not in body
        assert "⭐ Key Features" not in body
        
        # Add todos
        sticky.set_todos([{"content": "Fix bug", "status": "in_progress"}])
        body = sticky._build_body()
        assert "Progress:" in body
        assert "📊 Workflow Visualization" in body
        
        # Add files
        sticky.add_file_modified("src/bugfix.py", "Fixed the bug")
        body = sticky._build_body()
        assert "📝 Files Modified" in body
        assert "`src/bugfix.py`" in body
        
        # Add features
        sticky.add_feature("Bug is now fixed")
        body = sticky._build_body()
        assert "⭐ Key Features Implemented" in body
        
        # Finalize - usage section appears
        sticky.add_usage_example("bugfix.apply()")
        body = sticky._build_body(final=True)
        assert "💡 Usage" in body
        assert "```python" in body
        assert "Powered by [PraisonAI]" in body

    def test_elapsed_time_tracking(self):
        """Verify elapsed time is shown in progress bar."""
        from praisonai.cli.commands.github import StickyComment
        
        sticky = StickyComment(
            api_base="https://api.github.com",
            issue=999,
            token="fake",
            task_type="Task",
            title="Test",
            run_url="",
            repo_name="owner/repo"
        )
        
        sticky.set_todos([{"content": "Step 1", "status": "in_progress"}])
        
        # Wait a bit
        time.sleep(1.1)
        
        body = sticky._build_body()
        assert "⏱️" in body  # Clock icon
        # Should show at least 1m or 0m 1s
        assert "m" in body and "s" in body

    def test_clickable_file_links(self):
        """Verify file paths are clickable when repo info available."""
        from praisonai.cli.commands.github import StickyComment
        
        sticky = StickyComment(
            api_base="https://api.github.com",
            issue=111,
            token="fake",
            task_type="Issue",
            title="Test",
            run_url="",
            repo_name="MervinPraison/PraisonAI"
        )
        
        sticky.set_branch("feature/test")
        sticky.add_file_modified("src/main.py", "Main file")
        
        body = sticky._build_body(final=True)
        
        # File should be clickable link
        assert "https://github.com/MervinPraison/PraisonAI/blob/feature/test/src/main.py" in body


@pytest.mark.manual
class TestEnhancedIntegration:
    """Manual integration tests requiring real GitHub."""
    
    def test_live_comment_updates(self):
        """
        Manual test: Run triage and verify comment updates live.
        
        Steps:
        1. Create test issue
        2. Run: praisonai github triage --issue <NUM>
        3. Watch comment update in real-time
        4. Verify all sections appear progressively
        """
        pytest.skip("Manual test - requires real GitHub issue and API keys")
