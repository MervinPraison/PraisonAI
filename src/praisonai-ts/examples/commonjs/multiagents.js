const { Agent, PraisonAIAgents } = require('praisonai');

// Create agents with specific roles
const researchAgent = new Agent({
  instructions: 'You are a research agent. Provide factual and concise information about the given topic.',
  name: 'Researcher'
});

const summarizeAgent = new Agent({
  instructions: 'You are a summarizer. Create brief, clear summaries of the information provided.',
  name: 'Summarizer'
});

// Define tasks for each agent
const tasks = [
  "What are the latest developments in AI in 2024?",  // For research agent
  "{{previous}}"  // For summarize agent - uses output from research agent
];

// Create multi-agent system
const agents = new PraisonAIAgents({
  agents: [researchAgent, summarizeAgent],
  tasks: tasks,
  process: 'sequential'  // Run agents one after another
});

// Start the agents and handle the results
agents.start()
  .then(results => {
    console.log('\nResults:');
    console.log('Research:', results[0]);
    console.log('\nSummary:', results[1]);
  })
  .catch(error => {
    console.error('Error:', error);
  });
