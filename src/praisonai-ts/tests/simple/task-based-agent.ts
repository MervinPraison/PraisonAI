import { Agent, PraisonAIAgents } from '../../src/agent/simple';

// Create recipe agent
const recipeAgent = new Agent({
  instructions: `You are a professional chef and nutritionist. Create 1 healthy food recipes that are both nutritious and delicious.`,
  name: "RecipeAgent",
  verbose: true
});

// Create blog agent
const blogAgent = new Agent({
  instructions: `You are a food and health blogger. Write an engaging blog post about the provided recipes`,
  name: "BlogAgent",
  verbose: true
});

// Create PraisonAIAgents instance with tasks
const agents = new PraisonAIAgents({
  agents: [recipeAgent, blogAgent],
  tasks: [
    "Create 1 healthy and delicious recipes in 5 lines with emojis",
    "Write a blog post about the recipes in 5 lines with emojis"
  ],
  verbose: true
});

// Start the agents
agents.start()
  .then(results => {
    console.log('\nFinal Results:');
    console.log('\nRecipe Task Results:');
    console.log(results[0]);
    console.log('\nBlog Task Results:');
    console.log(results[1]);
  })
  .catch(error => {
    console.error('Error:', error);
  });
