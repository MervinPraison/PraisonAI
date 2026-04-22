"""
Chainlit UI components for pairing approval banner.

Provides admin banner functionality for approving pending pairing requests.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

import chainlit as cl

logger = logging.getLogger(__name__)


# Gateway client configuration
GATEWAY_HOST = os.environ.get("GATEWAY_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "8765"))
GATEWAY_TOKEN = os.environ.get("GATEWAY_AUTH_TOKEN", "")


async def get_pending_pairings() -> List[Dict]:
    """Fetch pending pairing requests from gateway API."""
    if not GATEWAY_TOKEN:
        logger.warning("No GATEWAY_AUTH_TOKEN set, cannot fetch pending pairings")
        return []
    
    try:
        import aiohttp
        
        url = f"http://{GATEWAY_HOST}:{GATEWAY_PORT}/api/pairing/pending"
        headers = {"Authorization": f"Bearer {GATEWAY_TOKEN}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("pending", [])
                else:
                    logger.warning(f"Failed to fetch pending pairings: {resp.status}")
                    return []
    except Exception as e:
        logger.error(f"Error fetching pending pairings: {e}")
        return []


async def approve_pairing(channel: str, code: str) -> bool:
    """Approve a pairing request via gateway API."""
    if not GATEWAY_TOKEN:
        logger.warning("No GATEWAY_AUTH_TOKEN set, cannot approve pairing")
        return False
    
    try:
        import aiohttp
        
        url = f"http://{GATEWAY_HOST}:{GATEWAY_PORT}/api/pairing/approve"
        headers = {
            "Authorization": f"Bearer {GATEWAY_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {"channel": channel, "code": code}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as resp:
                success = resp.status == 200
                if not success:
                    logger.warning(f"Failed to approve pairing: {resp.status}")
                return success
    except Exception as e:
        logger.error(f"Error approving pairing: {e}")
        return False


async def refresh_pending_banner():
    """Display or update the pending pairing banner for admin users."""
    # Check if user is admin
    user = cl.user_session.get("user")
    if not user or user.metadata.get("role") != "admin":
        return
    
    pending = await get_pending_pairings()
    
    if not pending:
        # No pending requests - don't show banner
        return
    
    # Create approval actions for each pending request
    actions = []
    for p in pending:
        channel = p.get("channel", "unknown")
        code = p.get("code", "")
        user_name = p.get("user_name", f"User {code}")
        age = p.get("age_seconds", 0)
        
        # Format age nicely
        if age < 60:
            age_str = f"{age}s ago"
        elif age < 3600:
            age_str = f"{age//60}m ago"
        else:
            age_str = f"{age//3600}h ago"
        
        actions.append(
            cl.Action(
                name=f"approve_{code}",
                value=f"{channel}:{code}",
                label=f"✅ Approve {user_name} ({channel}) - {age_str}",
                description=f"Approve pairing request from {user_name} on {channel}"
            )
        )
    
    # Display banner message with actions
    banner_content = f"🔔 **{len(pending)} pending pairing request(s)**\n\nClick to approve:"
    
    await cl.Message(
        content=banner_content,
        actions=actions,
        author="System"
    ).send()


@cl.action_callback("approve_*")
async def on_approve_pairing(action: cl.Action):
    """Handle approval action from banner."""
    try:
        # Parse channel:code from action value
        channel, code = action.value.split(":", 1)
        
        # Show loading message
        await cl.Message(
            content=f"⏳ Approving pairing for {channel} code {code}...",
            author="System"
        ).send()
        
        # Approve the pairing
        success = await approve_pairing(channel, code)
        
        if success:
            await cl.Message(
                content=f"✅ Successfully approved pairing for {channel} code {code}",
                author="System"
            ).send()
        else:
            await cl.Message(
                content=f"❌ Failed to approve pairing for {channel} code {code}",
                author="System"
            ).send()
        
        # Refresh the banner to update count
        await refresh_pending_banner()
        
    except Exception as e:
        logger.error(f"Error in approval handler: {e}")
        await cl.Message(
            content=f"❌ Error processing approval: {str(e)}",
            author="System"
        ).send()


async def setup_pairing_banner():
    """Setup pairing banner on chat start (call this from @cl.on_chat_start)."""
    await refresh_pending_banner()