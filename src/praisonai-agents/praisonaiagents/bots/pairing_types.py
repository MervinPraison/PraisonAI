"""
Pairing types and protocols for bot user approval.

Contains lightweight types and protocols for the pairing approval system.
Heavy implementations are in the wrapper package.
"""

from dataclasses import dataclass
from typing import Literal, Optional

# Policy for handling unknown users
UnknownUserPolicy = Literal["deny", "pair", "allow"]


@dataclass
class PairingReply:
    """Reply data for pairing approval requests."""
    
    user_name: str
    user_id: str
    channel: str
    code: str
    message: str = ""
    
    def __post_init__(self):
        if not self.message:
            self.message = f"User {self.user_name} wants to chat. Approve access?"


@dataclass
class PairingApprovalResult:
    """Result of a pairing approval action."""
    
    success: bool
    message: str
    user_id: Optional[str] = None
    channel: Optional[str] = None