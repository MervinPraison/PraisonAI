"""
MCP Auth Storage Example

This example demonstrates how to use the MCPAuthStorage class
to manage OAuth tokens for remote MCP servers.
"""

from praisonaiagents.mcp import (
    MCPAuthStorage,
    generate_state,
    generate_code_verifier,
    generate_code_challenge,
    get_redirect_url
)
import time

# Initialize auth storage
storage = MCPAuthStorage()
print(f"Auth storage path: {storage.filepath}")

# Generate PKCE parameters for OAuth flow
state = generate_state()
verifier = generate_code_verifier()
challenge = generate_code_challenge(verifier)
redirect_url = get_redirect_url()

print("\n=== PKCE Parameters ===")
print(f"State: {state[:30]}...")
print(f"Verifier: {verifier[:30]}...")
print(f"Challenge: {challenge[:30]}...")
print(f"Redirect URL: {redirect_url}")

# Store tokens (simulating OAuth callback)
print("\n=== Storing Tokens ===")
storage.set_tokens("example-server", {
    "access_token": "example_access_token_12345",
    "refresh_token": "example_refresh_token_67890",
    "expires_at": time.time() + 3600,  # 1 hour from now
    "scope": "read write"
}, server_url="https://mcp.example.com/mcp")
print("Tokens stored successfully")

# Retrieve tokens
entry = storage.get("example-server")
print("\n=== Retrieved Entry ===")
print(f"Server URL: {entry['server_url']}")
print(f"Access Token: {entry['tokens']['access_token'][:20]}...")
print(f"Expires At: {entry['tokens']['expires_at']}")

# Check token expiration
is_expired = storage.is_token_expired("example-server")
print("\n=== Token Status ===")
print(f"Is Expired: {is_expired}")

# URL validation
print("\n=== URL Validation ===")
valid = storage.get_for_url("example-server", "https://mcp.example.com/mcp")
print(f"Same URL: {valid is not None}")

invalid = storage.get_for_url("example-server", "https://different.url/mcp")
print(f"Different URL: {invalid is None}")

# List all entries
print("\n=== All Entries ===")
all_entries = storage.all()
for name, entry in all_entries.items():
    print(f"  {name}: {entry.get('server_url', 'N/A')}")

# Cleanup
storage.remove("example-server")
print("\n=== Cleanup ===")
print("Removed example-server entry")
