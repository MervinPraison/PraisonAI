"""
Examples of advanced tools functionality for PraisonAI Agents.

This module demonstrates how to use the new advanced tool features:
- Pre/Post execution hooks
- Tool-level caching with TTL
- External execution markers
- Structured user input fields
"""

from praisonaiagents.tools import tool, cache, external, user_input
from praisonaiagents.tools import Field, InputGroup, Choice, Range, Pattern
from praisonaiagents.tools import ToolContext, set_global_hooks, register_external_handler

import time
import requests
from typing import List, Dict, Any


# Example 1: Pre/Post Execution Hooks
def log_start(context: ToolContext):
    """Log when a tool starts executing."""
    print(f"🚀 Starting {context.tool_name} with args: {context.args}")

def log_end(context: ToolContext):
    """Log when a tool finishes executing."""
    if context.error:
        print(f"❌ {context.tool_name} failed: {context.error}")
    else:
        print(f"✅ {context.tool_name} completed in {context.execution_time:.2f}s")

@tool(
    before=log_start,
    after=log_end
)
def calculate_metrics(data: List[float]) -> Dict[str, float]:
    """Calculate basic statistics for a list of numbers."""
    if not data:
        return {"error": "No data provided"}
    
    return {
        "mean": sum(data) / len(data),
        "min": min(data),
        "max": max(data),
        "count": len(data)
    }


# Example 2: Multiple hooks with priority
def validate_input(context: ToolContext):
    """Validate input data."""
    if context.args and len(context.args[0]) == 0:
        raise ValueError("Input data cannot be empty")

from praisonaiagents.tools import Priority

@tool(
    before=[
        (validate_input, Priority.HIGHEST),  # Runs first
        (log_start, Priority.MEDIUM)         # Runs second
    ],
    after=log_end
)
def process_data(input_data: str) -> str:
    """Process input data with validation."""
    return input_data.upper()


# Example 3: Error handling hook
def error_handler(context: ToolContext):
    """Handle tool errors gracefully."""
    if context.error:
        print(f"🔧 Handling error in {context.tool_name}: {context.error}")
        # Can modify the error or suppress it
        if "network" in str(context.error).lower():
            context.error = None
            context.result = {"status": "offline", "message": "Network unavailable"}

@tool(after=error_handler)
def risky_operation(fail: bool = False):
    """An operation that might fail."""
    if fail:
        raise Exception("Network connection failed")
    return {"status": "success"}


# Example 4: Simple caching
@tool
@cache(ttl=300)  # 5 minutes
def fetch_weather(city: str) -> Dict[str, Any]:
    """Fetch weather data with caching."""
    # Simulate API call
    time.sleep(1)  # Simulate network delay
    return {
        "city": city,
        "temperature": 22,
        "condition": "sunny",
        "timestamp": time.time()
    }


# Example 5: Advanced caching with custom key and condition
@tool
@cache(
    ttl=3600,  # 1 hour
    key=lambda city, date: f"{city}:{date}",  # Custom cache key
    condition=lambda result: result.get('status') == 'success',  # Only cache successful results
    tags=['weather', 'historical']
)
def get_historical_weather(city: str, date: str) -> Dict[str, Any]:
    """Get historical weather data with advanced caching."""
    # Simulate API call
    return {
        "city": city,
        "date": date,
        "temperature": 18,
        "status": "success"
    }


# Example 6: External execution markers
@tool
@external
def run_on_gpu(model_path: str, data: List[float]) -> Dict[str, Any]:
    """Run model inference on GPU (marked for external execution)."""
    # This would pause execution and return control to handler
    return {"predictions": [x * 2 for x in data]}


# Example 7: External with metadata
@tool
@external(
    executor="gpu_cluster",
    requirements=["cuda>=11.0", "torch>=2.0"],
    estimated_time=300  # 5 minutes
)
def train_model(dataset: str, hyperparams: Dict[str, Any]) -> Dict[str, Any]:
    """Train a model on GPU cluster."""
    return {"model_id": "model_123", "accuracy": 0.95}


# Example 8: Conditional external execution
@tool
@external(when=lambda args: len(args[0]) > 1000)  # Only external if data is large
def process_large_data(data: List[Any], threshold: int = 1000) -> Dict[str, Any]:
    """Process data, using external execution for large datasets."""
    return {"processed_count": len(data), "external": len(data) > threshold}


# Example 9: Structured user input fields
@tool
@user_input(
    Field(name="confirm", type=bool, description="Proceed with deletion?"),
    Field(name="reason", type=str, description="Reason for deletion", required=False)
)
def delete_records(confirm: bool, reason: str = None) -> Dict[str, Any]:
    """Delete records with user confirmation."""
    if not confirm:
        return {"status": "cancelled", "message": "Deletion cancelled by user"}
    
    return {
        "status": "deleted",
        "reason": reason or "No reason provided",
        "deleted_count": 10
    }


# Example 10: Advanced field types
@tool
@user_input(
    Field(
        name="priority",
        type=Choice(["low", "medium", "high"]),
        description="Task priority",
        default="medium"
    ),
    Field(
        name="budget",
        type=Range(min=0, max=10000),
        description="Budget in USD"
    ),
    Field(
        name="email",
        type=Pattern(r"^[\w\.-]+@[\w\.-]+\.\w+$"),
        description="Contact email"
    )
)
def create_project(priority: str, budget: float, email: str) -> Dict[str, Any]:
    """Create a new project with validated inputs."""
    return {
        "project_id": "proj_123",
        "priority": priority,
        "budget": budget,
        "contact": email,
        "status": "created"
    }


# Example 11: Input groups
@tool
@user_input(
    InputGroup(
        "Personal Information",
        Field(name="first_name", type=str),
        Field(name="last_name", type=str),
        Field(name="age", type=int, required=False)
    ),
    InputGroup(
        "Preferences",
        Field(name="newsletter", type=bool, default=True),
        Field(name="language", type=Choice(["en", "es", "fr"]))
    )
)
def register_user(**kwargs) -> Dict[str, Any]:
    """Register a new user with grouped input fields."""
    return {
        "user_id": "user_123",
        "profile": kwargs,
        "status": "registered"
    }


# Example 12: Integration with existing approval system
try:
    from praisonaiagents.tools.approval import require_approval
    
    @require_approval(risk_level="high")
    @tool(
        before=validate_input,
        after=log_end
    )
    def delete_production_data(table: str) -> Dict[str, Any]:
        """Delete production data with approval and hooks."""
        return {"table": table, "status": "deleted", "rows": 1000}
        
except ImportError:
    # Approval system not available, create simple version
    @tool(
        before=validate_input,
        after=log_end
    )
    def delete_production_data(table: str) -> Dict[str, Any]:
        """Delete production data with hooks (approval not available)."""
        return {"table": table, "status": "deleted", "rows": 1000}


# Example 13: Global hooks setup
def global_logger(context: ToolContext):
    """Global logging for all tools."""
    print(f"🔧 Tool executed: {context.tool_name}")

def global_metrics(context: ToolContext):
    """Global metrics collection."""
    # In a real implementation, this would send to a metrics system
    print(f"📊 Metrics: {context.tool_name} took {context.execution_time:.2f}s")

# Set up global hooks
set_global_hooks(
    before=global_logger,
    after=global_metrics
)


# Example 14: External handler registration
async def gpu_cluster_handler(func, context: ToolContext, external_config):
    """Handle GPU cluster execution."""
    print(f"📡 Submitting {context.tool_name} to GPU cluster...")
    
    # Simulate external execution
    import asyncio
    await asyncio.sleep(1)  # Simulate processing time
    
    # Execute the function normally for this example
    result = func(*context.args, **context.kwargs)
    print(f"🏁 GPU cluster execution completed")
    return result

# Register the external handler
register_external_handler("gpu_cluster", gpu_cluster_handler)


# Example 15: Comprehensive tool with all features
@tool(
    name="comprehensive_analysis",
    description="A comprehensive data analysis tool demonstrating all advanced features",
    before=[(validate_input, Priority.HIGHEST), (log_start, Priority.MEDIUM)],
    after=[log_end, global_metrics],
    cache={"ttl": 600, "tags": ["analysis"], "condition": lambda r: r.get("success", True)},
    external={"executor": "gpu_cluster", "when": lambda data: len(data) > 100},
    inputs=[
        InputGroup(
            "Data Configuration",
            Field(name="dataset", type=str, description="Dataset name"),
            Field(name="algorithm", type=Choice(["linear", "svm", "neural"]), default="linear")
        ),
        InputGroup(
            "Output Options", 
            Field(name="save_results", type=bool, default=True),
            Field(name="output_format", type=Choice(["json", "csv", "xlsx"]), default="json")
        )
    ]
)
def comprehensive_analysis(data: List[float], **config) -> Dict[str, Any]:
    """Demonstrate all advanced tool features in one comprehensive example."""
    return {
        "data_points": len(data),
        "algorithm": config.get("algorithm", "linear"),
        "results": {"accuracy": 0.92, "precision": 0.89},
        "config": config,
        "success": True
    }


if __name__ == "__main__":
    # Example usage demonstrations
    print("🔧 Advanced Tools Examples")
    print("=" * 50)
    
    # Test basic tool with hooks
    print("\n1. Basic tool with hooks:")
    result = calculate_metrics([1, 2, 3, 4, 5])
    print(f"Result: {result}")
    
    # Test caching
    print("\n2. Caching example:")
    print("First call (will be slow):")
    weather1 = fetch_weather("New York")
    print(f"Result: {weather1}")
    
    print("Second call (cached, should be fast):")
    weather2 = fetch_weather("New York")
    print(f"Result: {weather2}")
    
    # Test error handling
    print("\n3. Error handling:")
    try:
        risky_operation(fail=True)
    except Exception as e:
        print(f"Error caught: {e}")
    
    # Test external execution
    print("\n4. External execution:")
    gpu_result = run_on_gpu("/models/test", [1, 2, 3])
    print(f"GPU Result: {gpu_result}")
    
    print("\n✅ All examples completed!")