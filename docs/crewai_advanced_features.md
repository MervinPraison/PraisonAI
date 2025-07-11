# CrewAI Advanced Features in PraisonAI

This document describes the advanced CrewAI features available in PraisonAI. All features are optional and maintain full backward compatibility with existing configurations.

## Table of Contents
- [Process Types](#process-types)
- [Manager LLM Configuration](#manager-llm-configuration)
- [Crew-Level Memory](#crew-level-memory)
- [Planning Features](#planning-features)
- [Verbose Mode Configuration](#verbose-mode-configuration)
- [Output Log Files](#output-log-files)
- [Rate Limiting](#rate-limiting)
- [Custom Embedder](#custom-embedder)
- [Crew Callbacks](#crew-callbacks)
- [Custom Inputs](#custom-inputs)
- [Enhanced Error Handling](#enhanced-error-handling)
- [Usage Metrics](#usage-metrics)

## Process Types

Configure how agents work together:

```yaml
# Sequential process (default)
process_type: sequential

# Hierarchical process with a manager
process_type: hierarchical
```

## Manager LLM Configuration

For hierarchical processes, configure a manager LLM:

```yaml
process_type: hierarchical
manager_llm:
  model: "openai/gpt-4o"
```

## Crew-Level Memory

Enable memory across all agents in the crew:

```yaml
memory: true
```

## Planning Features

Enable planning with optional dedicated planning LLM:

```yaml
planning: true
planning_llm:
  model: "openai/gpt-4o-mini"
```

## Verbose Mode Configuration

Control output verbosity (defaults to true for backward compatibility):

```yaml
verbose: false  # Reduce output
```

## Output Log Files

Save crew execution logs to a file:

```yaml
output_log_file: "crew_execution.log"
```

## Rate Limiting

Control API request rates:

```yaml
max_rpm: 30  # Maximum requests per minute
before_rpm_sleep: 10  # Sleep seconds before hitting limit
```

## Custom Embedder

Configure custom embeddings for semantic operations:

```yaml
embedder:
  provider: "openai"
  model: "text-embedding-ada-002"
```

## Crew Callbacks

Add callbacks for monitoring and logging:

```yaml
crew_callbacks:
  - on_task_start
  - on_task_complete
  - on_agent_action
```

## Custom Inputs

Pass custom inputs to the crew:

```yaml
inputs:
  project_name: "My Project"
  deadline: "2024-12-31"
  priority: "high"
```

## Enhanced Error Handling

The implementation now includes:
- Detailed error logging
- Graceful failure handling
- AgentOps session management
- Exception propagation with context

## Usage Metrics

When available, the system collects and reports:
- Token usage
- API calls made
- Execution time
- Cost estimates

These metrics are appended to the output when available.

## Backward Compatibility

All existing YAML configurations continue to work without modification:

```yaml
# Simple configuration still works
framework: crewai
roles:
  researcher:
    role: "Researcher"
    goal: "Research {topic}"
    backstory: "Expert researcher"
    tasks:
      research:
        description: "Research {topic}"
        expected_output: "Research report"
```

## Example Usage

See `examples/crewai_advanced_example.yaml` for a complete example using all features.