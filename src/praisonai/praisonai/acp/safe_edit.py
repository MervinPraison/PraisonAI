"""
Safe Edit Pipeline for ACP.

Implements a propose → diff → approve → apply workflow for file edits.
Ensures no silent file writes - all changes require explicit approval.
"""

import difflib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EditStatus(str, Enum):
    """Status of an edit proposal."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    FAILED = "failed"


@dataclass
class EditProposal:
    """
    A proposed file edit with diff preview.
    
    Represents a change that has been proposed but not yet applied.
    """
    proposal_id: str
    file_path: Path
    original_content: str
    proposed_content: str
    description: str
    diff_lines: List[str] = field(default_factory=list)
    status: EditStatus = EditStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    approved_at: Optional[str] = None
    applied_at: Optional[str] = None
    error: Optional[str] = None
    
    def __post_init__(self):
        """Generate diff on creation."""
        if not self.diff_lines:
            self.diff_lines = self._generate_diff()
    
    def _generate_diff(self) -> List[str]:
        """Generate unified diff between original and proposed content."""
        original_lines = self.original_content.splitlines(keepends=True)
        proposed_lines = self.proposed_content.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            original_lines,
            proposed_lines,
            fromfile=f"a/{self.file_path.name}",
            tofile=f"b/{self.file_path.name}",
            lineterm=""
        )
        return list(diff)
    
    @property
    def diff_text(self) -> str:
        """Get diff as a single string."""
        return "\n".join(self.diff_lines)
    
    @property
    def is_new_file(self) -> bool:
        """Check if this is a new file creation."""
        return not self.original_content
    
    @property
    def is_deletion(self) -> bool:
        """Check if this is a file deletion."""
        return not self.proposed_content and bool(self.original_content)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "proposal_id": self.proposal_id,
            "file_path": str(self.file_path),
            "description": self.description,
            "status": self.status.value,
            "is_new_file": self.is_new_file,
            "is_deletion": self.is_deletion,
            "diff": self.diff_text,
            "created_at": self.created_at,
            "approved_at": self.approved_at,
            "applied_at": self.applied_at,
            "error": self.error,
        }


class SafeEditPipeline:
    """
    Safe file editing with diff preview and approval workflow.
    
    Workflow:
    1. propose_edit() - Create an edit proposal with diff
    2. show_diff() - Display the diff to user
    3. approve() / reject() - User decision
    4. apply_edit() - Apply approved edit
    
    ACP remains read-only by default. Writes only happen after explicit approval.
    """
    
    def __init__(
        self,
        workspace: Optional[Path] = None,
        auto_approve: bool = False,
        approval_callback: Optional[callable] = None,
    ):
        """
        Initialize safe edit pipeline.
        
        Args:
            workspace: Root workspace directory for path validation
            auto_approve: If True, auto-approve all edits (dangerous, for testing only)
            approval_callback: Optional callback for approval (async or sync)
        """
        self.workspace = Path(workspace) if workspace else Path.cwd()
        self.auto_approve = auto_approve
        self.approval_callback = approval_callback
        self._proposals: Dict[str, EditProposal] = {}
    
    def _validate_path(self, file_path: Path) -> Path:
        """
        Validate and resolve file path.
        
        Ensures path is within workspace and resolves to absolute path.
        """
        if not file_path.is_absolute():
            file_path = self.workspace / file_path
        
        resolved = file_path.resolve()
        
        # Security check: ensure path is within workspace
        try:
            resolved.relative_to(self.workspace.resolve())
        except ValueError:
            raise ValueError(f"Path {file_path} is outside workspace {self.workspace}")
        
        return resolved
    
    def propose_edit(
        self,
        file_path: Path,
        new_content: str,
        description: str,
    ) -> EditProposal:
        """
        Create an edit proposal with diff preview.
        
        Args:
            file_path: Path to file to edit
            new_content: Proposed new content
            description: Human-readable description of the change
            
        Returns:
            EditProposal with diff
        """
        resolved_path = self._validate_path(Path(file_path))
        
        # Read original content if file exists
        original_content = ""
        if resolved_path.exists():
            try:
                original_content = resolved_path.read_text()
            except Exception as e:
                logger.warning(f"Could not read {resolved_path}: {e}")
        
        # Create proposal
        proposal = EditProposal(
            proposal_id=str(uuid.uuid4())[:8],
            file_path=resolved_path,
            original_content=original_content,
            proposed_content=new_content,
            description=description,
        )
        
        self._proposals[proposal.proposal_id] = proposal
        logger.info(f"Created edit proposal {proposal.proposal_id} for {file_path}")
        
        return proposal
    
    def propose_create(
        self,
        file_path: Path,
        content: str,
        description: str,
    ) -> EditProposal:
        """
        Create a proposal for a new file.
        
        Args:
            file_path: Path for new file
            content: File content
            description: Description of the new file
            
        Returns:
            EditProposal for file creation
        """
        return self.propose_edit(file_path, content, description)
    
    def propose_delete(
        self,
        file_path: Path,
        description: str,
    ) -> EditProposal:
        """
        Create a proposal to delete a file.
        
        Args:
            file_path: Path to file to delete
            description: Reason for deletion
            
        Returns:
            EditProposal for file deletion
        """
        return self.propose_edit(file_path, "", description)
    
    def get_proposal(self, proposal_id: str) -> Optional[EditProposal]:
        """Get a proposal by ID."""
        return self._proposals.get(proposal_id)
    
    def list_proposals(self, status: Optional[EditStatus] = None) -> List[EditProposal]:
        """
        List all proposals, optionally filtered by status.
        
        Args:
            status: Optional status filter
            
        Returns:
            List of proposals
        """
        proposals = list(self._proposals.values())
        if status:
            proposals = [p for p in proposals if p.status == status]
        return proposals
    
    def approve(self, proposal_id: str) -> bool:
        """
        Approve an edit proposal.
        
        Args:
            proposal_id: ID of proposal to approve
            
        Returns:
            True if approved, False if not found or already processed
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            logger.warning(f"Proposal {proposal_id} not found")
            return False
        
        if proposal.status != EditStatus.PENDING:
            logger.warning(f"Proposal {proposal_id} is not pending (status: {proposal.status})")
            return False
        
        proposal.status = EditStatus.APPROVED
        proposal.approved_at = datetime.now().isoformat()
        logger.info(f"Approved proposal {proposal_id}")
        return True
    
    def reject(self, proposal_id: str, reason: Optional[str] = None) -> bool:
        """
        Reject an edit proposal.
        
        Args:
            proposal_id: ID of proposal to reject
            reason: Optional rejection reason
            
        Returns:
            True if rejected, False if not found or already processed
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            logger.warning(f"Proposal {proposal_id} not found")
            return False
        
        if proposal.status != EditStatus.PENDING:
            logger.warning(f"Proposal {proposal_id} is not pending (status: {proposal.status})")
            return False
        
        proposal.status = EditStatus.REJECTED
        proposal.error = reason
        logger.info(f"Rejected proposal {proposal_id}: {reason}")
        return True
    
    def apply_edit(self, proposal_id: str) -> bool:
        """
        Apply an approved edit.
        
        Args:
            proposal_id: ID of approved proposal to apply
            
        Returns:
            True if applied successfully, False otherwise
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            logger.error(f"Proposal {proposal_id} not found")
            return False
        
        if proposal.status != EditStatus.APPROVED:
            logger.error(f"Proposal {proposal_id} is not approved (status: {proposal.status})")
            return False
        
        try:
            if proposal.is_deletion:
                # Delete file
                if proposal.file_path.exists():
                    proposal.file_path.unlink()
                    logger.info(f"Deleted {proposal.file_path}")
            else:
                # Create parent directories if needed
                proposal.file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Write new content
                proposal.file_path.write_text(proposal.proposed_content)
                logger.info(f"Applied edit to {proposal.file_path}")
            
            proposal.status = EditStatus.APPLIED
            proposal.applied_at = datetime.now().isoformat()
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply proposal {proposal_id}: {e}")
            proposal.status = EditStatus.FAILED
            proposal.error = str(e)
            return False
    
    def propose_and_apply(
        self,
        file_path: Path,
        new_content: str,
        description: str,
    ) -> EditProposal:
        """
        Convenience method: propose, auto-approve if enabled, and apply.
        
        Only applies if auto_approve is True or approval_callback returns True.
        
        Args:
            file_path: Path to file
            new_content: New content
            description: Description
            
        Returns:
            EditProposal (may be pending, approved, or applied)
        """
        proposal = self.propose_edit(file_path, new_content, description)
        
        if self.auto_approve:
            self.approve(proposal.proposal_id)
            self.apply_edit(proposal.proposal_id)
        elif self.approval_callback:
            try:
                if self.approval_callback(proposal):
                    self.approve(proposal.proposal_id)
                    self.apply_edit(proposal.proposal_id)
                else:
                    self.reject(proposal.proposal_id, "Rejected by callback")
            except Exception as e:
                logger.error(f"Approval callback failed: {e}")
                proposal.error = str(e)
        
        return proposal
    
    def format_diff_for_display(self, proposal: EditProposal) -> str:
        """
        Format diff for terminal display with colors.
        
        Args:
            proposal: Edit proposal
            
        Returns:
            Formatted diff string with ANSI colors
        """
        lines = []
        lines.append(f"📝 Edit Proposal: {proposal.proposal_id}")
        lines.append(f"   File: {proposal.file_path}")
        lines.append(f"   Description: {proposal.description}")
        lines.append(f"   Status: {proposal.status.value}")
        lines.append("")
        
        if proposal.is_new_file:
            lines.append("   [NEW FILE]")
        elif proposal.is_deletion:
            lines.append("   [DELETE FILE]")
        
        lines.append("   --- Diff ---")
        for line in proposal.diff_lines:
            if line.startswith("+") and not line.startswith("+++"):
                lines.append(f"   \033[32m{line}\033[0m")  # Green for additions
            elif line.startswith("-") and not line.startswith("---"):
                lines.append(f"   \033[31m{line}\033[0m")  # Red for deletions
            elif line.startswith("@@"):
                lines.append(f"   \033[36m{line}\033[0m")  # Cyan for line numbers
            else:
                lines.append(f"   {line}")
        
        return "\n".join(lines)
    
    def clear_proposals(self, status: Optional[EditStatus] = None) -> int:
        """
        Clear proposals, optionally filtered by status.
        
        Args:
            status: Optional status filter (None = clear all)
            
        Returns:
            Number of proposals cleared
        """
        if status is None:
            count = len(self._proposals)
            self._proposals.clear()
        else:
            to_remove = [pid for pid, p in self._proposals.items() if p.status == status]
            for pid in to_remove:
                del self._proposals[pid]
            count = len(to_remove)
        
        logger.info(f"Cleared {count} proposals")
        return count


# Global pipeline instance for ACP
_safe_edit_pipeline: Optional[SafeEditPipeline] = None


def get_safe_edit_pipeline(workspace: Optional[Path] = None) -> SafeEditPipeline:
    """Get or create the global safe edit pipeline."""
    global _safe_edit_pipeline
    if _safe_edit_pipeline is None:
        _safe_edit_pipeline = SafeEditPipeline(workspace=workspace)
    return _safe_edit_pipeline
