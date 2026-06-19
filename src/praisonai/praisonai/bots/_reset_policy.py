"""
Session reset policies for automatic session lifecycle management.

Provides configurable policies for automatically resetting user sessions
based on idle time and/or scheduled times.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionResetPolicy:
    """Policy for automatic session reset.
    
    Supports idle-based and scheduled resets, or both combined.
    
    Args:
        mode: Reset mode - "none", "idle", "daily", or "both"
        idle_minutes: Reset after N minutes of inactivity (when mode includes idle)
        at_hour: Daily reset hour 0-23 (when mode includes daily)
    """
    mode: str = "none"
    idle_minutes: int = 60
    at_hour: Optional[int] = None
    
    def __post_init__(self):
        """Validate policy configuration."""
        valid_modes = {"none", "idle", "daily", "both"}
        if self.mode not in valid_modes:
            raise ValueError(
                f"Invalid reset mode '{self.mode}'. "
                f"Must be one of: {', '.join(sorted(valid_modes))}"
            )
        
        if self.idle_minutes < 1:
            raise ValueError("idle_minutes must be at least 1")
        
        if self.at_hour is not None and not (0 <= self.at_hour <= 23):
            raise ValueError("at_hour must be between 0 and 23")
        
        # Validate configuration consistency
        if self.mode in ("daily", "both") and self.at_hour is None:
            raise ValueError(f"at_hour is required when mode is '{self.mode}'")
    
    def should_reset(
        self,
        last_activity: float,
        last_reset: float,
        now: float,
        current_datetime: Optional[datetime] = None
    ) -> bool:
        """Check if session should be reset based on policy.
        
        Args:
            last_activity: Timestamp of last user activity (monotonic time)
            last_reset: Timestamp of last reset (monotonic time)
            now: Current timestamp (monotonic time)
            current_datetime: Current datetime for scheduled reset checks
        
        Returns:
            True if session should be reset, False otherwise
        """
        if self.mode == "none":
            return False
        
        # Check idle timeout
        if self.mode in ("idle", "both"):
            idle_seconds = now - last_activity
            if idle_seconds >= self.idle_minutes * 60:
                logger.debug(
                    "Session idle for %.1f minutes (threshold: %d)",
                    idle_seconds / 60,
                    self.idle_minutes
                )
                return True
        
        # Check daily scheduled reset
        if self.mode in ("daily", "both") and self.at_hour is not None:
            if current_datetime is None:
                current_datetime = datetime.now()
            
            # Get the last reset hour
            reset_hour = self.at_hour
            reset_time_today = current_datetime.replace(
                hour=reset_hour,
                minute=0,
                second=0,
                microsecond=0
            )
            
            # Check the most recent scheduled boundary
            # If current time is past today's reset time, use today's reset time
            # Otherwise, use yesterday's reset time
            last_scheduled = (
                reset_time_today
                if current_datetime >= reset_time_today
                else reset_time_today - timedelta(days=1)
            )
            
            # Calculate seconds since the most recent scheduled reset
            seconds_since_scheduled = (current_datetime - last_scheduled).total_seconds()
            seconds_since_last_reset = now - last_reset
            
            # If we haven't reset since the most recent scheduled time
            if seconds_since_last_reset >= seconds_since_scheduled:
                logger.debug(
                    "Daily reset triggered (hour=%d, last_reset=%.1f mins ago)",
                    reset_hour,
                    seconds_since_last_reset / 60
                )
                return True
        
        return False
    
    @classmethod
    def from_dict(cls, data: dict) -> SessionResetPolicy:
        """Create policy from dictionary (e.g., from YAML config)."""
        return cls(
            mode=data.get("mode", "none"),
            idle_minutes=data.get("idle_minutes", 60),
            at_hour=data.get("at_hour")
        )