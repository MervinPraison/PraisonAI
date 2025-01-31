const { Agent, PraisonAIAgents } = require('praisonai');

const researchAgent = new Agent({ instructions: 'Research about AI' });
const summariseAgent = new Agent({ instructions: 'Summarise research agent\'s findings' });

const agents = new PraisonAIAgents({ agents: [researchAgent, summariseAgent] });
agents.start();
