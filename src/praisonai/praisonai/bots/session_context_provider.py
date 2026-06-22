"""
Session context provider for platform awareness in gateway agents.

Builds enriched SessionContext with origin and reachable targets information
to be injected into agent prompts for platform-aware reasoning.
"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING, List

from praisonaiagents.session.context import (
    Origin,
    ReachableTarget,
    SessionContext,
)

from .delivery import detect_chat_type

if TYPE_CHECKING:
    from .delivery import ChannelDirectory

logger = logging.getLogger(__name__)


class SessionContextProvider:
    """Provides enriched session context with platform awareness."""
    
    def __init__(
        self,
        channel_directory: Optional[ChannelDirectory] = None,
        inject_context: bool = True,
    ):
        """Initialize the session context provider.
        
        Args:
            channel_directory: Channel directory for reachable targets
            inject_context: Whether to inject platform context into prompts
        """
        self.channel_directory = channel_directory
        self.inject_context = inject_context
    
    def build_context(
        self,
        platform: str,
        chat_id: str,
        chat_name: str = "",
        thread_id: str = "",
        user_id: str = "",
        user_name: str = "",
        unified_user_id: str = "",
    ) -> SessionContext:
        """Build enriched session context with origin and targets.
        
        Args:
            platform: Platform name
            chat_id: Chat/channel ID
            chat_name: Optional chat/channel name
            thread_id: Optional thread ID
            user_id: User ID
            user_name: Optional user display name
            unified_user_id: Unified user ID across platforms
            
        Returns:
            Enriched SessionContext with origin and reachable_targets
        """
        # Build origin information
        origin = None
        if self.inject_context:
            chat_type = detect_chat_type(platform, chat_id)
            display_name = chat_name or chat_id
            
            origin = Origin(
                platform=platform,
                chat_type=chat_type,
                display_name=display_name,
                thread_id=thread_id,
            )
        
        # Build reachable targets list
        reachable_targets = None
        if self.inject_context and self.channel_directory:
            targets_data = self.channel_directory.describe_targets()
            reachable_targets = [
                ReachableTarget(
                    name=t['name'],
                    platform=t['platform'],
                    channel_id=t['channel_id'],
                    kind=t['kind'],
                )
                for t in targets_data
            ]
        
        # Return enriched context
        return SessionContext(
            platform=platform,
            chat_id=chat_id,
            chat_name=chat_name,
            thread_id=thread_id,
            user_id=user_id,
            user_name=user_name,
            unified_user_id=unified_user_id,
            origin=origin,
            reachable_targets=reachable_targets,
        )
    
    def format_system_prompt(self, context: SessionContext) -> str:
        """Format the session context as a system prompt section.
        
        Args:
            context: The session context to format
            
        Returns:
            Formatted string for system prompt injection
        """
        if not self.inject_context:
            return ""
        
        parts = []
        
        # Add origin information
        if context.origin:
            origin = context.origin
            parts.append(
                f"[Session] You are replying on {origin.platform}"
            )
            if origin.chat_type and origin.chat_type != "unknown":
                parts[-1] += f" ({origin.chat_type}"
                if origin.display_name:
                    parts[-1] += f' "{origin.display_name}"'
                parts[-1] += ")"
            if origin.thread_id:
                parts[-1] += f" in thread {origin.thread_id}"
            parts[-1] += "."
        
        # Add reachable targets
        if context.reachable_targets:
            target_descriptions = []
            for target in context.reachable_targets:
                desc = f"{target.name} ({target.platform}"
                if target.kind == "home":
                    desc += ", home"
                if target.kind == "alias":
                    desc += f', alias "{target.name}"'
                desc += ")"
                target_descriptions.append(desc)
            
            if target_descriptions:
                parts.append(
                    f"Reachable targets: {', '.join(target_descriptions)}."
                )
        
        return "\n".join(parts) if parts else ""