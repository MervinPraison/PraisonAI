"""
Home channel registry and delivery resolver for PraisonAI gateway.

Provides ergonomic proactive/scheduled delivery routing with home channels
and delivery tokens (origin, platform names, all).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from praisonaiagents.gateway.protocols import (
    DeliveryResolverProtocol,
    HomeChannelRegistryProtocol,
)
from praisonaiagents.scheduler.models import DeliveryTarget

logger = logging.getLogger(__name__)


class HomeChannelRegistry(HomeChannelRegistryProtocol):
    """Registry for managing default delivery targets per platform.
    
    Persists home channels to a JSON file for durability across restarts.
    """
    
    def __init__(self, persist_path: Optional[Path] = None):
        """Initialize the home channel registry.
        
        Args:
            persist_path: Path to persist home channels. Defaults to
                         ~/.praisonai/state/home_channels.json
        """
        if persist_path is None:
            state_dir = Path.home() / ".praisonai" / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            persist_path = state_dir / "home_channels.json"
        
        self._persist_path = persist_path
        self._home_channels: Dict[str, Tuple[str, Optional[str]]] = {}
        self._load()
    
    def _load(self) -> None:
        """Load home channels from persistent storage."""
        if self._persist_path.exists():
            try:
                with open(self._persist_path, "r") as f:
                    data = json.load(f)
                    for platform, channel_data in data.items():
                        if isinstance(channel_data, dict):
                            chat_id = channel_data.get("chat_id", "")
                            thread_id = channel_data.get("thread_id")
                            self._home_channels[platform] = (chat_id, thread_id)
                logger.info(
                    "Loaded %d home channels from %s",
                    len(self._home_channels),
                    self._persist_path,
                )
            except Exception as e:
                logger.warning("Failed to load home channels: %s", e)
    
    def _save(self) -> None:
        """Save home channels to persistent storage."""
        try:
            data = {}
            for platform, (chat_id, thread_id) in self._home_channels.items():
                data[platform] = {
                    "chat_id": chat_id,
                    "thread_id": thread_id,
                }
            
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._persist_path, "w") as f:
                json.dump(data, f, indent=2)
            
            logger.debug("Saved %d home channels to %s", len(data), self._persist_path)
        except Exception as e:
            logger.error("Failed to save home channels: %s", e)
    
    def set_home(
        self,
        platform: str,
        chat_id: str,
        thread_id: Optional[str] = None
    ) -> None:
        """Set the home channel for a platform.
        
        Args:
            platform: Platform name (e.g., "telegram", "slack", "discord")
            chat_id: Platform-specific chat/channel ID
            thread_id: Optional thread ID for threaded platforms
        """
        self._home_channels[platform] = (chat_id, thread_id)
        self._save()
        logger.info(
            "Set home channel for %s",
            platform,
        )
        logger.debug(
            "Home channel details for %s: chat_id=%s, thread_id=%s",
            platform, chat_id, thread_id,
        )
    
    def get_home(self, platform: str) -> Optional[Tuple[str, Optional[str]]]:
        """Get the home channel for a platform.
        
        Args:
            platform: Platform name to look up
            
        Returns:
            Tuple of (chat_id, thread_id) if set, None otherwise
        """
        return self._home_channels.get(platform)
    
    def platforms_with_home(self) -> List[str]:
        """List all platforms that have a home channel configured.
        
        Returns:
            List of platform names with home channels
        """
        return list(self._home_channels.keys())


class DeliveryResolver(DeliveryResolverProtocol):
    """Resolver for delivery routing tokens.
    
    Resolves tokens like "origin", "telegram", "all" to concrete delivery
    targets at fire time.
    """
    
    def __init__(
        self,
        home_registry: HomeChannelRegistryProtocol,
        *,
        directory: Optional[Any] = None,
    ):
        """Initialize the delivery resolver.
        
        Args:
            home_registry: Registry for looking up home channels.
            directory: Optional channel directory (e.g. a
                ``praisonai.bots.delivery.ChannelDirectory``) exposing
                ``resolve_alias(name) -> Optional[(platform, channel_id)]``.
                When supplied, friendly aliases/names can be used as delivery
                tokens. Resolution falls back to the single home channel for
                full backward compatibility when no alias matches.
        """
        self._home_registry = home_registry
        self._directory = directory
    
    def _resolve_alias(self, token: str) -> Optional[DeliveryTarget]:
        """Resolve a friendly alias/name via the optional channel directory.
        
        Returns a concrete ``DeliveryTarget`` when the directory knows the
        alias, otherwise ``None`` so the caller falls through to the
        unresolved-token warning and returns an empty list.
        """
        if self._directory is None:
            return None
        resolve_alias = getattr(self._directory, "resolve_alias", None)
        if not callable(resolve_alias):
            return None
        try:
            resolved = resolve_alias(token)
        except Exception as e:
            logger.warning("Channel directory alias lookup failed for %s: %s", token, e)
            return None
        if not resolved:
            return None
        try:
            platform, chat_id = resolved
        except (TypeError, ValueError) as e:
            logger.warning(
                "Channel directory alias lookup returned invalid target for %s: %s",
                token, e,
            )
            return None
        return DeliveryTarget(
            channel=platform,
            channel_id=chat_id,
            thread_id=None,
        )
    
    def resolve(
        self,
        token: str,
        *,
        origin: Optional[DeliveryTarget] = None
    ) -> List[DeliveryTarget]:
        """Resolve a routing token to concrete delivery targets.
        
        Token formats:
        - "origin": Reply to the chat where the job was created (requires origin)
        - "<platform>": That platform's home channel
        - "<platform>:<chat_id>[:<thread_id>]": Explicit target
        - "<alias>": Friendly name from the channel directory (if configured)
        - "all": Fan-out to every connected platform with a home channel
        
        Args:
            token: Routing token to resolve
            origin: Original delivery target (for "origin" token)
            
        Returns:
            List of concrete delivery targets
        """
        if not token:
            return []
        
        # Handle "origin" token
        if token == "origin":
            if origin is None:
                logger.warning("Cannot resolve 'origin' token without origin target")
                return []
            return [origin]
        
        # Handle "all" token - fan out to all home channels
        if token == "all":
            targets = []
            for platform in self._home_registry.platforms_with_home():
                home = self._home_registry.get_home(platform)
                if home:
                    chat_id, thread_id = home
                    targets.append(DeliveryTarget(
                        channel=platform,
                        channel_id=chat_id,
                        thread_id=thread_id,
                    ))
            return targets
        
        # Handle explicit "<platform>:<chat_id>[:<thread_id>]" format
        if ":" in token:
            parts = token.split(":", 2)
            if len(parts) >= 2:
                platform = parts[0].strip()
                chat_id = parts[1].strip()
                thread_id = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
                
                # Validate that platform and chat_id are non-empty
                if not platform or not chat_id:
                    logger.warning("Invalid explicit delivery token (empty platform or chat_id): %s", token)
                    return []
                
                return [DeliveryTarget(
                    channel=platform,
                    channel_id=chat_id,
                    thread_id=thread_id,
                )]
        
        # Handle platform name token - look up home channel
        home = self._home_registry.get_home(token)
        if home:
            chat_id, thread_id = home
            return [DeliveryTarget(
                channel=token,
                channel_id=chat_id,
                thread_id=thread_id,
            )]
        
        # Handle friendly alias/name via the optional channel directory.
        # Checked after platform/home resolution so existing tokens keep their
        # meaning; aliases only resolve names that are not platforms.
        alias_target = self._resolve_alias(token)
        if alias_target is not None:
            return [alias_target]
        
        logger.warning("Could not resolve delivery token: %s", token)
        return []
