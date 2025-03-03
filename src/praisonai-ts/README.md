# PraisonAI TypeScript Node.js AI Agents Framework

PraisonAI is a production-ready Multi AI Agents framework, designed to create AI Agents to automate and solve problems ranging from simple tasks to complex challenges. It provides a low-code solution to streamline the building and management of multi-agent LLM systems, emphasising simplicity, customisation, and effective human-agent collaboration.

## Installation

```bash
npm install praisonai
```

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/MervinPraison/PraisonAI.git
cd src/praisonai-ts
```

2. Install dependencies:
```bash
npm install
```

3. Build the package:
```bash
npm run build
```

## Usage

Here are examples of different ways to use PraisonAI:

### 1. Single Agent Example

```typescript
import { Agent, PraisonAIAgents } from 'praisonai';

async function main() {
    // Create a simple agent (no task specified)
    const agent = new Agent({
        name: "BiologyExpert",
        instructions: "Explain the process of photosynthesis in detail.",
        verbose: true
    });

    // Run the agent
    const praisonAI = new PraisonAIAgents({
        agents: [agent],
        tasks: ["Explain the process of photosynthesis in detail."],
        verbose: true
    });

    try {
        console.log('Starting single agent example...');
        const results = await praisonAI.start();
        console.log('\nFinal Results:', results);
    } catch (error) {
        console.error('Error:', error);
    }
}

main();
```

### 2. Multi-Agent Example

```typescript
import { Agent, PraisonAIAgents } from 'praisonai';

async function main() {
    // Create multiple agents with different roles
    const researchAgent = new Agent({
        name: "ResearchAgent",
        instructions: "Research and provide detailed information about renewable energy sources.",
        verbose: true
    });

    const summaryAgent = new Agent({
        name: "SummaryAgent",
        instructions: "Create a concise summary of the research findings about renewable energy sources. Use {previous_result} as input.",
        verbose: true
    });

    const recommendationAgent = new Agent({
        name: "RecommendationAgent",
        instructions: "Based on the summary in {previous_result}, provide specific recommendations for implementing renewable energy solutions.",
        verbose: true
    });

    // Run the agents in sequence
    const praisonAI = new PraisonAIAgents({
        agents: [researchAgent, summaryAgent, recommendationAgent],
        tasks: [
            "Research and analyze current renewable energy technologies and their implementation.",
            "Summarize the key findings from the research.",
            "Provide actionable recommendations based on the summary."
        ],
        verbose: true
    });

    try {
        console.log('Starting multi-agent example...');
        const results = await praisonAI.start();
        console.log('\nFinal Results:', results);
    } catch (error) {
        console.error('Error:', error);
    }
}

main();
```

### 3. Task-Based Agent Example

```typescript
import { Agent, Task, PraisonAIAgents } from 'praisonai';

async function main() {
    // Create agents first
    const dietAgent = new Agent({
        name: "DietAgent",
        role: "Nutrition Expert",
        goal: "Create healthy and delicious recipes",
        backstory: "You are a certified nutritionist with years of experience in creating balanced meal plans.",
        verbose: true,  // Enable streaming output
        instructions: `You are a professional chef and nutritionist. Create 5 healthy food recipes that are both nutritious and delicious.
Each recipe should include:
1. Recipe name
2. List of ingredients with quantities
3. Step-by-step cooking instructions
4. Nutritional information
5. Health benefits

Format your response in markdown.`
    });

    const blogAgent = new Agent({
        name: "BlogAgent",
        role: "Food Blogger",
        goal: "Write engaging blog posts about food and recipes",
        backstory: "You are a successful food blogger known for your ability to make recipes sound delicious and approachable.",
        verbose: true,  // Enable streaming output
        instructions: `You are a food and health blogger. Write an engaging blog post about the provided recipes.
The blog post should:
1. Have an engaging title
2. Include an introduction about healthy eating`
    });

    // Create tasks
    const createRecipesTask = new Task({
        name: "Create Recipes",
        description: "Create 5 healthy and delicious recipes",
        agent: dietAgent
    });

    const writeBlogTask = new Task({
        name: "Write Blog",
        description: "Write a blog post about the recipes",
        agent: blogAgent,
        dependencies: [createRecipesTask]  // This task depends on the recipes being created first
    });

    // Run the tasks
    const praisonAI = new PraisonAIAgents({
        tasks: [createRecipesTask, writeBlogTask],
        verbose: true
    });

    try {
        console.log('Starting task-based example...');
        const results = await praisonAI.start();
        console.log('\nFinal Results:', results);
    } catch (error) {
        console.error('Error:', error);
    }
}

main();
```

### Running the Examples

1. First, set up your environment variables:
```bash
export OPENAI_API_KEY='your-api-key'
```

2. Create a new TypeScript file (e.g., `example.ts`) with any of the above examples.

3. Run the example:
```bash
npx ts-node example.ts
```

For more examples, check out the `examples/concepts/` directory in the repository.

## Package Structure

```
src/
├── agent/         # Agent-related interfaces and implementations
├── agents/        # Multi-agent system management
├── knowledge/     # Knowledge base and management
├── llm/          # Language Model interfaces
├── memory/       # Memory management systems
├── process/      # Process management
├── task/         # Task management
└── tools/        # Various utility tools
    ├── arxivTools.ts
    └── ... (other tools)
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License - see the LICENSE file for details

## Testing

### Manual Testing

```bash
export OPENAI_API_KEY='your-api-key'
npx ts-node tests/development/simple/single-agent.ts
npx ts-node tests/development/simple/multi-agent.ts
npx ts-node tests/development/simple/multi-agents-simple.js
```

## Examples Testing

```bash
export OPENAI_API_KEY='your-api-key'
npx ts-node examples/simple/single-agent.ts
npx ts-node examples/simple/multi-agent.ts
```

### Automated Testing (WIP)

```bash
npm run test
```

