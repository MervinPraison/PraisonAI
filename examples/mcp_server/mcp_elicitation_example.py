#!/usr/bin/env python3
"""
MCP Elicitation Example

Demonstrates the Elicitation API per MCP 2025-11-25 specification.
Elicitation allows servers to request additional information from users.

Supports two modes:
- Form mode: Structured data collection with JSON schema validation
- URL mode: External URLs for sensitive interactions (OAuth, payments)

Usage:
    python mcp_elicitation_example.py
"""

import asyncio
from praisonai.mcp_server.elicitation import (
    ElicitationHandler,
    ElicitationResult,
    create_form_request,
    create_url_request,
)


async def main():
    print("=" * 60)
    print("MCP Elicitation Example (2025-11-25 Specification)")
    print("=" * 60)
    
    # Create handler in CI mode (non-interactive) with defaults
    handler = ElicitationHandler(
        ci_mode=True,
        ci_defaults={
            "name": "John Doe",
            "email": "john@example.com",
            "confirm": True,
        }
    )
    
    # 1. Form mode elicitation
    print("\n1. Form Mode Elicitation")
    print("-" * 40)
    
    form_request = create_form_request(
        message="Please provide your contact information",
        properties={
            "name": {
                "type": "string",
                "description": "Your full name",
            },
            "email": {
                "type": "string",
                "format": "email",
                "description": "Your email address",
            },
            "age": {
                "type": "integer",
                "description": "Your age",
                "default": 25,
            },
        },
        required=["name", "email"],
        title="Contact Form",
    )
    
    print(f"   Request message: {form_request.message}")
    print(f"   Request dict: {form_request.to_dict()}")
    
    result = await handler.elicit(form_request)
    print(f"\n   Response action: {result.action.value}")
    print(f"   Response content: {result.content}")
    print(f"   MCP format: {result.to_dict()}")
    
    # 2. URL mode elicitation
    print("\n2. URL Mode Elicitation")
    print("-" * 40)
    
    url_request = create_url_request(
        message="Please authorize access to your GitHub account",
        url="https://github.com/login/oauth/authorize?client_id=xxx",
        elicitation_id="oauth-github-123",
    )
    
    print(f"   Request message: {url_request.message}")
    print(f"   Request URL: {url_request.url}")
    print(f"   Elicitation ID: {url_request.elicitation_id}")
    print(f"   Request dict: {url_request.to_dict()}")
    
    # URL mode returns decline in CI mode (cannot be automated)
    result = await handler.elicit(url_request)
    print(f"\n   Response action: {result.action.value}")
    print("   (URL mode cannot be completed in CI mode)")
    
    # 3. Using factory methods
    print("\n3. ElicitationResult Factory Methods")
    print("-" * 40)
    
    # Accept with data
    accept_result = ElicitationResult.accept({"confirmed": True, "value": 42})
    print(f"   Accept: {accept_result.to_dict()}")
    
    # Decline with error
    decline_result = ElicitationResult.decline("Invalid input provided")
    print(f"   Decline: {decline_result.to_dict()}")
    
    # Cancel
    cancel_result = ElicitationResult.cancel()
    print(f"   Cancel: {cancel_result.to_dict()}")
    
    # 4. Custom handler
    print("\n4. Custom Elicitation Handler")
    print("-" * 40)
    
    async def custom_handler(request):
        """Custom handler that auto-approves everything."""
        print(f"   Custom handler received: {request.message}")
        return ElicitationResult.accept({"auto_approved": True})
    
    custom_elicit = ElicitationHandler()
    custom_elicit.set_custom_handler(custom_handler)
    
    test_request = create_form_request(
        message="Test custom handler",
        properties={"test": {"type": "string"}},
    )
    
    result = await custom_elicit.elicit(test_request)
    print(f"   Custom result: {result.to_dict()}")
    
    print("\n" + "=" * 60)
    print("Elicitation Example Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
