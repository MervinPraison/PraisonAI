# CrewAI Advanced Features in PraisonAI

This document describes the enhanced CrewAI features now available in PraisonAI.

## New Features Added

### 1. Process Types
You can now specify different process types for crew execution:
- `sequential` (default): Tasks are executed one after another
- `hierarchical`: A manager agent coordinates task execution

```yaml
framework: "crewai"
process: "hierarchical"  # or "sequential"
```

### 2. Manager LLM Configuration
For hierarchical processes, you can specify a dedicated LLM for the manager:

```yaml
manager_llm:
  model: "openai/gpt-4o"
```

### 3. Memory Support
Enable memory/caching at the crew level:

```yaml
memory: true
```

### 4. Planning Features
Enable planning mode with optional planning LLM:

```yaml
planning: true
planning_llm:
  model: "openai/gpt-4o"
```

### 5. Verbose Control
Control verbosity at the crew level:

```yaml
verbose: false  # or true
```

### 6. Output Logging
Save crew execution logs to a file:

```yaml
output_log_file: "crew_execution.log"
```

### 7. Rate Limiting
Configure rate limiting for API calls:

```yaml
max_rpm: 60  # Maximum requests per minute
before_rpm_sleep: 1  # Sleep time in seconds before hitting rate limit
```

### 8. Embedder Configuration
Configure embeddings for semantic search (if needed):

```yaml
embedder:
  model: "text-embedding-ada-002"
```

### 9. Custom Inputs
Provide custom inputs to the crew:

```yaml
inputs:
  topic: "AI Research"
  industry: "Healthcare"
  budget: "$100,000"
```

### 10. Crew Sharing
Enable or disable crew sharing:

```yaml
share_crew: false
```

### 11. Enhanced Error Handling
Better error handling and logging during crew execution.

### 12. Usage Metrics
Automatic tracking and reporting of LLM usage metrics (when available).

## Backward Compatibility

All existing CrewAI configurations will continue to work as before. The new features are optional and only activate when explicitly configured.

## Example Configuration

See `/examples/crewai_advanced_example.yaml` for a complete example demonstrating all new features.

## Migration Guide

To use the new features:

1. Update your YAML configuration to include desired features
2. No code changes required - just configuration
3. All features are optional and backward compatible

### Before (Basic Configuration):
```yaml
framework: "crewai"
topic: "My Topic"
roles:
  researcher:
    role: "Researcher"
    goal: "Research the topic"
    backstory: "Expert researcher"
    tasks:
      research:
        description: "Research the topic"
        expected_output: "Research report"
```

### After (With Advanced Features):
```yaml
framework: "crewai"
topic: "My Topic"
process: "hierarchical"
memory: true
verbose: true
planning: true
output_log_file: "execution.log"

manager_llm:
  model: "openai/gpt-4o"

planning_llm:
  model: "openai/gpt-4o"

inputs:
  topic: "Advanced Topic"
  
roles:
  researcher:
    role: "Researcher"
    goal: "Research the topic"
    backstory: "Expert researcher"
    tasks:
      research:
        description: "Research the topic"
        expected_output: "Research report"
        output_file: "research.md"
        human_input: true
```

## Notes

- Some features may require specific CrewAI versions
- Memory feature may increase token usage
- Hierarchical process requires a manager LLM configuration
- Planning features are experimental and may affect performance