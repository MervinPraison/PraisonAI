import { Agent, PraisonAIAgents } from 'praisonai';

// Create recipe agent
const recipeAgent = new Agent({
  instructions: `You are a professional chef and nutritionist. Create 5 healthy food recipes that are both nutritious and delicious.
Each recipe should include:
1. Recipe name
2. List of ingredients with quantities
3. Step-by-step cooking instructions
4. Nutritional information
5. Health benefits

Format your response in markdown.`,
  name: "RecipeAgent",
  verbose: true
});

// Create blog agent
const blogAgent = new Agent({
  instructions: `You are a food and health blogger. Write an engaging blog post about the provided recipes.
The blog post should:
1. Have an engaging title
2. Include an introduction about healthy eating
3. Discuss each recipe and its unique health benefits
4. Include tips for meal planning and preparation
5. End with a conclusion encouraging healthy eating habits

Here are the recipes to write about:
{previous_result}

Format your response in markdown.`,
  name: "BlogAgent",
  verbose: true
});

// Create PraisonAIAgents instance with tasks
const agents = new PraisonAIAgents({
  agents: [recipeAgent, blogAgent],
  tasks: [
    "Create 5 healthy and delicious recipes",
    "Write a blog post about the recipes"
  ],
  verbose: true
});

// Chat with agents
agents.chat()
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
