# Domain Context Solution

This example demonstrates how to solve domain context issues in multi-agent systems using existing PraisonAI features.

## Problem

In hierarchical multi-agent workflows, tools often default to generic values like "example.com" instead of using user-specified domains. This happens because domain context doesn't automatically reach the tool execution level.

## Solution: 4-Layer Context Approach

This solution uses four existing PraisonAI features to ensure domain context is properly maintained:

### 1. **Custom Tool Wrappers**
```python
def create_domain_aware_tools(target_domain: str):
    def query_fofa(query: str = None) -> dict:
        if query is None or query == "example.com":
            query = target_domain
        # Tool implementation with domain injection
```

### 2. **Agent Instructions**
```python
agent = Agent(
    instructions=f"""
    CRITICAL DOMAIN CONTEXT: You are working exclusively with the domain '{domain}'. 
    All operations, tool calls, and analysis must focus on this specific domain.
    Never use example.com or generic examples - always use {domain}.
    """,
    tools=domain_tools
)
```

### 3. **Task Context Parameter**
```python
task = Task(
    description=f"Analyze domain {domain}",
    context=[domain_context.get_context()],  # Pass domain context
    agent=agent
)
```

### 4. **Shared Memory**
```python
agents = PraisonAIAgents(
    agents=[agent1, agent2],
    tasks=[task1, task2],
    memory=True,  # Enable shared memory for context
    memory_config={
        "provider": "rag",
        "config": {"collection_name": f"{domain}_analysis"}
    }
)
```

## Usage

```python
from domain_context_solution import main

# Set your target domain
domain = "your-domain.com"

# Run the hierarchical workflow
main()
```

## Key Benefits

- ✅ **No Core SDK Changes** - Uses only existing framework features
- ✅ **Multi-Layer Reliability** - Context maintained through multiple mechanisms
- ✅ **Domain-Specific Results** - Tools focus on specified domain
- ✅ **Backward Compatible** - Doesn't break existing functionality
- ✅ **Scalable Pattern** - Works for any domain or context type

## Files

- `domain-context-solution.py` - Complete working solution
- `README-domain-context.md` - This documentation

This pattern can be adapted for any context passing scenario in PraisonAI multi-agent systems.