import { Agent, PraisonAIAgents } from '../../../src/agent/proxy';

const storyAgent = new Agent({
  instructions: "Generate a very short story (2-3 sentences) about artificial intelligence developing emotions and creativity with emojis.",
  name: "StoryAgent"
});

const summaryAgent = new Agent({
  instructions: "Summarize the provided AI story in one sentence. Do not ask for input - the story will be automatically provided to you with emojis.",
  name: "SummaryAgent"
});

const agents = new PraisonAIAgents({
  agents: [storyAgent, summaryAgent]
});

agents.start()