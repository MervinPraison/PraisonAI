import { Agent, PraisonAIAgents } from 'praisonai';

const storyAgent = new Agent({
  instructions: "Generate a very short story (2-3 sentences) about artificial intelligence with emojis.",
  name: "StoryAgent"
});

const summaryAgent = new Agent({
  instructions: "Summarize the provided AI story in one sentence with emojis.",
  name: "SummaryAgent"
});

const agents = new PraisonAIAgents({
  agents: [storyAgent, summaryAgent]
});

agents.start()