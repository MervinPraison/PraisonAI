import { Agent, PraisonAIAgents } from 'praisonai';

const recipeAgent = new Agent({
  instructions: `You are a professional chef and nutritionist. Create 1 healthy food recipes that are both nutritious and delicious.`,
  name: "RecipeAgent"
});

const blogAgent = new Agent({
  instructions: `You are a food and health blogger. Write an engaging blog post about the provided recipes`,
  name: "BlogAgent"
});

const agents = new PraisonAIAgents({
  agents: [recipeAgent, blogAgent],
  tasks: [
    "Create 1 healthy and delicious recipes in 5 lines with emojis",
    "Write a blog post about the recipes in 5 lines with emojis"
  ]
});

agents.start()