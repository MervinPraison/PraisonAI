"""
Model Failover for PraisonAI Agents.

Provides auth profile management and automatic failover between
LLM providers when rate limits or errors occur.

This module is lightweight and protocol-driven.
Heavy implementations live in the praisonai wrapper.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    runtime_checkable,
)

logger = logging.getLogger(__name__)


class ProviderStatus(str, Enum):
    """Status of an LLM provider."""
    
    AVAILABLE = "available"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class AuthProfile:
    """Authentication profile for an LLM provider.
    
    Attributes:
        name: Profile name for identification
        provider: Provider name (openai, anthropic, google, etc.)
        api_key: API key for authentication
        base_url: Optional base URL override
        model: Default model for this profile
        priority: Priority for failover (lower = higher priority)
        rate_limit_rpm: Requests per minute limit
        rate_limit_tpm: Tokens per minute limit
        status: Current status
        last_error: Last error message
        last_error_time: Timestamp of last error
        cooldown_until: Timestamp until which this profile is in cooldown
        metadata: Additional provider-specific configuration
    """
    
    name: str
    provider: str
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    priority: int = 0
    rate_limit_rpm: Optional[int] = None
    rate_limit_tpm: Optional[int] = None
    status: ProviderStatus = ProviderStatus.AVAILABLE
    last_error: Optional[str] = None
    last_error_time: Optional[float] = None
    cooldown_until: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (hides sensitive data)."""
        return {
            "name": self.name,
            "provider": self.provider,
            "api_key": "***" + self.api_key[-4:] if self.api_key else None,
            "base_url": self.base_url,
            "model": self.model,
            "priority": self.priority,
            "rate_limit_rpm": self.rate_limit_rpm,
            "rate_limit_tpm": self.rate_limit_tpm,
            "status": self.status.value,
            "last_error": self.last_error,
            "last_error_time": self.last_error_time,
            "cooldown_until": self.cooldown_until,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuthProfile":
        """Create from dictionary."""
        status = data.get("status", "available")
        try:
            status = ProviderStatus(status)
        except ValueError:
            status = ProviderStatus.AVAILABLE
        
        return cls(
            name=data.get("name", "default"),
            provider=data.get("provider", "openai"),
            api_key=data.get("api_key", ""),
            base_url=data.get("base_url"),
            model=data.get("model"),
            priority=data.get("priority", 0),
            rate_limit_rpm=data.get("rate_limit_rpm"),
            rate_limit_tpm=data.get("rate_limit_tpm"),
            status=status,
            last_error=data.get("last_error"),
            last_error_time=data.get("last_error_time"),
            cooldown_until=data.get("cooldown_until"),
            metadata=data.get("metadata", {}),
        )
    
    @property
    def is_available(self) -> bool:
        """Check if this profile is currently available."""
        if self.status == ProviderStatus.DISABLED:
            return False
        if self.cooldown_until and time.time() < self.cooldown_until:
            return False
        return True
    
    def mark_rate_limited(self, cooldown_seconds: float = 60.0) -> None:
        """Mark this profile as rate limited."""
        self.status = ProviderStatus.RATE_LIMITED
        self.cooldown_until = time.time() + cooldown_seconds
        self.last_error = "Rate limited"
        self.last_error_time = time.time()
    
    def mark_error(self, error: str, cooldown_seconds: float = 30.0) -> None:
        """Mark this profile as having an error."""
        self.status = ProviderStatus.ERROR
        self.cooldown_until = time.time() + cooldown_seconds
        self.last_error = error
        self.last_error_time = time.time()
    
    def reset(self) -> None:
        """Reset this profile to available status."""
        self.status = ProviderStatus.AVAILABLE
        self.cooldown_until = None
        self.last_error = None
        self.last_error_time = None


@runtime_checkable
class FailoverProtocol(Protocol):
    """Protocol for failover management."""
    
    def get_next_profile(self) -> Optional[AuthProfile]:
        """Get the next available profile."""
        ...
    
    def mark_failure(self, profile: AuthProfile, error: str) -> None:
        """Mark a profile as failed."""
        ...
    
    def mark_success(self, profile: AuthProfile) -> None:
        """Mark a profile as successful."""
        ...


@dataclass
class FailoverConfig:
    """Configuration for failover behavior.
    
    Attributes:
        max_retries: Maximum retry attempts per request
        retry_delay: Base delay between retries (seconds)
        exponential_backoff: Whether to use exponential backoff
        max_retry_delay: Maximum retry delay (seconds)
        cooldown_on_rate_limit: Cooldown duration for rate limits (seconds)
        cooldown_on_error: Cooldown duration for errors (seconds)
        rotate_on_success: Whether to rotate profiles on success
    """
    
    max_retries: int = 3
    retry_delay: float = 1.0
    exponential_backoff: bool = True
    max_retry_delay: float = 60.0
    cooldown_on_rate_limit: float = 60.0
    cooldown_on_error: float = 30.0
    rotate_on_success: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "exponential_backoff": self.exponential_backoff,
            "max_retry_delay": self.max_retry_delay,
            "cooldown_on_rate_limit": self.cooldown_on_rate_limit,
            "cooldown_on_error": self.cooldown_on_error,
            "rotate_on_success": self.rotate_on_success,
        }


class FailoverManager:
    """Manages failover between multiple LLM auth profiles.
    
    Provides automatic failover when rate limits or errors occur,
    with configurable retry behavior and cooldown periods.
    
    Example:
        manager = FailoverManager()
        manager.add_profile(AuthProfile(
            name="openai-primary",
            provider="openai",
            api_key="sk-...",
            priority=0,
        ))
        manager.add_profile(AuthProfile(
            name="openai-backup",
            provider="openai",
            api_key="sk-...",
            priority=1,
        ))
        
        # Get next available profile
        profile = manager.get_next_profile()
        
        # On failure
        manager.mark_failure(profile, "Rate limit exceeded")
        
        # Get next profile (will return backup)
        profile = manager.get_next_profile()
    """
    
    def __init__(self, config: Optional[FailoverConfig] = None):
        """Initialize the failover manager.
        
        Args:
            config: Failover configuration
        """
        self.config = config or FailoverConfig()
        self._profiles: List[AuthProfile] = []
        self._current_index: int = 0
        self._on_failover_callbacks: List[Callable[[AuthProfile, AuthProfile], None]] = []
    
    def add_profile(self, profile: AuthProfile) -> None:
        """Add an auth profile.
        
        Args:
            profile: The profile to add
        """
        self._profiles.append(profile)
        self._profiles.sort(key=lambda p: p.priority)
    
    def remove_profile(self, name: str) -> bool:
        """Remove a profile by name.
        
        Args:
            name: Profile name to remove
            
        Returns:
            True if removed, False if not found
        """
        for i, profile in enumerate(self._profiles):
            if profile.name == name:
                self._profiles.pop(i)
                return True
        return False
    
    def get_profile(self, name: str) -> Optional[AuthProfile]:
        """Get a profile by name.
        
        Args:
            name: Profile name
            
        Returns:
            The profile or None if not found
        """
        for profile in self._profiles:
            if profile.name == name:
                return profile
        return None
    
    def list_profiles(self) -> List[AuthProfile]:
        """List all profiles.
        
        Returns:
            List of all profiles
        """
        return list(self._profiles)
    
    def get_next_profile(self) -> Optional[AuthProfile]:
        """Get the next available profile.
        
        Returns profiles in priority order, skipping those that are
        rate limited or in cooldown.
        
        Returns:
            The next available profile, or None if all are unavailable
        """
        if not self._profiles:
            return None
        
        # First, check if any cooldowns have expired
        current_time = time.time()
        for profile in self._profiles:
            if profile.cooldown_until and current_time >= profile.cooldown_until:
                profile.reset()
        
        # Find first available profile
        for profile in self._profiles:
            if profile.is_available:
                return profile
        
        # If none available, return the one with shortest remaining cooldown
        available_profiles = [p for p in self._profiles if p.status != ProviderStatus.DISABLED]
        if available_profiles:
            return min(
                available_profiles,
                key=lambda p: p.cooldown_until or 0
            )
        
        return None
    
    def mark_failure(
        self,
        profile: AuthProfile,
        error: str,
        is_rate_limit: bool = False,
    ) -> None:
        """Mark a profile as failed.
        
        Args:
            profile: The profile that failed
            error: Error message
            is_rate_limit: Whether this is a rate limit error
        """
        if is_rate_limit:
            profile.mark_rate_limited(self.config.cooldown_on_rate_limit)
            logger.warning(
                f"Profile '{profile.name}' rate limited, "
                f"cooldown for {self.config.cooldown_on_rate_limit}s"
            )
        else:
            profile.mark_error(error, self.config.cooldown_on_error)
            logger.warning(
                f"Profile '{profile.name}' error: {error}, "
                f"cooldown for {self.config.cooldown_on_error}s"
            )
        
        # Notify callbacks
        next_profile = self.get_next_profile()
        if next_profile and next_profile != profile:
            for callback in self._on_failover_callbacks:
                try:
                    callback(profile, next_profile)
                except Exception as e:
                    logger.error(f"Failover callback error: {e}")
    
    def mark_success(self, profile: AuthProfile) -> None:
        """Mark a profile as successful.
        
        Args:
            profile: The profile that succeeded
        """
        if profile.status != ProviderStatus.AVAILABLE:
            profile.reset()
            logger.info(f"Profile '{profile.name}' recovered")
    
    def on_failover(
        self,
        callback: Callable[[AuthProfile, AuthProfile], None],
    ) -> None:
        """Register a callback for failover events.
        
        Args:
            callback: Function called with (failed_profile, new_profile)
        """
        self._on_failover_callbacks.append(callback)
    
    def get_retry_delay(self, attempt: int) -> float:
        """Calculate retry delay for an attempt.
        
        Args:
            attempt: Attempt number (0-indexed)
            
        Returns:
            Delay in seconds
        """
        if self.config.exponential_backoff:
            delay = self.config.retry_delay * (2 ** attempt)
        else:
            delay = self.config.retry_delay
        
        return min(delay, self.config.max_retry_delay)
    
    def status(self) -> Dict[str, Any]:
        """Get failover manager status.
        
        Returns:
            Status information
        """
        available = sum(1 for p in self._profiles if p.is_available)
        return {
            "total_profiles": len(self._profiles),
            "available_profiles": available,
            "profiles": [p.to_dict() for p in self._profiles],
            "config": self.config.to_dict(),
        }
    
    def reset_all(self) -> None:
        """Reset all profiles to available status."""
        for profile in self._profiles:
            profile.reset()
