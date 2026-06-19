"""
Session reset policies for automatic session lifecycle management.

Provides configurable policies for automatically resetting user sessions
based on idle time and/or scheduled times.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time as datetime_time
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
            
            # Calculate time since last potential reset
            # If we're past today's reset time and haven't reset since then
            if current_datetime >= reset_time_today:
                # Time since today's scheduled reset (in seconds)
                seconds_since_scheduled = (current_datetime - reset_time_today).total_seconds()
                # Time since last actual reset
                seconds_since_last_reset = now - last_reset
                
                # If last reset was before the scheduled time
                if seconds_since_last_reset > seconds_since_scheduled:
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