import { Agent } from '../../src/agent/proxy';

// Single agent example - Short Story Writer
const agent = new Agent({ 
  instructions: `You are a creative writer who writes short stories.
Keep stories brief (max 100 words) and engaging.`,
  name: "StoryWriter",
  verbose: true,
  pretty: true,  // Enable pretty logging
  stream: true   // Enable streaming output
});

// Write a very short story
agent.start("Write a 100-word story about a time traveler")
  .catch(error => {
    console.error('Error:', error);
  });
