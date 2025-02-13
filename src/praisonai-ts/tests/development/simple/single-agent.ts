import { Agent } from '../../../src/agent/proxy';

const agent = new Agent({ 
  instructions: `You are a creative writer who writes short stories.
Keep stories brief (max 50 words) and engaging with emojis.`,
  name: "StoryWriter"
});

agent.start("Write a story about a time traveler")