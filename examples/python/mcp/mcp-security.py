"""
MCP Security Example

Demonstrates security features for MCP transports.
These features help prevent attacks like DNS rebinding.

Features:
- Origin header validation
- DNS rebinding prevention
- Localhost binding for local servers
- Authentication header support
- Secure session ID generation

Protocol: MCP 2025-11-25
"""

# Example code (requires running MCP servers):
#
# from praisonaiagents import Agent, MCP
#
# # Agent with authentication
# agent = Agent(
#     name="Secure Assistant",
#     tools=MCP(
#         "https://api.example.com/mcp",
#         headers={"Authorization": "Bearer your-token"}
#     )
# )
#
# # WebSocket with auth token
# agent_ws = Agent(
#     name="Secure WebSocket Assistant",
#     tools=MCP(
#         "wss://api.example.com/mcp",
#         auth_token="Bearer your-secret-token"
#     )
# )

# Using security utilities directly (no server required)
if __name__ == "__main__":
    from praisonaiagents.mcp.mcp_security import (
        is_valid_origin,
        create_auth_header,
        generate_secure_session_id,
        SecurityConfig
    )
    
    print("MCP Security Example")
    print("=" * 40)
    
    # Origin validation (DNS rebinding prevention)
    print("\n1. Origin Validation:")
    allowed = ["localhost", "127.0.0.1", "example.com"]
    print(f"   Allowed origins: {allowed}")
    print(f"   'http://localhost:8080' valid: {is_valid_origin('http://localhost:8080', allowed)}")
    print(f"   'https://evil.com' valid: {is_valid_origin('https://evil.com', allowed)}")
    
    # Authentication headers
    print("\n2. Authentication Headers:")
    bearer = create_auth_header("my-token", auth_type="bearer")
    print(f"   Bearer: {bearer}")
    basic = create_auth_header("user:pass", auth_type="basic")
    print(f"   Basic: {basic}")
    
    # Secure session IDs
    print("\n3. Secure Session IDs:")
    session_id = generate_secure_session_id()
    print(f"   Generated: {session_id}")
    print(f"   Length: {len(session_id)} chars")
    
    # Security config
    print("\n4. Security Configuration:")
    config = SecurityConfig(
        allowed_origins=["localhost", "example.com"],
        require_auth=True
    )
    print(f"   Validate origin: {config.validate_origin}")
    print(f"   Require auth: {config.require_auth}")
    print(f"   Bind address: {config.get_bind_address()}")
