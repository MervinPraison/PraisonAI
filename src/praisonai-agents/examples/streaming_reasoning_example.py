"""
Streaming with Reasoning Content Example

This example demonstrates how to handle streaming events with reasoning content
from models like o1, o1-mini, and deepseek-reasoner.

The is_reasoning flag allows you to distinguish between:
- Reasoning/thinking content (is_reasoning=True)
- Final response content (is_reasoning=False)
"""

from praisonaiagents import Agent
from praisonaiagents.streaming import StreamEvent, StreamEventType, StreamMetrics


def create_styled_callback():
    """Create a callback that styles reasoning content differently."""
    
    def callback(event: StreamEvent):
        if event.type == StreamEventType.DELTA_TEXT:
            if event.is_reasoning:
                # Dim gray for reasoning content
                print(f"\033[90m{event.content}\033[0m", end="", flush=True)
            else:
                # Normal for response content
                print(event.content, end="", flush=True)
        elif event.type == StreamEventType.STREAM_END:
            print()  # Newline at end
    
    return callback


def create_collecting_callback():
    """Create a callback that collects reasoning and response separately."""
    reasoning_parts = []
    response_parts = []
    
    def callback(event: StreamEvent):
        if event.type == StreamEventType.DELTA_TEXT:
            if event.is_reasoning:
                reasoning_parts.append(event.content)
            else:
                response_parts.append(event.content)
    
    def get_results():
        return {
            "reasoning": "".join(reasoning_parts),
            "response": "".join(response_parts)
        }
    
    return callback, get_results


def example_basic_streaming():
    """Basic streaming with reasoning detection."""
    print("=" * 60)
    print("Example 1: Basic Streaming with Reasoning Detection")
    print("=" * 60)
    
    agent = Agent(
        name="thinker",
        instructions="Think step by step before answering.",
        llm="gpt-4o-mini"  # Change to o1-mini for actual reasoning
    )
    
    # Add styled callback
    agent.stream_emitter.add_callback(create_styled_callback())
    
    # Enable metrics
    agent.stream_emitter.enable_metrics()
    
    # Run with streaming
    response = agent.start("What is 15 * 23?", stream=True)
    
    # Show metrics
    metrics = agent.stream_emitter.get_metrics()
    if metrics:
        print(f"\n📊 {metrics.format_summary()}")
    
    return response


def example_collect_separately():
    """Collect reasoning and response content separately."""
    print("\n" + "=" * 60)
    print("Example 2: Collect Reasoning and Response Separately")
    print("=" * 60)
    
    agent = Agent(
        name="analyzer",
        instructions="Analyze the problem carefully.",
        llm="gpt-4o-mini"
    )
    
    # Create collecting callback
    callback, get_results = create_collecting_callback()
    agent.stream_emitter.add_callback(callback)
    
    # Run with streaming
    response = agent.start("Explain why the sky is blue.", stream=True)
    
    # Get separated results
    results = get_results()
    
    print(f"\n📝 Reasoning length: {len(results['reasoning'])} chars")
    print(f"📝 Response length: {len(results['response'])} chars")
    
    return response


def example_with_metrics():
    """Track streaming performance metrics."""
    print("\n" + "=" * 60)
    print("Example 3: Streaming with Performance Metrics")
    print("=" * 60)
    
    metrics = StreamMetrics()
    
    def metrics_callback(event: StreamEvent):
        metrics.update_from_event(event)
        
        if event.type == StreamEventType.FIRST_TOKEN:
            print("⚡ First token received!")
        elif event.type == StreamEventType.DELTA_TEXT:
            print(event.content, end="", flush=True)
        elif event.type == StreamEventType.STREAM_END:
            print()
    
    agent = Agent(name="assistant", llm="gpt-4o-mini")
    agent.stream_emitter.add_callback(metrics_callback)
    
    response = agent.start("Write a haiku about coding.", stream=True)
    
    print("\n📊 Performance Metrics:")
    print(f"   TTFT: {metrics.ttft * 1000:.0f}ms")
    print(f"   Stream Duration: {metrics.stream_duration * 1000:.0f}ms")
    print(f"   Total Time: {metrics.total_time * 1000:.0f}ms")
    print(f"   Tokens: {metrics.token_count}")
    print(f"   Speed: {metrics.tokens_per_second:.1f} tokens/sec")
    
    return response


def example_multi_agent_context():
    """Show agent context in multi-agent scenarios."""
    print("\n" + "=" * 60)
    print("Example 4: Multi-Agent Context")
    print("=" * 60)
    
    def context_callback(event: StreamEvent):
        if event.type == StreamEventType.DELTA_TEXT:
            prefix = f"[{event.agent_id}] " if event.agent_id else ""
            print(f"{prefix}{event.content}", end="", flush=True)
        elif event.type == StreamEventType.STREAM_END:
            print()
    
    # Note: agent_id is populated when using multi-agent workflows
    agent = Agent(name="helper", llm="gpt-4o-mini")
    agent.stream_emitter.add_callback(context_callback)
    
    response = agent.start("Say hello!", stream=True)
    
    return response


if __name__ == "__main__":
    print("🚀 PraisonAI Streaming with Reasoning Examples\n")
    
    # Run examples
    example_basic_streaming()
    example_collect_separately()
    example_with_metrics()
    example_multi_agent_context()
    
    print("\n✅ All examples completed!")
