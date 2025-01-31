const { Agent } = require('praisonai');

// Create a simple science explainer agent
const agent = new Agent({
  instructions: "You are a science expert who explains complex phenomena in simple terms.",
  name: "ScienceExplainer",
  verbose: true
});

// Ask a question
agent.start("Why is the sky blue?")
  .then(response => {
    console.log('\nExplanation:');
    console.log(response);
  })
  .catch(error => console.error('Error:', error));
