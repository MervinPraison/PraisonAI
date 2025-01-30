# PraisonAI Concept Examples

This directory contains examples demonstrating core concepts of the PraisonAI package.

## Getting Started

1. Install the package:
```bash
npm install praisonai
```

2. Run any example using ts-node:
```bash
# Run single agent example
npx ts-node examples/concepts/single-agent.ts

# Run multi-agent example
npx ts-node examples/concepts/multi-agent.ts

# Run task-based agent example
npx ts-node examples/concepts/task-based-agent.ts
```

> **Note**: These examples assume you have installed the `praisonai` package from npm. If you're running these examples from within the package source code, the imports will automatically use the local package code.

## Examples

### Single Agent (`single-agent.ts`)
A simple example showing how to use a single agent to perform a task.

### Multi Agent (`multi-agent.ts`)
Demonstrates how to use multiple agents working together in sequence.

### Task Based Agent (`task-based-agent.ts`)
Shows how to create and execute dependent tasks using multiple agents.

## Usage in Your Code

You can use these concepts in your own code:

```typescript
import { Agent, Task, PraisonAIAgents } from 'praisonai';

// Create an agent
const agent = new Agent({
    name: "MyAgent",
    role: "Custom Role",
    goal: "Achieve something specific",
    backstory: "Relevant background",
    verbose: true
});

// Create a task
const task = new Task({
    name: "my_task",
    description: "Do something specific",
    expected_output: "Expected result",
    agent: agent
});

// Run the agent
const system = new PraisonAIAgents({
    agents: [agent],
    tasks: [task],
    verbose: true
});

const result = await system.start();
```

## Key Features

1. **Agent Configuration**
   - Name, role, and goal definition
   - Backstory for context
   - Verbose mode for debugging
   - LLM model selection
   - Markdown output option

2. **Task Management**
   - Task dependencies
   - Expected output specification
   - Agent assignment

3. **Execution Modes**
   - Sequential (default)
   - Parallel
   - Hierarchical with manager LLM

4. **Process Control**
   - Verbose logging
   - Error handling
   - Dependency resolution
