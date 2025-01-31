import { Agent } from 'praisonai';

// Single agent example - Movie Script Writer
const agent = new Agent({ 
  instructions: `You are a professional screenwriter specializing in science fiction scripts.
Write compelling movie scripts that include:
1. Scene descriptions
2. Character dialogue
3. Emotional moments
4. Scientific accuracy
5. Proper screenplay format`,
  name: "ScriptWriter",
  verbose: true
});

agent.chat("Write a movie script about a robot stranded on Mars")
  .then(response => {
    console.log('\nMovie Script:');
    console.log(response);
  })
  .catch(error => {
    console.error('Error:', error);
  });
