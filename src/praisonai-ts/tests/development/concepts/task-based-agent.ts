import { Agent, Task, PraisonAIAgents } from '../../src/agent';

async function main() {
    // Create agents first
    const dietAgent = new Agent({
        name: "DietAgent",
        role: "Nutrition Expert",
        goal: "Create healthy and delicious recipes",
        backstory: "You are a certified nutritionist with years of experience in creating balanced meal plans.",
        verbose: true,  // Enable streaming output
        instructions: `You are a professional chef and nutritionist. Create 5 healthy food recipes that are both nutritious and delicious.
Each recipe should include:
1. Recipe name
2. List of ingredients with quantities
3. Step-by-step cooking instructions
4. Nutritional information
5. Health benefits

Format your response in markdown.`
    });

    const blogAgent = new Agent({
        name: "BlogAgent",
        role: "Food Blogger",
        goal: "Write engaging blog posts about food and recipes",
        backstory: "You are a successful food blogger known for your ability to make recipes sound delicious and approachable.",
        verbose: true,  // Enable streaming output
        instructions: `You are a food and health blogger. Write an engaging blog post about the provided recipes.
The blog post should:
1. Have an engaging title
2. Include an introduction about healthy eating
3. Discuss each recipe and its unique health benefits
4. Include tips for meal planning and preparation
5. End with a conclusion encouraging healthy eating habits

Use the following recipes as input:
{recipes}

Format your response in markdown.`
    });

    // Then create tasks and assign agents to them
    const recipeTask = new Task({
        name: "Create Recipes",
        description: "Create 5 healthy food recipes that are both nutritious and delicious",
        expected_output: "A list of 5 detailed recipes with ingredients and instructions",
        agent: dietAgent
    });

    const blogTask = new Task({
        name: "Write Blog Post",
        description: "Write an engaging blog post about the provided recipes",
        expected_output: "A well-structured blog post discussing the recipes and their health benefits",
        dependencies: [recipeTask],
        agent: blogAgent
    });

    // Run the tasks
    const praisonAI = new PraisonAIAgents({
        agents: [dietAgent, blogAgent],
        tasks: [recipeTask, blogTask],
        verbose: true,
        process: 'hierarchical'
    });

    try {
        console.log('Starting task-based agent example...');
        const results = await praisonAI.start();
        console.log('\nFinal Results:');
        console.log('Recipe Task Results:', results[0]);
        console.log('\nBlog Task Results:', results[1]);
    } catch (error) {
        console.error('Error:', error);
    }
}

// Run the example
if (require.main === module) {
    main();
}
