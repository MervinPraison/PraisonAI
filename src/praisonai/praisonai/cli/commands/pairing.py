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

import click

from praisonai.gateway.pairing import PairingStore

logger = logging.getLogger(__name__)


@click.group()
def pairing():
    """Manage bot user pairing."""
    pass


@pairing.command()
@click.option(
    '--store-dir',
    default=None,
    help='Custom pairing store directory'
)
def list(store_dir: Optional[str]):
    """List all paired channels."""
    try:
        store = PairingStore(store_dir=store_dir)
        paired = store.list_paired()
        
        if not paired:
            click.echo("No paired channels found.")
            return
        
        click.echo(f"Found {len(paired)} paired channels:\n")
        
        for channel in paired:
            # Format timestamp
            import datetime
            paired_time = datetime.datetime.fromtimestamp(channel.paired_at)
            
            click.echo(f"Platform: {channel.channel_type}")
            click.echo(f"Channel:  {channel.channel_id}")
            click.echo(f"Paired:   {paired_time.strftime('%Y-%m-%d %H:%M:%S')}")
            if channel.label:
                click.echo(f"Label:    {channel.label}")
            click.echo()
            
    except Exception as e:
        click.echo(f"Error listing paired channels: {e}", err=True)
        raise click.ClickException(str(e))


@pairing.command()
@click.argument('platform')
@click.argument('code')
@click.argument('channel_id', required=False)
@click.option(
    '--label',
    default='',
    help='Optional human-readable label for this pairing'
)
@click.option(
    '--store-dir',
    default=None,
    help='Custom pairing store directory'
)
def approve(platform: str, code: str, channel_id: Optional[str], label: str, store_dir: Optional[str]):
    """Approve a pairing code.
    
    PLATFORM: Platform type (telegram, discord, slack, whatsapp)
    CODE: 8-character pairing code
    CHANNEL_ID: Channel ID (optional, will use code as channel_id if not provided)
    """
    # If no channel_id provided, use the code as channel_id
    # This works for simple cases where the code represents the channel
    if not channel_id:
        channel_id = f"user_{code}"
    
    try:
        store = PairingStore(store_dir=store_dir)
        
        success = store.verify_and_pair(
            code=code,
            channel_id=channel_id,
            channel_type=platform,
            label=label
        )
        
        if success:
            click.echo(f"✅ Successfully paired {platform} channel {channel_id}")
            if label:
                click.echo(f"   Label: {label}")
        else:
            click.echo(f"❌ Failed to pair - invalid or expired code: {code}", err=True)
            raise click.ClickException(f"Invalid code: {code}")
            
    except Exception as e:
        click.echo(f"Error approving pairing: {e}", err=True)
        raise click.ClickException(str(e))


@pairing.command()
@click.argument('platform')
@click.argument('channel_id')
@click.option(
    '--store-dir',
    default=None,
    help='Custom pairing store directory'
)
def revoke(platform: str, channel_id: str, store_dir: Optional[str]):
    """Revoke a paired channel.
    
    PLATFORM: Platform type (telegram, discord, slack, whatsapp)
    CHANNEL_ID: Channel ID to revoke
    """
    try:
        store = PairingStore(store_dir=store_dir)
        
        success = store.revoke(channel_id=channel_id, channel_type=platform)
        
        if success:
            click.echo(f"✅ Revoked {platform} channel {channel_id}")
        else:
            click.echo(f"❌ Channel not found: {platform}/{channel_id}", err=True)
            
    except Exception as e:
        click.echo(f"Error revoking pairing: {e}", err=True)
        raise click.ClickException(str(e))


@pairing.command()
@click.option(
    '--confirm',
    is_flag=True,
    help='Skip confirmation prompt'
)
@click.option(
    '--store-dir',
    default=None,
    help='Custom pairing store directory'
)
def clear(confirm: bool, store_dir: Optional[str]):
    """Clear all paired channels."""
    if not confirm:
        if not click.confirm('Are you sure you want to clear ALL paired channels?'):
            click.echo("Cancelled.")
            return
    
    try:
        store = PairingStore(store_dir=store_dir)
        paired = store.list_paired()
        
        if not paired:
            click.echo("No paired channels to clear.")
            return
        
        # Revoke each paired channel
        count = 0
        for channel in paired:
            if store.revoke(channel.channel_id, channel.channel_type):
                count += 1
        
        click.echo(f"✅ Cleared {count} paired channels")
        
    except Exception as e:
        click.echo(f"Error clearing paired channels: {e}", err=True)
        raise click.ClickException(str(e))


if __name__ == '__main__':
    pairing()