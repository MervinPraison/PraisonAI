"""
Streaming & Real-Time Performance Monitoring - Example 9

Demonstrates performance monitoring for streaming and real-time operations:
- Real-time performance tracking
- Streaming response monitoring
- Live performance metrics
- Continuous performance analysis

Shows how to monitor performance during streaming operations.
"""

import time
import threading
from datetime import datetime
from praisonaiagents import Agent
from praisonaiagents.telemetry import (
    monitor_function, track_api_call, performance_monitor,
    get_performance_report, get_function_stats
)

# Global variables for streaming simulation
streaming_active = False
streaming_stats = {
    'messages_processed': 0,
    'total_latency': 0.0,
    'errors': 0,
    'start_time': None
}

@monitor_function("stream_message_processing")
def process_stream_message(message_id: int, content: str):
    """Process a single streaming message with monitoring."""
    processing_start = time.time()
    
    print(f"📨 Processing stream message {message_id}: {content[:30]}...")
    
    # Simulate variable processing time
    processing_time = 0.05 + (message_id % 3) * 0.02  # Simulate varying complexity
    time.sleep(processing_time)
    
    # Simulate occasional errors
    if message_id % 20 == 0:  # Every 20th message fails
        raise Exception(f"Processing error for message {message_id}")
    
    processing_end = time.time()
    latency = processing_end - processing_start
    
    # Update streaming stats
    streaming_stats['messages_processed'] += 1
    streaming_stats['total_latency'] += latency
    
    return f"Processed message {message_id} in {latency:.3f}s"

@monitor_function("real_time_agent_response")
def get_real_time_agent_response(query: str, response_id: int):
    """Simulate real-time agent response with monitoring."""
    print(f"🤖 Generating real-time response {response_id} for: {query}")
    
    # Create a lightweight agent for streaming
    agent = Agent(
        instructions="You are a real-time assistant. Provide quick, helpful responses.",
        llm="gpt-5-nano"
    )
    
    with track_api_call(f"streaming_response_{response_id}"):
        # Simulate streaming response generation
        time.sleep(0.1)  # Base response time
        
        # In real implementation, this would be actual agent.start()
        response = agent.start(f"Quickly respond to: {query}")
        
        return response

@monitor_function("performance_metrics_collector")
def collect_live_metrics():
    """Collect live performance metrics during streaming."""
    
    while streaming_active:
        current_time = time.time()
        
        # Collect current performance data
        current_stats = performance_monitor.get_function_performance()
        api_stats = performance_monitor.get_api_call_performance()
        
        # Calculate streaming metrics
        if streaming_stats['start_time']:
            elapsed_time = current_time - streaming_stats['start_time']
            messages_per_second = streaming_stats['messages_processed'] / elapsed_time if elapsed_time > 0 else 0
            avg_latency = streaming_stats['total_latency'] / streaming_stats['messages_processed'] if streaming_stats['messages_processed'] > 0 else 0
            
            print(f"📊 Live Metrics - Messages/sec: {messages_per_second:.2f}, Avg Latency: {avg_latency:.3f}s")
        
        time.sleep(2)  # Update every 2 seconds

@monitor_function("streaming_simulation")
def simulate_streaming_workload():
    """Simulate a streaming workload with continuous monitoring."""
    global streaming_active, streaming_stats
    
    print("🌊 Starting streaming simulation...")
    streaming_active = True
    streaming_stats['start_time'] = time.time()
    
    # Start metrics collector in background
    metrics_thread = threading.Thread(target=collect_live_metrics)
    metrics_thread.daemon = True
    metrics_thread.start()
    
    # Simulate incoming stream messages
    messages = [
        "User question about AI",
        "Request for weather information",
        "Help with programming",
        "General knowledge query",
        "Technical support request",
        "Creative writing assistance",
        "Data analysis question",
        "Research inquiry"
    ]
    
    processed_responses = []
    
    try:
        for i in range(20):  # Process 20 streaming messages
            message = messages[i % len(messages)]
            
            try:
                # Process the stream message
                result = process_stream_message(i + 1, message)
                
                # Generate real-time response every 3rd message
                if (i + 1) % 3 == 0:
                    response = get_real_time_agent_response(message, i + 1)
                    processed_responses.append(response)
                
                # Brief pause between messages
                time.sleep(0.1)
                
            except Exception as e:
                streaming_stats['errors'] += 1
                print(f"❌ Error processing message {i + 1}: {e}")
        
    finally:
        streaming_active = False
        print("🛑 Streaming simulation completed")
    
    return processed_responses

@monitor_function("batch_vs_streaming_comparison")
def compare_batch_vs_streaming():
    """Compare batch vs streaming performance."""
    
    print("\n🔄 Comparing Batch vs Streaming Performance...")
    
    # Batch processing simulation
    print("\n📦 Batch Processing Test:")
    batch_start = time.time()
    
    batch_messages = [f"Batch message {i}" for i in range(10)]
    batch_results = []
    
    with track_api_call("batch_processing"):
        for i, message in enumerate(batch_messages):
            # Simulate batch processing (all at once)
            time.sleep(0.08)  # Batch processing time
            batch_results.append(f"Batch processed: {message}")
    
    batch_time = time.time() - batch_start
    
    # Streaming processing test (already done above)
    streaming_time = streaming_stats['total_latency']
    streaming_count = streaming_stats['messages_processed']
    
    print(f"\n📊 Batch vs Streaming Comparison:")
    print(f"  Batch Processing:")
    print(f"    Messages: {len(batch_results)}")
    print(f"    Total Time: {batch_time:.3f}s") 
    print(f"    Avg per Message: {batch_time/len(batch_results):.3f}s")
    
    print(f"  Streaming Processing:")
    print(f"    Messages: {streaming_count}")
    print(f"    Total Processing Time: {streaming_time:.3f}s")
    print(f"    Avg per Message: {streaming_time/streaming_count:.3f}s" if streaming_count > 0 else "    No messages processed")
    
    return batch_time, streaming_time

def main():
    """Main function demonstrating streaming performance monitoring."""
    print("=" * 70)
    print("EXAMPLE 9: Streaming & Real-Time Performance Monitoring")
    print("=" * 70)
    
    # Phase 1: Streaming simulation
    print("\n🌊 Phase 1: Streaming Workload Simulation")
    streaming_responses = simulate_streaming_workload()
    
    # Phase 2: Batch vs Streaming comparison
    print("\n📊 Phase 2: Batch vs Streaming Comparison")
    batch_time, streaming_time = compare_batch_vs_streaming()
    
    # Real-time Performance Analysis
    print("\n" + "=" * 70)
    print("📊 STREAMING PERFORMANCE ANALYSIS")
    print("=" * 70)
    
    # Streaming-specific metrics
    print("\n🌊 Streaming Metrics:")
    elapsed_total = time.time() - streaming_stats['start_time'] if streaming_stats['start_time'] else 0
    throughput = streaming_stats['messages_processed'] / elapsed_total if elapsed_total > 0 else 0
    avg_latency = streaming_stats['total_latency'] / streaming_stats['messages_processed'] if streaming_stats['messages_processed'] > 0 else 0
    error_rate = streaming_stats['errors'] / streaming_stats['messages_processed'] * 100 if streaming_stats['messages_processed'] > 0 else 0
    
    print(f"  Messages Processed: {streaming_stats['messages_processed']}")
    print(f"  Total Processing Time: {streaming_stats['total_latency']:.3f}s")
    print(f"  Average Latency: {avg_latency:.3f}s")
    print(f"  Throughput: {throughput:.2f} messages/second")
    print(f"  Error Rate: {error_rate:.2f}%")
    print(f"  Errors: {streaming_stats['errors']}")
    
    # Function performance during streaming
    print("\n⚡ Real-Time Function Performance:")
    stats = get_function_stats()
    streaming_functions = {k: v for k, v in stats.items() if 'stream' in k.lower() or 'real_time' in k.lower()}
    
    for func_name, data in streaming_functions.items():
        avg_time = data['total_time'] / data['call_count'] if data['call_count'] > 0 else 0
        print(f"  {func_name}:")
        print(f"    Calls: {data['call_count']}")
        print(f"    Avg Time: {avg_time:.3f}s")
        print(f"    Total Time: {data['total_time']:.3f}s")
    
    # Performance trend analysis
    print("\n📈 Performance Trends:")
    recent_performance = performance_monitor.get_function_performance()
    total_functions = len(recent_performance)
    total_calls = sum(data['call_count'] for data in recent_performance.values())
    
    print(f"  Functions Monitored: {total_functions}")
    print(f"  Total Function Calls: {total_calls}")
    print(f"  Average Calls per Function: {total_calls/total_functions:.1f}" if total_functions > 0 else "  No functions monitored")
    
    # Real-time vs Batch efficiency
    print(f"\n⚖️ Efficiency Analysis:")
    if batch_time > 0 and streaming_time > 0:
        efficiency_gain = (batch_time - streaming_time) / batch_time * 100
        print(f"  Streaming vs Batch Efficiency: {efficiency_gain:+.1f}%")
    
    if avg_latency > 0:
        if avg_latency < 0.1:
            print("  ✅ Excellent real-time performance (< 100ms)")
        elif avg_latency < 0.2:
            print("  ⚡ Good real-time performance (< 200ms)")
        else:
            print("  ⚠️ Consider optimization for better real-time performance")
    
    # Current performance report
    print("\n📋 Current Performance Report:")
    report = get_performance_report()
    print(report[:400] + "..." if len(report) > 400 else report)
    
    # Real-time optimization suggestions
    print(f"\n💡 Real-Time Optimization Recommendations:")
    
    if avg_latency > 0.15:
        print(f"  - Optimize message processing (current avg: {avg_latency:.3f}s)")
    if error_rate > 5:
        print(f"  - Investigate error patterns (current rate: {error_rate:.1f}%)")
    if throughput < 10:
        print(f"  - Consider parallel processing for better throughput")
    
    print("  - Monitor memory usage during extended streaming")
    print("  - Implement adaptive batching for optimal performance")
    
    return {
        'streaming_responses': len(streaming_responses),
        'messages_processed': streaming_stats['messages_processed'],
        'throughput': throughput,
        'average_latency': avg_latency,
        'error_rate': error_rate
    }

if __name__ == "__main__":
    result = main()
    print(f"\n🎉 Streaming monitoring completed!")
    print(f"Throughput: {result['throughput']:.2f} msg/s, Latency: {result['average_latency']:.3f}s")