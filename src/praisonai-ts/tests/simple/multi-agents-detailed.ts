import { Agent, PraisonAIAgents } from '../../src/agent/simple';

// Create research agent
const researchAgent = new Agent({ 
    instructions: `You are an AI research expert. Conduct comprehensive research about artificial intelligence`,
    name: "ResearchAgent",
    verbose: true,
    pretty: true
});

// Create summarize agent
const summarizeAgent = new Agent({ 
    instructions: `You are a professional technical writer. Create a concise executive summary of the research findings about AI`,
    name: "SummarizeAgent",
    verbose: true,
    pretty: true
});

// Create PraisonAIAgents instance
const agents = new PraisonAIAgents({ 
    agents: [researchAgent, summarizeAgent],
    tasks: ["Research current state and future of AI with emojis", "Create executive summary with emojis"],
    process: 'sequential',  // Run agents one after another
    verbose: true,
    pretty: true
});

// Start the agents
agents.start()
    .then(results => {
        console.log('\nFinal Results:');
        results.forEach((result, index) => {
            console.log(`\nAgent ${index + 1} Result:`);
            console.log(result);
        });
    })
    .catch(error => {
        console.error('Error:', error);
    });
