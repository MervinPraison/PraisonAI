# Stateful Agents Examples

This directory contains comprehensive examples demonstrating PraisonAI's stateful agents capabilities, including session management, memory systems, and persistent workflows.

## Examples Overview

### 1. Session Management (`session-example.py`)

Demonstrates the `Session` class for managing stateful agent interactions:

- **Session Creation**: Persistent session with unique IDs
- **Agent Context**: Creating agents within session scope
- **State Management**: Saving and restoring session state
- **Memory Integration**: Adding and retrieving session-specific memories
- **Context Building**: Generating context from session history

**Key Features Shown:**
```python
session = Session(session_id="demo_chat_001", user_id="demo_user")
agent = session.create_agent("Assistant", memory=True)
session.save_state({"conversation_style": "brief_technical"})
```

### 2. Workflow State Management (`workflow-state-example.py`)

Shows advanced state management in multi-agent workflows:

- **Multi-Agent Workflows**: Coordinated agents with shared state
- **Conditional Execution**: Tasks that depend on workflow state
- **State Persistence**: Saving and restoring complete workflow state
- **Progress Tracking**: Monitoring workflow progress with counters
- **Cross-Task Communication**: State sharing between tasks

**Key Features Shown:**
```python
workflow = PraisonAIAgents(agents=[...], memory=True, process="workflow")
workflow.set_state("research_topic", "AI safety")
workflow.increment_state("tasks_completed", 1)
workflow.save_session_state("research_session")
```

### 3. Memory Quality Management (`memory-quality-example.py`)

Demonstrates advanced memory management with quality scoring:

- **Quality-Based Storage**: Storing information with quality metrics
- **Quality Filtering**: Retrieving memories above quality thresholds
- **Multi-Tiered Memory**: Short-term and long-term memory strategies
- **Context Building**: Quality-aware context generation
- **Memory Statistics**: Analyzing memory quality distribution

**Key Features Shown:**
```python
memory.store_long_term(
    text="AI safety research findings...",
    completeness=0.95, relevance=0.90, clarity=0.88, accuracy=0.92
)
high_quality = memory.search_long_term(query="AI safety", min_quality=0.8)
```

## Running the Examples

### Prerequisites

1. Install PraisonAI with memory support:
```bash
pip install "praisonaiagents[memory]"
```

2. Set up your OpenAI API key:
```bash
export OPENAI_API_KEY="your-api-key-here"
```

### Running Individual Examples

```bash
# Session management example
python examples/python/stateful/session-example.py

# Workflow state management example  
python examples/python/stateful/workflow-state-example.py

# Memory quality management example
python examples/python/stateful/memory-quality-example.py
```

## Key Concepts Demonstrated

### Session Management
- **Persistent Sessions**: Sessions that survive application restarts
- **User Context**: User-specific memory and preferences
- **State Restoration**: Recovering session state after interruptions
- **Memory Integration**: Session-aware memory storage and retrieval

### Workflow State
- **Shared State**: State accessible across all agents and tasks
- **Conditional Logic**: Decisions based on current workflow state
- **Progress Tracking**: Monitoring workflow completion status
- **Error Recovery**: Graceful handling of failed tasks

### Memory Quality
- **Quality Metrics**: Completeness, relevance, clarity, accuracy scores
- **Automatic Filtering**: Retrieving only high-quality memories
- **Tiered Storage**: Short-term vs long-term memory strategies
- **Context Optimization**: Building context from best available memories

## Integration Patterns

### With Existing PraisonAI Features

1. **Multi-Agent Systems**: Each example works with multiple agents
2. **Tool Integration**: Tools can access and modify workflow state
3. **Process Types**: Compatible with sequential, hierarchical, and workflow processes
4. **Knowledge Bases**: Memory systems integrate with knowledge processing

### With External Systems

1. **API Integration**: Stateful agents in web applications
2. **Database Persistence**: Memory backends support various databases
3. **Monitoring**: State and memory metrics for observability
4. **UI Components**: Stateful behavior in user interfaces

## Best Practices Shown

### Session Design
- Use meaningful session IDs for debugging and restoration
- Include user context for multi-user applications
- Save state at logical workflow milestones
- Implement graceful degradation when state is unavailable

### Memory Strategy
- Set quality thresholds based on application requirements
- Use appropriate memory types (short-term vs long-term)
- Implement memory cleanup for long-running applications
- Build context efficiently using quality filters

### State Management
- Keep state keys descriptive and consistent
- Use typed data structures for complex state
- Implement state validation for critical workflows
- Provide sensible defaults for missing state values

## Advanced Usage

### Custom Memory Providers
Examples show configuration for different memory backends:
- **RAG Provider**: ChromaDB with embeddings
- **Mem0 Provider**: Advanced memory with graph support
- **Local Provider**: SQLite for simple use cases

### Quality Scoring
Examples demonstrate custom quality calculation:
- **Weighted Metrics**: Custom weights for different quality aspects
- **External Evaluators**: Using LLMs to assess quality
- **Domain-Specific**: Quality criteria tailored to specific domains

### State Persistence
Examples show different persistence strategies:
- **Session-Based**: State tied to user sessions
- **Workflow-Based**: State tied to specific workflows
- **User-Based**: State tied to individual users
- **Global**: Application-wide state management

## Troubleshooting

### Common Issues

1. **Memory Dependencies**: Ensure memory dependencies are installed
2. **API Keys**: Verify OpenAI API key is set correctly
3. **File Permissions**: Check write permissions for memory storage
4. **State Conflicts**: Handle state key collisions in complex workflows

### Debug Mode

Run examples with verbose output:
```python
memory = Memory(config=memory_config, verbose=5)
workflow = PraisonAIAgents(..., verbose=1)
```

### Performance Optimization

- Use quality filters to reduce memory search space
- Implement memory cleanup for long-running applications
- Cache frequently accessed state values
- Use appropriate memory providers for your scale

These examples provide a comprehensive foundation for building sophisticated stateful agent applications with PraisonAI.