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

// Run the example
if (require.main === module) {
    main();
}
