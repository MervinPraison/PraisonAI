"""
Authentication command group for PraisonAI CLI.

Provides secure credential management:
- auth login: Store API keys with validation
- auth logout: Remove stored credentials  
- auth list: Show stored providers (keys redacted)
- auth status: Check credential status and validation
"""

import os
import sys
from typing import Optional

import typer

from ..output.console import get_output_controller
from ..configuration.credentials import CredentialStore, redact_key, validate_api_key


app = typer.Typer(help="Manage API credentials")


def _format_expiry(cred) -> str:
    """Format an OAuth credential's expiry for display ('(n/a)' for keys)."""
    if not getattr(cred, "auth_method", "apikey") == "oauth":
        return "(n/a)"
    if not cred.expires_at:
        return "(no expiry)"
    import time as _time
    remaining = cred.expires_at - _time.time()
    if remaining <= 0:
        return "expired"
    mins = int(remaining // 60)
    if mins >= 60:
        return f"{mins // 60}h {mins % 60}m"
    return f"{mins}m" if mins else "<1m"


def _validate_with_live_call(provider: str, api_key: str, base_url: Optional[str] = None) -> tuple[bool, str]:
    """
    Validate API key with a cheap live call to the provider.
    
    Args:
        provider: Provider name
        api_key: API key to validate
        base_url: Optional base URL
        
    Returns:
        Tuple of (is_valid, message)
    """
    try:
        if provider.lower() == "openai":
            # Use a cheap OpenAI API call to validate
            import openai
            client = openai.OpenAI(
                api_key=api_key,
                base_url=base_url or "https://api.openai.com/v1"
            )
            
            # Try to list models (cheap operation)
            client.models.list()
            return True, "API key verified"
            
        elif provider.lower() == "anthropic":
            # Live validation would require a billable request; skip it.
            return True, "Format valid (live test skipped for Anthropic)"
            
        elif provider.lower() in ("google", "gemini"):
            # For Google/Gemini, format validation only
            return True, "Format valid (live test not implemented)"
            
        else:
            # Unknown provider - skip live validation
            return True, "Format valid (live test not available)"
            
    except ImportError:
        return True, "Format valid (provider SDK not installed for live test)"
    except Exception as e:
        return False, f"API key invalid: {str(e)}"


def _run_oauth_login(
    provider: str,
    output,
    base_url,
    model,
    no_browser: bool,
    overrides: Optional[dict] = None,
) -> None:
    """Run the browser/device-code OAuth flow and store the resulting tokens."""
    from ..configuration.oauth import run_oauth_login

    def _on_prompt(uri: Optional[str], user_code: Optional[str]) -> None:
        if user_code:
            output.print_info(
                f"To sign in, visit {uri} and enter code: {user_code}"
            )
        elif uri:
            output.print_info(f"Opening browser to authorize... If it doesn't open, visit:\n{uri}")

    try:
        config, tokens = run_oauth_login(
            provider,
            overrides=overrides,
            open_browser=not no_browser,
            on_prompt=_on_prompt,
        )
    except ValueError as e:
        output.print_error(str(e))
        raise typer.Exit(1)
    except Exception as e:
        output.print_error(f"OAuth login failed: {e}")
        raise typer.Exit(1)

    if not tokens.get("access_token"):
        output.print_error("OAuth flow did not return an access token")
        raise typer.Exit(1)

    try:
        store = CredentialStore()
        store.store_oauth_credential(
            provider=provider,
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            expires_at=tokens.get("expires_at"),
            token_url=config.token_url,
            client_id=config.client_id,
            scope=tokens.get("scope") or config.scope,
            base_url=base_url,
            model=model,
        )
    except Exception as e:
        output.print_error(f"Failed to store credentials: {e}")
        raise typer.Exit(1)

    if output.is_json_mode:
        # Emit a single JSON document; ``print_success`` would emit a second.
        output.print_json({
            "provider": provider,
            "status": "stored",
            "auth_method": "oauth",
            "expires_at": tokens.get("expires_at"),
        })
    else:
        output.print_success(f"Signed in to {provider} via OAuth")


@app.command("login")
def auth_login(
    provider: str = typer.Argument(help="Provider name (e.g., openai, anthropic)"),
    method: str = typer.Option("auto", "--method", help="Auth method: auto, apikey, or oauth"),
    key: Optional[str] = typer.Option(None, "--key", help="API key (will prompt if not provided)"),
    key_stdin: bool = typer.Option(False, "--key-stdin", help="Read API key from stdin"),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="Custom base URL"),
    model: Optional[str] = typer.Option(None, "--model", help="Default model for this provider"),
    skip_validation: bool = typer.Option(False, "--skip-validation", help="Skip API key validation"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not auto-open the browser for OAuth"),
    client_id: Optional[str] = typer.Option(None, "--client-id", help="OAuth client id (overrides the built-in provider entry)"),
    token_url: Optional[str] = typer.Option(None, "--token-url", help="OAuth token endpoint (for providers not in the built-in registry)"),
    device_authorization_url: Optional[str] = typer.Option(None, "--device-authorization-url", help="OAuth device-code endpoint (RFC 8628)"),
    authorization_url: Optional[str] = typer.Option(None, "--authorization-url", help="OAuth authorization endpoint (RFC 7636 PKCE)"),
    scope: Optional[str] = typer.Option(None, "--scope", help="OAuth scope(s) to request"),
):
    """
    Store API credentials for a provider.
    
    Examples:
        praisonai auth login openai
        praisonai auth login openai --key sk-...
        echo "sk-..." | praisonai auth login openai --key-stdin
        praisonai auth login github --method oauth --client-id <app-id>
    """
    output = get_output_controller()

    # Assemble any OAuth endpoint overrides supplied on the command line. These
    # let users sign in to a built-in provider that needs an app client id, or
    # to a provider not in the registry (e.g. a self-hosted gateway).
    oauth_overrides = {
        "client_id": client_id,
        "token_url": token_url,
        "device_authorization_url": device_authorization_url,
        "authorization_url": authorization_url,
        "scope": scope,
    }
    oauth_overrides = {k: v for k, v in oauth_overrides.items() if v is not None}

    # Decide between OAuth and API-key login. ``auto`` selects OAuth only when
    # the provider has an OAuth config AND no key was supplied; otherwise it
    # falls back to the API-key path (unchanged behaviour).
    method = (method or "auto").lower()
    if method not in {"auto", "apikey", "oauth"}:
        output.print_error("Invalid auth method. Use: auto, apikey, or oauth")
        raise typer.Exit(1)
    if method == "oauth":
        _run_oauth_login(provider, output, base_url, model, no_browser, oauth_overrides)
        return
    if method == "auto" and not key and not key_stdin:
        try:
            from ..configuration.oauth import provider_supports_oauth, provider_requires_client_id
            if provider_supports_oauth(provider, oauth_overrides):
                # Don't silently start an OAuth flow that will immediately fail
                # for lack of a client id; fall through to API-key login unless
                # the user explicitly supplied one.
                if not provider_requires_client_id(provider, oauth_overrides):
                    _run_oauth_login(provider, output, base_url, model, no_browser, oauth_overrides)
                    return
                # Known OAuth provider but no client id yet: surface the OAuth
                # path so the user isn't left wondering why they're being asked
                # for an API key, then continue to the API-key fallback below.
                output.print_info(
                    f"{provider} supports OAuth sign-in. To use it, re-run with: "
                    f"praisonai auth login {provider} --method oauth "
                    f"--client-id <your-oauth-app-client-id>"
                )
        except Exception:
            # Fall through to API-key login on any OAuth detection error.
            pass

    # Get API key
    api_key = None
    
    if key_stdin:
        # Read from stdin
        try:
            api_key = sys.stdin.read().strip()
        except KeyboardInterrupt:
            output.print_error("Cancelled")
            raise typer.Exit(1)
    elif key:
        # Use provided key
        api_key = key
    else:
        # Prompt for key
        try:
            api_key = typer.prompt(
                f"Enter API key for {provider}",
                hide_input=True
            )
        except KeyboardInterrupt:
            output.print_error("Cancelled")
            raise typer.Exit(1)
    
    if not api_key:
        output.print_error("No API key provided")
        raise typer.Exit(1)
    
    # Validate API key format
    if not skip_validation:
        format_valid, format_msg = validate_api_key(provider, api_key)
        if not format_valid:
            output.print_error(f"Invalid API key format: {format_msg}")
            raise typer.Exit(1)
        
        # Try live validation for some providers
        live_valid, live_msg = _validate_with_live_call(provider, api_key, base_url)
        if not live_valid:
            output.print_error(f"API key validation failed: {live_msg}")
            if not typer.confirm("Store anyway?"):
                raise typer.Exit(1)
        else:
            output.print_success(f"API key validated: {live_msg}")
    
    # Store credential
    try:
        store = CredentialStore()
        store.store_credential(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model
        )
        
        output.print_success(f"Stored credentials for {provider}")
        
        if output.is_json_mode:
            output.print_json({
                "provider": provider,
                "status": "stored",
                "key_redacted": redact_key(api_key)
            })
        else:
            output.print_info(f"Key stored: {redact_key(api_key)}")
            
    except Exception as e:
        output.print_error(f"Failed to store credentials: {e}")
        raise typer.Exit(1)


@app.command("logout")
def auth_logout(
    provider: Optional[str] = typer.Argument(None, help="Provider name to remove"),
    all_providers: bool = typer.Option(False, "--all", help="Remove all stored credentials"),
):
    """
    Remove stored credentials.
    
    Examples:
        praisonai auth logout openai
        praisonai auth logout --all
    """
    output = get_output_controller()
    
    try:
        store = CredentialStore()
        
        if all_providers:
            # Remove all credentials
            if not typer.confirm("Remove ALL stored credentials?"):
                output.print_info("Cancelled")
                return
            
            store.clear_all()
            output.print_success("Removed all stored credentials")
            
            if output.is_json_mode:
                output.print_json({"status": "all_removed"})
                
        else:
            # Remove specific provider
            if provider is None:
                output.print_error("Provider name is required when not using --all")
                output.print_info("Use 'praisonai auth logout <provider>' or 'praisonai auth logout --all'")
                raise typer.Exit(1)
            
            if not store.has_credential(provider):
                output.print_warning(f"No credentials found for {provider}")
                raise typer.Exit(1)
            
            if store.remove_credential(provider):
                output.print_success(f"Removed credentials for {provider}")
                
                if output.is_json_mode:
                    output.print_json({
                        "provider": provider,
                        "status": "removed"
                    })
            else:
                output.print_error(f"Failed to remove credentials for {provider}")
                raise typer.Exit(1)
                
    except Exception as e:
        output.print_error(f"Failed to remove credentials: {e}")
        raise typer.Exit(1)


@app.command("list")
def auth_list():
    """
    List all stored providers (API keys are redacted).
    
    Example:
        praisonai auth list
    """
    output = get_output_controller()
    
    try:
        store = CredentialStore()
        providers = store.list_providers()
        
        if not providers:
            output.print_info("No stored credentials")
            if output.is_json_mode:
                output.print_json({"providers": []})
            return
        
        # Get detailed info for each provider
        provider_info = []
        for provider_name in providers:
            cred = store.get_credential(provider_name)
            if cred:
                info = {
                    "provider": provider_name,
                    "auth_method": cred.auth_method,
                    "key_redacted": redact_key(cred.api_key),
                    "base_url": cred.base_url,
                    "model": cred.model,
                    "expires_at": cred.expires_at,
                    "expires": _format_expiry(cred),
                }
                provider_info.append(info)
        
        if output.is_json_mode:
            output.print_json({"providers": provider_info})
        else:
            # Create table
            headers = ["Provider", "Method", "Secret", "Expires", "Base URL", "Model"]
            rows = []
            for info in provider_info:
                rows.append([
                    info["provider"],
                    info["auth_method"],
                    info["key_redacted"],
                    info["expires"],
                    info["base_url"] or "(default)",
                    info["model"] or "(none)"
                ])
            
            output.print_table(headers, rows, title="Stored Credentials")
            
    except Exception as e:
        output.print_error(f"Failed to list credentials: {e}")
        raise typer.Exit(1)


@app.command("status")
def auth_status(
    provider: Optional[str] = typer.Argument(None, help="Check specific provider (optional)"),
    validate: bool = typer.Option(False, "--validate", help="Perform live API validation"),
):
    """
    Check credential status and validation.
    
    Examples:
        praisonai auth status
        praisonai auth status openai
        praisonai auth status openai --validate
    """
    output = get_output_controller()
    
    try:
        store = CredentialStore()
        
        if provider:
            # Check specific provider
            cred = store.get_credential(provider)
            if not cred:
                output.print_warning(f"No credentials found for {provider}")
                if output.is_json_mode:
                    output.print_json({
                        "provider": provider,
                        "status": "not_found"
                    })
                raise typer.Exit(1)
            
            # Basic format validation (OAuth tokens have no static format)
            if cred.is_oauth():
                format_valid, format_msg = True, "OAuth token"
            else:
                format_valid, format_msg = validate_api_key(provider, cred.api_key)
            
            status_info = {
                "provider": provider,
                "status": "found",
                "auth_method": cred.auth_method,
                "key_redacted": redact_key(cred.api_key),
                "format_valid": format_valid,
                "format_message": format_msg,
                "base_url": cred.base_url,
                "model": cred.model,
                "expires_at": cred.expires_at,
                "expires": _format_expiry(cred),
            }
            
            # Live validation if requested
            if validate:
                # Use a freshly-refreshed token for OAuth so we don't validate a
                # stale mirrored access token.
                live_secret = store.get_valid_token(provider) if cred.is_oauth() else cred.api_key
                live_valid, live_msg = _validate_with_live_call(provider, live_secret, cred.base_url)
                status_info["live_valid"] = live_valid
                status_info["live_message"] = live_msg
            
            if output.is_json_mode:
                output.print_json(status_info)
            else:
                output.print_panel(
                    f"Provider: {provider}\n"
                    f"Method: {cred.auth_method}\n"
                    f"Secret: {redact_key(cred.api_key)}\n"
                    + (f"Expires: {_format_expiry(cred)}\n" if cred.is_oauth() else "") +
                    f"Format: {'✅' if format_valid else '❌'} {format_msg}\n"
                    + (f"Live Test: {'✅' if status_info.get('live_valid') else '❌'} {status_info.get('live_message', 'Not tested')}\n" if validate else "") +
                    f"Base URL: {cred.base_url or '(default)'}\n"
                    f"Model: {cred.model or '(none)'}",
                    title=f"Credentials Status: {provider}"
                )
                
        else:
            # Check all providers
            providers = store.list_providers()
            
            if not providers:
                output.print_info("No stored credentials")
                if output.is_json_mode:
                    output.print_json({"providers": []})
                return
            
            all_status = []
            for provider_name in providers:
                cred = store.get_credential(provider_name)
                if cred:
                    if cred.is_oauth():
                        format_valid, format_msg = True, "OAuth token"
                    else:
                        format_valid, format_msg = validate_api_key(provider_name, cred.api_key)
                    
                    status = {
                        "provider": provider_name,
                        "auth_method": cred.auth_method,
                        "key_redacted": redact_key(cred.api_key),
                        "format_valid": format_valid,
                        "format_message": format_msg,
                        "expires_at": cred.expires_at,
                        "expires": _format_expiry(cred),
                    }
                    
                    if validate:
                        live_secret = (
                            store.get_valid_token(provider_name)
                            if cred.is_oauth()
                            else cred.api_key
                        )
                        live_valid, live_msg = _validate_with_live_call(provider_name, live_secret, cred.base_url)
                        status["live_valid"] = live_valid
                        status["live_message"] = live_msg
                    
                    all_status.append(status)
            
            if output.is_json_mode:
                output.print_json({"providers": all_status})
            else:
                # Create table
                headers = ["Provider", "Method", "Secret", "Expires", "Format"]
                if validate:
                    headers.append("Live Test")
                
                rows = []
                for status in all_status:
                    row = [
                        status["provider"],
                        status["auth_method"],
                        status["key_redacted"],
                        status["expires"],
                        "✅" if status["format_valid"] else "❌"
                    ]
                    if validate:
                        row.append("✅" if status.get("live_valid") else "❌")
                    rows.append(row)
                
                output.print_table(headers, rows, title="Credentials Status")
                
    except Exception as e:
        output.print_error(f"Failed to check status: {e}")
        raise typer.Exit(1)