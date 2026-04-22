"""
Pairing CLI commands for PraisonAI Gateway.

Provides commands to manage bot user pairing:
- list: Show all paired channels
- approve: Approve a pairing code  
- revoke: Revoke a paired channel
- clear: Clear all paired channels
"""

import logging
import os
from typing import Optional

import typer

from praisonai.gateway.pairing import PairingStore

logger = logging.getLogger(__name__)

app = typer.Typer(help="Manage bot user pairing")


@app.command("list")
def list_cmd(
    store_dir: Optional[str] = typer.Option(
        None, "--store-dir", help="Custom pairing store directory"
    )
):
    """List all paired channels."""
    try:
        store = PairingStore(store_dir=store_dir)
        paired = store.list_paired()
        
        if not paired:
            typer.echo("No paired channels found.")
            return
        
        typer.echo(f"Found {len(paired)} paired channels:\n")
        
        for channel in paired:
            # Format timestamp
            import datetime
            paired_time = datetime.datetime.fromtimestamp(channel.paired_at)
            
            typer.echo(f"Platform: {channel.channel_type}")
            typer.echo(f"Channel:  {channel.channel_id}")
            typer.echo(f"Paired:   {paired_time.strftime('%Y-%m-%d %H:%M:%S')}")
            if channel.label:
                typer.echo(f"Label:    {channel.label}")
            typer.echo()
            
    except Exception as e:
        typer.echo(f"Error listing paired channels: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def approve(
    platform: str = typer.Argument(..., help="Platform type (telegram, discord, slack, whatsapp)"),
    code: str = typer.Argument(..., help="8-character pairing code"),
    channel_id: str = typer.Argument(..., help="Channel ID for the pairing"),
    label: str = typer.Option("", "--label", help="Optional human-readable label for this pairing"),
    store_dir: Optional[str] = typer.Option(None, "--store-dir", help="Custom pairing store directory"),
):
    """Approve a pairing code.
    
    PLATFORM: Platform type (telegram, discord, slack, whatsapp)
    CODE: 8-character pairing code
    CHANNEL_ID: Channel ID for the pairing
    """
    try:
        store = PairingStore(store_dir=store_dir)
        
        # First check if the code exists and get its details without consuming it
        pending_pairings = store.list_pending()
        code_info = None
        for pairing in pending_pairings:
            if pairing.get('code') == code:
                code_info = pairing
                break
        
        if not code_info:
            typer.echo(f"❌ Invalid or expired code: {code}", err=True)
            raise typer.Exit(1)
        
        # Now verify and pair (this will consume the code)
        success = store.verify_and_pair(
            code=code,
            channel_id=channel_id,
            channel_type=platform,
            label=label
        )
        
        if success:
            typer.echo(f"✅ Successfully paired {platform} channel {channel_id}")
            if label:
                typer.echo(f"   Label: {label}")
        else:
            typer.echo(f"❌ Failed to pair - invalid or expired code: {code}", err=True)
            raise typer.Exit(1)
            
    except Exception as e:
        typer.echo(f"Error approving pairing: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def revoke(
    platform: str = typer.Argument(..., help="Platform type (telegram, discord, slack, whatsapp)"),
    channel_id: str = typer.Argument(..., help="Channel ID to revoke"),
    store_dir: Optional[str] = typer.Option(None, "--store-dir", help="Custom pairing store directory"),
):
    """Revoke a paired channel.
    
    PLATFORM: Platform type (telegram, discord, slack, whatsapp)
    CHANNEL_ID: Channel ID to revoke
    """
    try:
        store = PairingStore(store_dir=store_dir)
        
        success = store.revoke(channel_id=channel_id, channel_type=platform)
        
        if success:
            typer.echo(f"✅ Revoked {platform} channel {channel_id}")
        else:
            typer.echo(f"❌ Channel not found: {platform}/{channel_id}", err=True)
            
    except Exception as e:
        typer.echo(f"Error revoking pairing: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def clear(
    confirm: bool = typer.Option(False, "--confirm", help="Skip confirmation prompt"),
    store_dir: Optional[str] = typer.Option(None, "--store-dir", help="Custom pairing store directory"),
):
    """Clear all paired channels."""
    if not confirm:
        if not typer.confirm('Are you sure you want to clear ALL paired channels?'):
            typer.echo("Cancelled.")
            return
    
    try:
        store = PairingStore(store_dir=store_dir)
        paired = store.list_paired()
        
        if not paired:
            typer.echo("No paired channels to clear.")
            return
        
        # Revoke each paired channel
        count = 0
        for channel in paired:
            if store.revoke(channel.channel_id, channel.channel_type):
                count += 1
        
        typer.echo(f"✅ Cleared {count} paired channels")
        
    except Exception as e:
        typer.echo(f"Error clearing paired channels: {e}", err=True)
        raise typer.Exit(1)


if __name__ == '__main__':
    app()
