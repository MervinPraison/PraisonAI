"""
Push notification models for PraisonAI Agents.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ChannelMessage:
    """A user-friendly wrapper around a push channel message.

    Attributes:
        channel: Channel name the message was received on
        data: Message payload
        event_id: Unique event identifier
        timestamp: When the event was created
        source: Source client ID (who sent it)
    """

    channel: str
    data: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    source: Optional[str] = None

    @classmethod
    def from_event_dict(cls, event_dict: Dict[str, Any]) -> "ChannelMessage":
        """Create from a raw gateway event dictionary."""
        return cls(
            channel=event_dict.get("channel", ""),
            data=event_dict.get("data", {}),
            event_id=event_dict.get("event_id", str(uuid.uuid4())),
            timestamp=event_dict.get("timestamp", time.time()),
            source=event_dict.get("source"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "channel": self.channel,
            "data": self.data,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "source": self.source,
        }
