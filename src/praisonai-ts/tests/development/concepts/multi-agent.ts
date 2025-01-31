import { Agent, PraisonAIAgents } from '../../src/agent';

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
        verbose: true,
        process: 'sequential'  // Agents will run in sequence, passing results to each other
    });

    try {
        console.log('Starting multi-agent example...');
        const results = await praisonAI.start();
        console.log('\nFinal Results:');
        console.log('Research Results:', results[0]);
        console.log('\nSummary Results:', results[1]);
        console.log('\nRecommendation Results:', results[2]);
    } catch (error) {
        console.error('Error:', error);
    }
}

// Run the example
if (require.main === module) {
    main();
}
