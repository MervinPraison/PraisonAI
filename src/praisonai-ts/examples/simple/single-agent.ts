import { Agent } from 'praisonai';

// Single agent example - Science Explainer
const agent = new Agent({ 
  instructions: `You are a science expert who explains complex phenomena in simple terms.
Provide clear, accurate, and easy-to-understand explanations.`,
  name: "ScienceExplainer",
  verbose: true
});

agent.start("Why is the sky blue?")
  .then(response => {
    console.log('\nExplanation:');
    console.log(response);
  })
  .catch(error => {
    console.error('Error:', error);
  });
