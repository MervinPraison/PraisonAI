"""
Delivery routing and channel directory for proactive outbound messaging.

Provides:
- DeliveryRouter: Resolves symbolic targets to concrete (platform, channel_id)
- ChannelDirectory: Manages reachable channels with friendly aliases
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .botos import BotOS

logger = logging.getLogger(__name__)


@dataclass
class SessionSource:
    """Source information for a message/session."""
    platform: str
    channel_id: str
    user_id: Optional[str] = None
    thread_id: Optional[str] = None


class ChannelDirectory:
    """
    Directory of reachable channels with friendly aliases.
    
    Maintains a mapping of:
    - Platform home channels
    - Named aliases to specific channels
    - Observed channels from active sessions
    """
    
    def __init__(self):
        # Home channel per platform (default delivery target)
        self._home_channels: Dict[str, str] = {}
        
        # Friendly aliases to (platform, channel_id)
        self._aliases: Dict[str, Tuple[str, str]] = {}
        
        # Recently observed channels per platform
        self._observed: Dict[str, set] = {}
    
    def set_home_channel(self, platform: str, channel_id: str) -> None:
        """Set the default/home channel for a platform."""
        platform_key = platform.lower()
        self._home_channels[platform_key] = channel_id
        logger.debug(f"ChannelDirectory: set home channel for {platform_key}: {channel_id}")
    
    def add_alias(self, name: str, platform: str, channel_id: str) -> None:
        """Add a friendly alias for a channel."""
        platform_key = platform.lower()
        existing = self._aliases.get(name)
        if existing and existing != (platform_key, channel_id):
            raise ValueError(
                f"Alias '{name}' already points to {existing[0]}:{existing[1]}"
            )
        self._aliases[name] = (platform_key, channel_id)
        logger.debug(f"ChannelDirectory: added alias '{name}' -> {platform_key}:{channel_id}")
    
    def observe_channel(self, platform: str, channel_id: str) -> None:
        """Record an observed channel from an active session."""
        platform_key = platform.lower()
        if platform_key not in self._observed:
            self._observed[platform_key] = set()
        self._observed[platform_key].add(channel_id)
    
    def get_home_channel(self, platform: str) -> Optional[str]:
        """Get the home channel for a platform."""
        return self._home_channels.get(platform.lower())
    
    def resolve_alias(self, alias: str) -> Optional[Tuple[str, str]]:
        """Resolve an alias to (platform, channel_id)."""
        return self._aliases.get(alias)
    
    def has_channel(self, platform: str, channel_id: str) -> bool:
        """Check if a channel is known (home, alias, or observed)."""
        platform_key = platform.lower()
        
        # Check if it's the home channel
        if self._home_channels.get(platform_key) == channel_id:
            return True
        
        # Check if it's in aliases
        for p, c in self._aliases.values():
            if p.lower() == platform_key and c == channel_id:
                return True
        
        # Check if it's observed
        if platform_key in self._observed and channel_id in self._observed[platform_key]:
            return True
        
        return False


class DeliveryRouter:
    """
    Routes messages to target channels using symbolic targets.
    
    Target grammar:
    - "origin" - the channel the request came from
    - "<platform>" - that platform's home/default channel
    - "<platform>:<channel_id>" - explicit channel on a platform
    - "<alias>" - friendly name from the channel directory
    """
    
    def __init__(self, botos: BotOS):
        self._botos = botos
        self.directory = ChannelDirectory()
    
    def resolve(self, target: str, origin: Optional[SessionSource] = None) -> Tuple[str, str]:
        """
        Resolve a target string to (platform, channel_id).
        
        Args:
            target: Target specification (origin|platform|platform:channel|alias)
            origin: Optional source of the original request
            
        Returns:
            Tuple of (platform, channel_id)
            
        Raises:
            ValueError: If target cannot be resolved
        """
        # Handle "origin" target
        if target == "origin":
            if not origin:
                raise ValueError("Cannot resolve 'origin' without source context")
            return (origin.platform, origin.channel_id)
        
        # Handle "platform:channel_id" format
        if ":" in target:
            platform, channel_id = [p.strip() for p in target.split(":", 1)]
            if not platform or not channel_id:
                raise ValueError(
                    "Invalid target format. Expected '<platform>:<channel_id>'"
                )
            
            # Validate platform exists (normalize to lowercase)
            platform_key = platform.lower()
            if not self._botos.get_bot(platform_key):
                raise ValueError(f"Platform '{platform}' not configured")
            
            return (platform_key, channel_id)
        
        # Check if it's a platform name (use home channel) - check this BEFORE aliases
        platform_key = target.lower()
        if self._botos.get_bot(platform_key):
            home_channel = self.directory.get_home_channel(platform_key)
            if home_channel:
                return (platform_key, home_channel)
            raise ValueError(f"Platform '{target}' has no home channel configured")
        
        # Check if it's an alias
        alias_result = self.directory.resolve_alias(target)
        if alias_result:
            return alias_result
        
        # If nothing matches, it might be an undefined alias
        raise ValueError(f"Cannot resolve target '{target}': not a platform, alias, or platform:channel format")
    
    async def deliver(self, target: str, text: str, origin: Optional[SessionSource] = None) -> bool:
        """
        Deliver a message to a target.
        
        Args:
            target: Target specification (origin|platform|platform:channel|alias)
            text: Message content to deliver
            origin: Optional source of the original request
            
        Returns:
            True if delivered successfully, False otherwise
        """
        try:
            platform, channel_id = self.resolve(target, origin)
            bot = self._botos.get_bot(platform)
            
            if not bot:
                logger.warning(f"DeliveryRouter: platform '{platform}' not available")
                return False
            
            await bot.send_message(channel_id, text)
            logger.info(f"DeliveryRouter: delivered to {platform}:{channel_id}")
            return True
            
        except ValueError as e:
            logger.error(f"DeliveryRouter: failed to resolve target '{target}': {e}")
            return False
        except Exception as e:
            logger.error(f"DeliveryRouter: delivery failed for '{target}': {e}")
            return False
    
    def configure_from_dict(self, config: Dict) -> None:
        """
        Configure the directory from a configuration dictionary.
        
        Expected format:
        {
            "platform_name": {
                "home_channel": "123456",
                "aliases": {
                    "ops-alerts": "123456",
                    "dev-chat": "789012"
                }
            }
        }
        """
        for platform, platform_config in config.items():
            # Set home channel
            if "home_channel" in platform_config:
                self.directory.set_home_channel(platform, platform_config["home_channel"])
            
            # Set aliases
            if "aliases" in platform_config:
                for alias_name, channel_id in platform_config["aliases"].items():
                    self.directory.add_alias(alias_name, platform, channel_id)
