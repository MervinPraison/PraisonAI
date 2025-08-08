"""
Error Handling with Performance Monitoring - Example 5

Demonstrates performance monitoring for error scenarios:
- Error rate tracking
- Failed operation timing
- Recovery mechanism performance
- Exception handling with monitoring

Shows how to monitor performance when things go wrong.
"""

import random
import time
from praisonaiagents import Agent
from praisonaiagents.telemetry import (
    monitor_function, track_api_call, get_function_stats,
    get_api_stats, performance_monitor
)

@monitor_function("unreliable_operation")
def simulate_unreliable_operation(operation_id: int, failure_rate: float = 0.3):
    """Simulate an operation that sometimes fails."""
    print(f"⚙️ Running operation {operation_id}...")
    
    # Simulate processing time
    time.sleep(random.uniform(0.05, 0.2))
    
    # Random failure simulation
    if random.random() < failure_rate:
        raise RuntimeError(f"Operation {operation_id} failed!")
    
    return f"Operation {operation_id} succeeded"

@monitor_function("retry_with_backoff")
def retry_operation(operation_id: int, max_retries: int = 3):
    """Retry an operation with exponential backoff and monitoring."""
    for attempt in range(max_retries):
        try:
            print(f"🔄 Attempt {attempt + 1} for operation {operation_id}")
            result = simulate_unreliable_operation(operation_id)
            print(f"✅ Operation {operation_id} succeeded on attempt {attempt + 1}")
            return result
        except Exception as e:
            print(f"❌ Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                # Exponential backoff
                sleep_time = 2 ** attempt * 0.1
                print(f"⏳ Waiting {sleep_time:.1f}s before retry...")
                time.sleep(sleep_time)
            else:
                print(f"💥 All {max_retries} attempts failed for operation {operation_id}")
                raise

@monitor_function("robust_agent_execution")
def run_robust_agent(query: str, with_error_simulation: bool = True):
    """Run agent with error handling and performance monitoring."""
    
    agent = Agent(
        instructions="""You are a resilient AI assistant. 
        Even when facing challenges, you provide helpful responses.
        If you encounter errors, acknowledge them and offer alternatives.""",
        llm="gpt-5-nano"
    )
    
    try:
        with track_api_call("robust_agent_request"):
            print(f"🚀 Processing query: {query}")
            
            if with_error_simulation and random.random() < 0.2:
                # Simulate API error
                raise Exception("Simulated API error")
            
            result = agent.start(query)
            return result
            
    except Exception as e:
        print(f"⚠️ Error during agent execution: {e}")
        
        # Fallback response with monitoring
        with track_api_call("fallback_response"):
            print("🔄 Using fallback response mechanism...")
            time.sleep(0.1)  # Simulate fallback processing
            return f"I encountered an error while processing '{query}', but I'm designed to be resilient. Let me provide a general response about this topic."

@monitor_function("batch_processing_with_errors")
def process_batch_with_error_handling(batch_size: int = 5):
    """Process a batch of operations with comprehensive error handling."""
    print(f"📦 Processing batch of {batch_size} operations with error monitoring...")
    
    results = []
    errors = []
    
    for i in range(batch_size):
        try:
            result = retry_operation(i + 1)
            results.append(result)
        except Exception as e:
            errors.append(f"Operation {i + 1}: {str(e)}")
    
    return results, errors

def main():
    """Main function demonstrating error handling with performance monitoring."""
    print("=" * 70)
    print("EXAMPLE 5: Error Handling Performance Monitoring")
    print("=" * 70)
    
    # Phase 1: Batch processing with errors
    print("\n📊 Phase 1: Batch Processing with Error Handling")
    successes, failures = process_batch_with_error_handling(5)
    
    print(f"\n📈 Batch Results:")
    print(f"  Successful operations: {len(successes)}")
    print(f"  Failed operations: {len(failures)}")
    
    # Phase 2: Agent execution with error scenarios
    print("\n🤖 Phase 2: Agent Execution with Error Scenarios")
    
    test_queries = [
        "What is artificial intelligence?",
        "How do computers work?",
        "Explain quantum physics",
    ]
    
    agent_results = []
    for query in test_queries:
        try:
            result = run_robust_agent(query, with_error_simulation=True)
            agent_results.append(result)
            print(f"✅ Query processed: '{query[:30]}...'")
        except Exception as e:
            print(f"❌ Query failed: '{query[:30]}...' - {e}")
    
    # Performance Analysis with Error Metrics
    print("\n" + "=" * 70)
    print("📊 ERROR HANDLING PERFORMANCE ANALYSIS")
    print("=" * 70)
    
    # Function performance with error rates
    print("\n📈 Function Performance (including errors):")
    stats = get_function_stats()
    for func_name, data in stats.items():
        avg_time = data['total_time'] / data['call_count'] if data['call_count'] > 0 else 0
        error_rate = data['error_count'] / data['call_count'] * 100 if data['call_count'] > 0 else 0
        success_rate = 100 - error_rate
        
        print(f"  {func_name}:")
        print(f"    Calls: {data['call_count']}")
        print(f"    Errors: {data['error_count']}")
        print(f"    Success Rate: {success_rate:.1f}%")
        print(f"    Avg Time: {avg_time:.3f}s")
    
    # API call reliability
    print("\n🌐 API Call Reliability:")
    api_stats = get_api_stats()
    for api_name, stats in api_stats.items():
        success_rate = stats['success_count'] / stats['call_count'] * 100 if stats['call_count'] > 0 else 0
        avg_time = stats['total_time'] / stats['call_count'] if stats['call_count'] > 0 else 0
        
        print(f"  {api_name}:")
        print(f"    Success Rate: {success_rate:.1f}%")
        print(f"    Average Response Time: {avg_time:.3f}s")
        print(f"    Total Calls: {stats['call_count']}")
    
    # Error patterns analysis
    print("\n⚠️ Error Patterns:")
    total_operations = sum(s['call_count'] for s in api_stats.values())
    total_errors = sum(s['error_count'] for s in api_stats.values())
    overall_success_rate = ((total_operations - total_errors) / total_operations * 100) if total_operations > 0 else 0
    
    print(f"  Total Operations: {total_operations}")
    print(f"  Total Errors: {total_errors}")
    print(f"  Overall Success Rate: {overall_success_rate:.1f}%")
    
    # Recommendations
    print(f"\n💡 Performance Recommendations:")
    if overall_success_rate < 90:
        print("  - Consider implementing more robust error handling")
        print("  - Review retry strategies and backoff algorithms")
    if total_errors > 0:
        print(f"  - Investigate {total_errors} errors for root cause analysis")
    print("  - Monitor error patterns for system reliability improvements")
    
    return {
        'successful_operations': len(successes),
        'failed_operations': len(failures), 
        'agent_results': len(agent_results),
        'overall_success_rate': overall_success_rate
    }

if __name__ == "__main__":
    result = main()
    print(f"\n✅ Error handling monitoring completed!")
    print(f"Success rate: {result['overall_success_rate']:.1f}%")