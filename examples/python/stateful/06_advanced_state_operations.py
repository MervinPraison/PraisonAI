#!/usr/bin/env python3
"""
Advanced State Operations Example
================================

This example demonstrates advanced state management techniques including:
- Working with complex nested state
- State transformations and calculations
- Error handling with state
- State-based caching
- Concurrent state updates

Run this example:
    python 06_advanced_state_operations.py
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
import json
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional


def manage_nested_state() -> str:
    """Demonstrate working with complex nested state structures"""
    # Initialize complex state structure
    if not workflow.has_state("system_config"):
        workflow.set_state("system_config", {
            "database": {
                "host": "localhost",
                "port": 5432,
                "connections": {
                    "max": 100,
                    "active": 0,
                    "idle": 100
                }
            },
            "api": {
                "endpoints": {
                    "v1": {"users": True, "products": True},
                    "v2": {"users": True, "products": True, "analytics": False}
                },
                "rate_limits": {
                    "global": 1000,
                    "per_user": 100
                }
            },
            "features": {
                "authentication": True,
                "caching": True,
                "monitoring": False
            }
        })
    
    # Get and modify nested state
    config = workflow.get_state("system_config")
    
    # Update nested values
    config["database"]["connections"]["active"] += 10
    config["database"]["connections"]["idle"] -= 10
    config["api"]["endpoints"]["v2"]["analytics"] = True
    config["features"]["monitoring"] = True
    
    # Add new nested section
    config["performance"] = {
        "cache_size": "512MB",
        "worker_threads": 4,
        "optimizations": {
            "query_cache": True,
            "connection_pooling": True,
            "lazy_loading": False
        }
    }
    
    # Save updated config
    workflow.set_state("system_config", config)
    
    # Create a summary
    summary = f"""
    Nested State Update Complete:
    - Active DB Connections: {config['database']['connections']['active']}
    - API v2 Analytics: {'Enabled' if config['api']['endpoints']['v2']['analytics'] else 'Disabled'}
    - Monitoring: {'Enabled' if config['features']['monitoring'] else 'Disabled'}
    - New Performance Section Added
    """
    
    return summary


def implement_state_cache() -> Dict[str, Any]:
    """Implement caching mechanism using state"""
    cache_key = "api_responses"
    
    # Initialize cache if not exists
    if not workflow.has_state(cache_key):
        workflow.set_state(cache_key, {})
        workflow.set_state("cache_stats", {
            "hits": 0,
            "misses": 0,
            "evictions": 0
        })
    
    # Simulate API calls with caching
    api_calls = ["user_123", "product_456", "user_123", "order_789", "product_456"]
    results = []
    
    cache = workflow.get_state(cache_key)
    cache_stats = workflow.get_state("cache_stats")
    max_cache_size = 3
    cache_ttl_seconds = 300  # 5 minutes
    
    for call_id in api_calls:
        current_time = time.time()
        
        # Check cache
        if call_id in cache:
            cached_data = cache[call_id]
            # Check if cache is still valid
            if current_time - cached_data["timestamp"] < cache_ttl_seconds:
                # Cache hit
                cache_stats["hits"] += 1
                results.append({
                    "id": call_id,
                    "data": cached_data["data"],
                    "source": "cache",
                    "age": current_time - cached_data["timestamp"]
                })
                continue
        
        # Cache miss - simulate API call
        cache_stats["misses"] += 1
        api_data = f"data_for_{call_id}_{int(current_time)}"
        
        # Add to cache with eviction if needed
        if len(cache) >= max_cache_size:
            # Evict oldest entry
            oldest_key = min(cache.keys(), key=lambda k: cache[k]["timestamp"])
            del cache[oldest_key]
            cache_stats["evictions"] += 1
        
        cache[call_id] = {
            "data": api_data,
            "timestamp": current_time
        }
        
        results.append({
            "id": call_id,
            "data": api_data,
            "source": "api",
            "age": 0
        })
    
    # Update state
    workflow.set_state(cache_key, cache)
    workflow.set_state("cache_stats", cache_stats)
    
    return {
        "results": results,
        "cache_stats": cache_stats,
        "cache_size": len(cache)
    }


def calculate_derived_metrics() -> Dict[str, Any]:
    """Calculate and store derived metrics from state data"""
    # Get various state values
    total_records = workflow.get_state("total_records_processed", 0)
    processing_time = workflow.get_state("total_processing_time", 0)
    error_count = workflow.get_state("total_errors", 0)
    successful_operations = workflow.get_state("successful_operations", 0)
    
    # Initialize metrics state
    if not workflow.has_state("performance_metrics"):
        workflow.set_state("performance_metrics", {})
    
    metrics = workflow.get_state("performance_metrics")
    
    # Calculate derived metrics
    if processing_time > 0:
        throughput = total_records / processing_time
    else:
        throughput = 0
    
    if successful_operations > 0:
        error_rate = (error_count / (successful_operations + error_count)) * 100
    else:
        error_rate = 0
    
    # Moving averages
    if "throughput_history" not in metrics:
        metrics["throughput_history"] = []
    
    metrics["throughput_history"].append(throughput)
    if len(metrics["throughput_history"]) > 10:
        metrics["throughput_history"] = metrics["throughput_history"][-10:]
    
    avg_throughput = sum(metrics["throughput_history"]) / len(metrics["throughput_history"])
    
    # Update metrics
    metrics.update({
        "current_throughput": throughput,
        "average_throughput": avg_throughput,
        "error_rate": error_rate,
        "efficiency": (successful_operations / (successful_operations + error_count) * 100) if (successful_operations + error_count) > 0 else 0,
        "last_calculated": datetime.now().isoformat()
    })
    
    workflow.set_state("performance_metrics", metrics)
    
    return metrics


def handle_state_transactions() -> str:
    """Demonstrate transaction-like state updates with rollback capability"""
    # Create transaction checkpoint
    transaction_id = f"txn_{int(time.time())}"
    
    # Save current state as checkpoint
    checkpoint = {
        "balance": workflow.get_state("account_balance", 1000),
        "transactions": workflow.get_state("transaction_history", []).copy(),
        "inventory": workflow.get_state("inventory", {"item_a": 10, "item_b": 20}).copy()
    }
    
    workflow.set_state(f"checkpoint_{transaction_id}", checkpoint)
    
    try:
        # Perform multiple state updates (simulating a transaction)
        balance = workflow.get_state("account_balance", 1000)
        inventory = workflow.get_state("inventory", {"item_a": 10, "item_b": 20})
        
        # Simulate purchase
        item_cost = 250
        if balance >= item_cost and inventory["item_a"] > 0:
            # Update balance
            workflow.set_state("account_balance", balance - item_cost)
            
            # Update inventory
            inventory["item_a"] -= 1
            workflow.set_state("inventory", inventory)
            
            # Add to transaction history
            workflow.append_to_state("transaction_history", {
                "id": transaction_id,
                "type": "purchase",
                "item": "item_a",
                "amount": item_cost,
                "timestamp": datetime.now().isoformat(),
                "status": "completed"
            })
            
            # Simulate potential failure
            if workflow.get_state("simulate_failure", False):
                raise Exception("Simulated transaction failure")
            
            result = f"Transaction {transaction_id} completed successfully"
        else:
            raise Exception("Insufficient balance or inventory")
            
    except Exception as e:
        # Rollback on failure
        checkpoint = workflow.get_state(f"checkpoint_{transaction_id}")
        workflow.set_state("account_balance", checkpoint["balance"])
        workflow.set_state("transaction_history", checkpoint["transactions"])
        workflow.set_state("inventory", checkpoint["inventory"])
        
        # Log failed transaction
        workflow.append_to_state("failed_transactions", {
            "id": transaction_id,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        })
        
        result = f"Transaction {transaction_id} failed and rolled back: {str(e)}"
    
    finally:
        # Clean up checkpoint
        workflow.delete_state(f"checkpoint_{transaction_id}")
    
    return result


def manage_state_versioning() -> Dict[str, Any]:
    """Implement state versioning for audit trail"""
    config_key = "application_config"
    
    # Initialize versioning system
    if not workflow.has_state("state_versions"):
        workflow.set_state("state_versions", {})
        workflow.set_state("version_counter", 0)
    
    # Get current config
    current_config = workflow.get_state(config_key, {
        "theme": "light",
        "language": "en",
        "notifications": True
    })
    
    # Create new version before changes
    version_counter = workflow.get_state("version_counter")
    version_counter += 1
    workflow.set_state("version_counter", version_counter)
    
    # Store current version
    versions = workflow.get_state("state_versions")
    version_id = f"v{version_counter}"
    versions[version_id] = {
        "config": current_config.copy(),
        "timestamp": datetime.now().isoformat(),
        "hash": hashlib.md5(json.dumps(current_config, sort_keys=True).encode()).hexdigest()
    }
    
    # Make changes
    new_config = current_config.copy()
    new_config["theme"] = "dark"
    new_config["language"] = "es"
    new_config["font_size"] = 14
    
    # Store new version
    workflow.set_state(config_key, new_config)
    workflow.set_state("state_versions", versions)
    
    # Calculate diff
    changes = []
    for key in set(list(current_config.keys()) + list(new_config.keys())):
        old_val = current_config.get(key, "not_set")
        new_val = new_config.get(key, "not_set")
        if old_val != new_val:
            changes.append({
                "field": key,
                "old": old_val,
                "new": new_val
            })
    
    return {
        "version": version_id,
        "changes": changes,
        "total_versions": len(versions),
        "config_hash": versions[version_id]["hash"]
    }


def aggregate_distributed_state() -> str:
    """Simulate aggregating state from multiple sources"""
    # Initialize distributed nodes state
    nodes = ["node_1", "node_2", "node_3"]
    
    for node in nodes:
        if not workflow.has_state(f"{node}_metrics"):
            workflow.set_state(f"{node}_metrics", {
                "requests": int(time.time() % 1000),
                "errors": int(time.time() % 10),
                "latency": int(time.time() % 100),
                "uptime": 99.5 + (time.time() % 0.5)
            })
    
    # Aggregate metrics
    aggregated = {
        "total_requests": 0,
        "total_errors": 0,
        "avg_latency": 0,
        "min_uptime": 100,
        "nodes_reporting": 0
    }
    
    latencies = []
    
    for node in nodes:
        node_metrics = workflow.get_state(f"{node}_metrics")
        if node_metrics:
            aggregated["total_requests"] += node_metrics["requests"]
            aggregated["total_errors"] += node_metrics["errors"]
            latencies.append(node_metrics["latency"])
            aggregated["min_uptime"] = min(aggregated["min_uptime"], node_metrics["uptime"])
            aggregated["nodes_reporting"] += 1
    
    if latencies:
        aggregated["avg_latency"] = sum(latencies) / len(latencies)
    
    # Store aggregated state with timestamp
    workflow.set_state("aggregated_metrics", {
        "data": aggregated,
        "timestamp": datetime.now().isoformat(),
        "nodes": nodes
    })
    
    # Create summary
    summary = f"""
    Distributed State Aggregation:
    - Nodes: {aggregated['nodes_reporting']}/{len(nodes)}
    - Total Requests: {aggregated['total_requests']}
    - Total Errors: {aggregated['total_errors']}
    - Average Latency: {aggregated['avg_latency']:.2f}ms
    - Minimum Uptime: {aggregated['min_uptime']:.2f}%
    """
    
    return summary


def generate_advanced_report() -> str:
    """Generate comprehensive report on advanced state operations"""
    system_config = workflow.get_state("system_config", {})
    cache_stats = workflow.get_state("cache_stats", {})
    performance_metrics = workflow.get_state("performance_metrics", {})
    transaction_history = workflow.get_state("transaction_history", [])
    failed_transactions = workflow.get_state("failed_transactions", [])
    versions = workflow.get_state("state_versions", {})
    aggregated_metrics = workflow.get_state("aggregated_metrics", {})
    
    report = f"""
    Advanced State Operations Report
    ===============================
    
    System Configuration:
    - Database Connections: {system_config.get('database', {}).get('connections', {}).get('active', 0)} active
    - Features Enabled: {sum(1 for v in system_config.get('features', {}).values() if v)}
    - Performance Optimizations: {sum(1 for v in system_config.get('performance', {}).get('optimizations', {}).values() if v)}
    
    Cache Performance:
    - Cache Hits: {cache_stats.get('hits', 0)}
    - Cache Misses: {cache_stats.get('misses', 0)}
    - Hit Rate: {(cache_stats.get('hits', 0) / (cache_stats.get('hits', 0) + cache_stats.get('misses', 0)) * 100):.1f}%
    - Evictions: {cache_stats.get('evictions', 0)}
    
    Performance Metrics:
    - Current Throughput: {performance_metrics.get('current_throughput', 0):.2f} records/sec
    - Average Throughput: {performance_metrics.get('average_throughput', 0):.2f} records/sec
    - Error Rate: {performance_metrics.get('error_rate', 0):.2f}%
    - Efficiency: {performance_metrics.get('efficiency', 0):.2f}%
    
    Transaction Management:
    - Successful Transactions: {len(transaction_history)}
    - Failed Transactions: {len(failed_transactions)}
    - Current Balance: ${workflow.get_state('account_balance', 0)}
    
    State Versioning:
    - Total Versions: {len(versions)}
    - Latest Version: {max(versions.keys()) if versions else 'None'}
    
    Distributed Aggregation:
    """
    
    if aggregated_metrics:
        data = aggregated_metrics.get('data', {})
        report += f"""
    - Reporting Nodes: {data.get('nodes_reporting', 0)}
    - Total Requests: {data.get('total_requests', 0)}
    - Average Latency: {data.get('avg_latency', 0):.2f}ms
    - System Uptime: {data.get('min_uptime', 0):.2f}%
    """
    
    return report


# Create agents
state_manager = Agent(
    name="StateManager",
    role="Manage complex state operations",
    goal="Demonstrate advanced state management techniques",
    backstory="An expert in state management",
    tools=[manage_nested_state, handle_state_transactions, manage_state_versioning],
    llm="gpt-4o-mini",
    verbose=True
)

cache_manager = Agent(
    name="CacheManager",
    role="Implement and manage state-based caching",
    goal="Optimize performance with intelligent caching",
    backstory="A caching specialist",
    tools=[implement_state_cache],
    llm="gpt-4o-mini",
    verbose=True
)

metrics_calculator = Agent(
    name="MetricsCalculator",
    role="Calculate derived metrics from state",
    goal="Provide insights through metric calculations",
    backstory="A data analytics expert",
    tools=[calculate_derived_metrics, aggregate_distributed_state],
    llm="gpt-4o-mini",
    verbose=True
)

report_generator = Agent(
    name="ReportGenerator",
    role="Generate comprehensive reports",
    goal="Document all advanced state operations",
    backstory="A reporting specialist",
    tools=[generate_advanced_report],
    llm="gpt-4o-mini",
    verbose=True
)

# Create tasks
tasks = [
    Task(
        name="setup_nested_state",
        description="Set up and manage complex nested state structures",
        expected_output="Nested state configuration summary",
        agent=state_manager,
        tools=[manage_nested_state]
    ),
    Task(
        name="implement_caching",
        description="Implement state-based caching with the API calls simulation",
        expected_output="Cache implementation results",
        agent=cache_manager,
        tools=[implement_state_cache]
    ),
    Task(
        name="test_transactions",
        description="Test transaction-like state updates with rollback",
        expected_output="Transaction test results",
        agent=state_manager,
        tools=[handle_state_transactions]
    ),
    Task(
        name="setup_versioning",
        description="Implement state versioning for configuration changes",
        expected_output="Versioning implementation results",
        agent=state_manager,
        tools=[manage_state_versioning]
    ),
    Task(
        name="calculate_metrics",
        description="Calculate derived performance metrics from state",
        expected_output="Calculated metrics",
        agent=metrics_calculator,
        tools=[calculate_derived_metrics]
    ),
    Task(
        name="aggregate_states",
        description="Aggregate state from distributed nodes",
        expected_output="Aggregation summary",
        agent=metrics_calculator,
        tools=[aggregate_distributed_state]
    ),
    Task(
        name="generate_report",
        description="Generate final report on all advanced state operations",
        expected_output="Comprehensive state operations report",
        agent=report_generator,
        tools=[generate_advanced_report]
    )
]

# Create workflow
workflow = PraisonAIAgents(
    agents=[state_manager, cache_manager, metrics_calculator, report_generator],
    tasks=tasks,
    verbose=True,
    process="sequential"
)

# Initialize some state for demonstrations
print("\n=== Initializing Advanced State Operations ===")
workflow.set_state("total_records_processed", 5000)
workflow.set_state("total_processing_time", 120)
workflow.set_state("total_errors", 23)
workflow.set_state("successful_operations", 477)

# Run workflow
result = workflow.start()

# Display final state summary
print("\n=== Final State Summary ===")
all_state = workflow.get_all_state()
print(f"Total state keys: {len(all_state)}")
print(f"State size (JSON): {len(json.dumps(all_state))} characters")

# Show state categories
categories = {
    "config": 0,
    "metrics": 0,
    "cache": 0,
    "transaction": 0,
    "version": 0,
    "other": 0
}

for key in all_state.keys():
    if "config" in key:
        categories["config"] += 1
    elif "metric" in key or "performance" in key:
        categories["metrics"] += 1
    elif "cache" in key:
        categories["cache"] += 1
    elif "transaction" in key or "balance" in key:
        categories["transaction"] += 1
    elif "version" in key:
        categories["version"] += 1
    else:
        categories["other"] += 1

print("\nState Categories:")
for category, count in categories.items():
    print(f"  - {category}: {count} keys")