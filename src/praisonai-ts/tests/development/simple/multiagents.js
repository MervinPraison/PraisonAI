const { Agent, PraisonAIAgents } = require('praisonai');

// Create agents with clear instructions that can be used as tasks
const researchAgent = new Agent({ 
    instructions: 'Research about artificial intelligence and its impact on society. Focus on current trends and future predictions.',
    name: 'Researcher',
    verbose: true,
    pretty: true
});

const summarizeAgent = new Agent({ 
    instructions: 'Create a concise summary of the research findings. Highlight key points and potential implications.',
    name: 'Summarizer',
    verbose: true,
    pretty: true
});

// Create multi-agent system - tasks will be auto-generated from instructions
const agents = new PraisonAIAgents({ 
    agents: [researchAgent, summarizeAgent],
    process: 'sequential',  // Run agents one after another
    verbose: true,
    pretty: true
});

// Start the agents - they will use auto-generated tasks from instructions
agents.start()
    .then(results => {
        console.log('\nFinal Results:');
        results.forEach((result, i) => {
            console.log(`\nAgent ${i + 1} Result:`);
            console.log(result);
        });
    })
    .catch(error => {
        console.error('Error:', error);
    });
