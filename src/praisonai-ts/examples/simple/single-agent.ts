import { Agent } from 'praisonai';

const agent = new Agent({ 
  instructions: `You are a creative writer who writes short stories with emojis.`,
  name: "StoryWriter"
});

agent.start("Write a story about a time traveler")