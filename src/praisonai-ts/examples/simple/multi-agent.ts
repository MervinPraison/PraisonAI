import { Agent, PraisonAIAgents } from '../../src/agent/simple';

// Create story agent
const storyAgent = new Agent({
  instructions: "You are a storyteller. Write a very short story (2-3 sentences) about a given topic.",
  name: "StoryAgent",
  verbose: true
});

// Create summary agent
const summaryAgent = new Agent({
  instructions: "You are an editor. Create a one-sentence summary of the given story.",
  name: "SummaryAgent",
  verbose: true
});

// Create and start agents
const agents = new PraisonAIAgents({
  agents: [storyAgent, summaryAgent],
  tasks: [
    "Write a short story about a cat",
    "{previous_result}"  // This will be replaced with the story
  ],
  verbose: true
});

agents.start()
  .then(results => {
    console.log('\nStory:', results[0]);
    console.log('\nSummary:', results[1]);
  })
  .catch(error => console.error('Error:', error));
