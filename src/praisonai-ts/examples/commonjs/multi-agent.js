const { PraisonAIAgents, Agent } = require('praisonai');

// Create a story agent and a summary agent
const storyAgent = new Agent({
  instructions: "You are a creative storyteller. Create engaging stories.",
  name: "Storyteller"
});

const summaryAgent = new Agent({
  instructions: "You summarize stories into brief, engaging summaries.",
  name: "Summarizer"
});

// Create multi-agent system
const agents = new PraisonAIAgents({
  agents: [storyAgent, summaryAgent],
  tasks: [
    "Create a short story about a magical forest",
    "Summarize the story in 2 sentences"
  ]
});

// Run the agents
agents.start()
  .then(responses => {
    console.log('\nStory:');
    console.log(responses[0]);
    console.log('\nSummary:');
    console.log(responses[1]);
  })
  .catch(error => console.error('Error:', error));
