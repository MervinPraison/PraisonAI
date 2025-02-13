const { Agent } = require('praisonai');

// Create a simple math tutor agent
const agent = new Agent({ 
  instructions: `You are a friendly math tutor. Help students solve basic math problems.
Keep explanations simple and clear.`,
  name: "MathTutor",
  verbose: true
});

// Ask the agent to solve a math problem
agent.start("What is 15% of 80?")
  .then(response => {
    console.log('\nMath Solution:');
    console.log(response);
  })
  .catch(error => {
    console.error('Error:', error);
  });
