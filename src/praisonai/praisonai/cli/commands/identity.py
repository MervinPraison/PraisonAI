"""
Identity CLI commands for PraisonAI cross-platform sessions.

Provides commands to link/unlink platform-scoped user IDs to a single
canonical identity so the same person shares one session, history and
memory across channels:
- link:   Map a (platform, user_id) to a canonical identity
- unlink: Remove a mapping
- list:   Show links for a canonical identity (or all links)
- import: Materialise paired channels as explicit identity links
"""

import logging
from typing import Optional

import typer

logger = logging.getLogger(__name__)

app = typer.Typer(help="Manage cross-platform user identity links")


def _resolver(path: Optional[str], store_dir: Optional[str]):
    from praisonai.bots import StoreBackedIdentityResolver

    return StoreBackedIdentityResolver.from_env(path=path, store_dir=store_dir)


@app.command()
def link(
    platform: str = typer.Argument(..., help="Platform (telegram, whatsapp, discord, slack)"),
    user_id: str = typer.Argument(..., help="Platform-scoped user id"),
    canonical: str = typer.Argument(..., help="Canonical identity to link this user to"),
    path: Optional[str] = typer.Option(None, "--path", help="Identity link-map JSON path"),
    store_dir: Optional[str] = typer.Option(None, "--store-dir", help="Pairing store directory"),
):
    """Link a platform user to a canonical identity."""
    try:
        resolver = _resolver(path, store_dir)
        resolver.link(platform, user_id, canonical)
        typer.echo(f"✅ Linked {platform}:{user_id} -> {canonical}")
    except Exception as e:
        typer.echo(f"Error linking identity: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def unlink(
    platform: str = typer.Argument(..., help="Platform (telegram, whatsapp, discord, slack)"),
    user_id: str = typer.Argument(..., help="Platform-scoped user id"),
    path: Optional[str] = typer.Option(None, "--path", help="Identity link-map JSON path"),
    store_dir: Optional[str] = typer.Option(None, "--store-dir", help="Pairing store directory"),
):
    """Unlink a platform user from its canonical identity."""
    try:
        resolver = _resolver(path, store_dir)
        resolver.unlink(platform, user_id)
        typer.echo(f"✅ Unlinked {platform}:{user_id}")
    except Exception as e:
        typer.echo(f"Error unlinking identity: {e}", err=True)
        raise typer.Exit(1)


@app.command("list")
def list_cmd(
    canonical: Optional[str] = typer.Argument(None, help="Canonical identity to inspect"),
    path: Optional[str] = typer.Option(None, "--path", help="Identity link-map JSON path"),
    store_dir: Optional[str] = typer.Option(None, "--store-dir", help="Pairing store directory"),
):
    """List links for a canonical identity."""
    try:
        resolver = _resolver(path, store_dir)
        if not canonical:
            all_links = resolver.all_links()
            if not all_links:
                typer.echo("No identity links found.")
                return
            typer.echo("All identity links:")
            for platform, user_id, cid in sorted(all_links):
                typer.echo(f"  {platform}:{user_id} -> {cid}")
            return
        links = resolver.links_for(canonical)
        if not links:
            typer.echo(f"No links found for {canonical}.")
            return
        typer.echo(f"Links for {canonical}:")
        for link in links:
            typer.echo(f"  {link.platform}:{link.platform_user_id}")
    except Exception as e:
        typer.echo(f"Error listing identity links: {e}", err=True)
        raise typer.Exit(1)


@app.command("import")
def import_cmd(
    path: Optional[str] = typer.Option(None, "--path", help="Identity link-map JSON path"),
    store_dir: Optional[str] = typer.Option(None, "--store-dir", help="Pairing store directory"),
):
    """Import paired channels as explicit identity links."""
    try:
        resolver = _resolver(path, store_dir)
        count = resolver.link_paired()
        typer.echo(f"✅ Imported {count} identity link(s) from pairing store")
    except Exception as e:
        typer.echo(f"Error importing identity links: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
