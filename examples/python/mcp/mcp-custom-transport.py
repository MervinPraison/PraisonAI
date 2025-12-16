"""
MCP Custom Transport Example

Demonstrates how to create custom MCP transports by extending
the BaseTransport class.

Features:
- BaseTransport abstract class
- TransportRegistry for registration
- TransportConfig for configuration
- Pluggable transport mechanism

Protocol: MCP 2025-11-25
"""

from praisonaiagents.mcp.mcp_transport import (
    BaseTransport,
    TransportConfig,
    TransportRegistry,
    get_default_registry
)

# Custom transport implementation
class MyCustomTransport(BaseTransport):
    """Example custom transport implementation."""
    
    def __init__(self, url: str, config: TransportConfig = None):
        self.url = url
        self.config = config or TransportConfig()
        self._connected = False
    
    async def connect(self):
        """Establish connection."""
        print(f"Connecting to {self.url}...")
        self._connected = True
        print("Connected!")
    
    async def send(self, message: dict):
        """Send JSON-RPC message."""
        if not self._connected:
            raise RuntimeError("Not connected")
        print(f"Sending: {message}")
    
    async def receive(self) -> dict:
        """Receive JSON-RPC message."""
        if not self._connected:
            raise RuntimeError("Not connected")
        return {"jsonrpc": "2.0", "result": "ok", "id": 1}
    
    async def close(self):
        """Close connection."""
        print("Closing connection...")
        self._connected = False
    
    @property
    def is_connected(self) -> bool:
        return self._connected


if __name__ == "__main__":
    import asyncio
    
    print("MCP Custom Transport Example")
    print("=" * 50)
    
    # 1. Transport configuration
    print("\n1. Transport Configuration:")
    config = TransportConfig(
        timeout=60,
        debug=True,
        retry_count=3,
        retry_delay=1.0,
        auth_token="my-token"
    )
    print(f"   Timeout: {config.timeout}s")
    print(f"   Debug: {config.debug}")
    print(f"   Retry count: {config.retry_count}")
    
    # 2. Default registry
    print("\n2. Default Transport Registry:")
    registry = get_default_registry()
    print(f"   Registered transports: {registry.list_transports()}")
    
    # 3. Register custom transport
    print("\n3. Registering Custom Transport:")
    custom_registry = TransportRegistry()
    custom_registry.register("my_custom", MyCustomTransport)
    print(f"   Registered: {custom_registry.list_transports()}")
    
    # 4. Use custom transport
    print("\n4. Using Custom Transport:")
    
    async def demo():
        transport = MyCustomTransport("custom://localhost:8080", config)
        
        async with transport:
            await transport.send({"jsonrpc": "2.0", "method": "test", "id": 1})
            response = await transport.receive()
            print(f"   Response: {response}")
    
    asyncio.run(demo())
    
    # 5. BaseTransport interface
    print("\n5. BaseTransport Interface:")
    print("   Required methods:")
    print("   - async connect()")
    print("   - async send(message: dict)")
    print("   - async receive() -> dict")
    print("   - async close()")
    print("   - @property is_connected -> bool")
