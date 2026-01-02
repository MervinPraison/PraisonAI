"""
Unit tests for ACP Safe Edit Pipeline.
"""

import tempfile
import pytest
from pathlib import Path

from praisonai.acp.safe_edit import (
    EditProposal,
    EditStatus,
    SafeEditPipeline,
    get_safe_edit_pipeline,
)


class TestEditProposal:
    """Tests for EditProposal class."""
    
    def test_create_proposal(self):
        """Test creating an edit proposal."""
        proposal = EditProposal(
            proposal_id="test-123",
            file_path=Path("/tmp/test.txt"),
            original_content="Hello",
            proposed_content="Hello, World!",
            description="Add greeting",
        )
        
        assert proposal.proposal_id == "test-123"
        assert proposal.status == EditStatus.PENDING
        assert len(proposal.diff_lines) > 0
    
    def test_diff_generation(self):
        """Test diff is generated correctly."""
        proposal = EditProposal(
            proposal_id="test-123",
            file_path=Path("/tmp/test.txt"),
            original_content="line1\nline2\nline3",
            proposed_content="line1\nmodified\nline3",
            description="Modify line 2",
        )
        
        diff_text = proposal.diff_text
        assert "-line2" in diff_text
        assert "+modified" in diff_text
    
    def test_is_new_file(self):
        """Test new file detection."""
        proposal = EditProposal(
            proposal_id="test-123",
            file_path=Path("/tmp/new.txt"),
            original_content="",
            proposed_content="New content",
            description="Create new file",
        )
        
        assert proposal.is_new_file is True
        assert proposal.is_deletion is False
    
    def test_is_deletion(self):
        """Test deletion detection."""
        proposal = EditProposal(
            proposal_id="test-123",
            file_path=Path("/tmp/delete.txt"),
            original_content="Content to delete",
            proposed_content="",
            description="Delete file",
        )
        
        assert proposal.is_deletion is True
        assert proposal.is_new_file is False
    
    def test_to_dict(self):
        """Test converting proposal to dictionary."""
        proposal = EditProposal(
            proposal_id="test-123",
            file_path=Path("/tmp/test.txt"),
            original_content="Hello",
            proposed_content="Hello, World!",
            description="Add greeting",
        )
        
        data = proposal.to_dict()
        
        assert data["proposal_id"] == "test-123"
        assert data["description"] == "Add greeting"
        assert data["status"] == "pending"
        assert "diff" in data


class TestSafeEditPipeline:
    """Tests for SafeEditPipeline class."""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def pipeline(self, temp_workspace):
        """Create a pipeline with temp workspace."""
        return SafeEditPipeline(workspace=temp_workspace)
    
    def test_create_pipeline(self, temp_workspace):
        """Test creating a pipeline."""
        pipeline = SafeEditPipeline(workspace=temp_workspace)
        
        assert pipeline.workspace == temp_workspace
        assert pipeline.auto_approve is False
    
    def test_propose_edit(self, pipeline, temp_workspace):
        """Test proposing an edit."""
        # Create a file to edit
        test_file = temp_workspace / "test.txt"
        test_file.write_text("Original content")
        
        proposal = pipeline.propose_edit(
            file_path=test_file,
            new_content="Modified content",
            description="Test edit",
        )
        
        assert proposal.status == EditStatus.PENDING
        assert proposal.original_content == "Original content"
        assert proposal.proposed_content == "Modified content"
    
    def test_propose_create(self, pipeline, temp_workspace):
        """Test proposing a new file."""
        new_file = temp_workspace / "new.txt"
        
        proposal = pipeline.propose_create(
            file_path=new_file,
            content="New file content",
            description="Create new file",
        )
        
        assert proposal.is_new_file is True
        assert proposal.status == EditStatus.PENDING
    
    def test_propose_delete(self, pipeline, temp_workspace):
        """Test proposing a deletion."""
        # Create a file to delete
        test_file = temp_workspace / "delete.txt"
        test_file.write_text("Content to delete")
        
        proposal = pipeline.propose_delete(
            file_path=test_file,
            description="Delete file",
        )
        
        assert proposal.is_deletion is True
        assert proposal.status == EditStatus.PENDING
    
    def test_approve_proposal(self, pipeline, temp_workspace):
        """Test approving a proposal."""
        test_file = temp_workspace / "test.txt"
        test_file.write_text("Original")
        
        proposal = pipeline.propose_edit(
            file_path=test_file,
            new_content="Modified",
            description="Test",
        )
        
        result = pipeline.approve(proposal.proposal_id)
        
        assert result is True
        assert proposal.status == EditStatus.APPROVED
        assert proposal.approved_at is not None
    
    def test_reject_proposal(self, pipeline, temp_workspace):
        """Test rejecting a proposal."""
        test_file = temp_workspace / "test.txt"
        test_file.write_text("Original")
        
        proposal = pipeline.propose_edit(
            file_path=test_file,
            new_content="Modified",
            description="Test",
        )
        
        result = pipeline.reject(proposal.proposal_id, "Not needed")
        
        assert result is True
        assert proposal.status == EditStatus.REJECTED
        assert proposal.error == "Not needed"
    
    def test_apply_approved_edit(self, pipeline, temp_workspace):
        """Test applying an approved edit."""
        test_file = temp_workspace / "test.txt"
        test_file.write_text("Original content")
        
        proposal = pipeline.propose_edit(
            file_path=test_file,
            new_content="Modified content",
            description="Test",
        )
        
        pipeline.approve(proposal.proposal_id)
        result = pipeline.apply_edit(proposal.proposal_id)
        
        assert result is True
        assert proposal.status == EditStatus.APPLIED
        assert test_file.read_text() == "Modified content"
    
    def test_apply_unapproved_fails(self, pipeline, temp_workspace):
        """Test that applying unapproved edit fails."""
        test_file = temp_workspace / "test.txt"
        test_file.write_text("Original")
        
        proposal = pipeline.propose_edit(
            file_path=test_file,
            new_content="Modified",
            description="Test",
        )
        
        # Don't approve
        result = pipeline.apply_edit(proposal.proposal_id)
        
        assert result is False
        assert test_file.read_text() == "Original"  # Unchanged
    
    def test_apply_creates_new_file(self, pipeline, temp_workspace):
        """Test applying a new file creation."""
        new_file = temp_workspace / "subdir" / "new.txt"
        
        proposal = pipeline.propose_create(
            file_path=new_file,
            content="New content",
            description="Create file",
        )
        
        pipeline.approve(proposal.proposal_id)
        result = pipeline.apply_edit(proposal.proposal_id)
        
        assert result is True
        assert new_file.exists()
        assert new_file.read_text() == "New content"
    
    def test_apply_deletes_file(self, pipeline, temp_workspace):
        """Test applying a file deletion."""
        test_file = temp_workspace / "delete.txt"
        test_file.write_text("To delete")
        
        proposal = pipeline.propose_delete(
            file_path=test_file,
            description="Delete",
        )
        
        pipeline.approve(proposal.proposal_id)
        result = pipeline.apply_edit(proposal.proposal_id)
        
        assert result is True
        assert not test_file.exists()
    
    def test_path_outside_workspace_rejected(self, pipeline, temp_workspace):
        """Test that paths outside workspace are rejected."""
        with pytest.raises(ValueError, match="outside workspace"):
            pipeline.propose_edit(
                file_path=Path("/etc/passwd"),
                new_content="hacked",
                description="Bad edit",
            )
    
    def test_list_proposals(self, pipeline, temp_workspace):
        """Test listing proposals."""
        test_file = temp_workspace / "test.txt"
        test_file.write_text("Original")
        
        pipeline.propose_edit(test_file, "Edit 1", "First")
        pipeline.propose_edit(test_file, "Edit 2", "Second")
        
        proposals = pipeline.list_proposals()
        
        assert len(proposals) == 2
    
    def test_list_proposals_by_status(self, pipeline, temp_workspace):
        """Test listing proposals filtered by status."""
        test_file = temp_workspace / "test.txt"
        test_file.write_text("Original")
        
        p1 = pipeline.propose_edit(test_file, "Edit 1", "First")
        pipeline.propose_edit(test_file, "Edit 2", "Second")
        
        pipeline.approve(p1.proposal_id)
        
        pending = pipeline.list_proposals(status=EditStatus.PENDING)
        approved = pipeline.list_proposals(status=EditStatus.APPROVED)
        
        assert len(pending) == 1
        assert len(approved) == 1
    
    def test_auto_approve_mode(self, temp_workspace):
        """Test auto-approve mode."""
        pipeline = SafeEditPipeline(workspace=temp_workspace, auto_approve=True)
        
        test_file = temp_workspace / "test.txt"
        test_file.write_text("Original")
        
        proposal = pipeline.propose_and_apply(
            file_path=test_file,
            new_content="Auto-modified",
            description="Auto edit",
        )
        
        assert proposal.status == EditStatus.APPLIED
        assert test_file.read_text() == "Auto-modified"
    
    def test_approval_callback(self, temp_workspace):
        """Test approval callback."""
        approved_proposals = []
        
        def callback(proposal):
            approved_proposals.append(proposal.proposal_id)
            return True
        
        pipeline = SafeEditPipeline(
            workspace=temp_workspace,
            approval_callback=callback,
        )
        
        test_file = temp_workspace / "test.txt"
        test_file.write_text("Original")
        
        proposal = pipeline.propose_and_apply(
            file_path=test_file,
            new_content="Callback-modified",
            description="Callback edit",
        )
        
        assert proposal.proposal_id in approved_proposals
        assert proposal.status == EditStatus.APPLIED
    
    def test_clear_proposals(self, pipeline, temp_workspace):
        """Test clearing proposals."""
        test_file = temp_workspace / "test.txt"
        test_file.write_text("Original")
        
        pipeline.propose_edit(test_file, "Edit 1", "First")
        pipeline.propose_edit(test_file, "Edit 2", "Second")
        
        count = pipeline.clear_proposals()
        
        assert count == 2
        assert len(pipeline.list_proposals()) == 0
    
    def test_format_diff_for_display(self, pipeline, temp_workspace):
        """Test formatting diff for display."""
        test_file = temp_workspace / "test.txt"
        test_file.write_text("line1\nline2\nline3")
        
        proposal = pipeline.propose_edit(
            file_path=test_file,
            new_content="line1\nmodified\nline3",
            description="Modify line 2",
        )
        
        display = pipeline.format_diff_for_display(proposal)
        
        assert "Edit Proposal" in display
        assert "Modify line 2" in display
        assert "Diff" in display


class TestGlobalPipeline:
    """Tests for global pipeline instance."""
    
    def test_get_safe_edit_pipeline(self):
        """Test getting global pipeline."""
        pipeline1 = get_safe_edit_pipeline()
        pipeline2 = get_safe_edit_pipeline()
        
        # Should return same instance
        assert pipeline1 is pipeline2
