const { Agent } = require('praisonai');

const agent = new Agent({ instructions: 'You are a helpful AI assistant' });

agent.start('Write a movie script about a robot on Mars')
  .then(response => {
    console.log(response);
  })
  .catch(error => {
    console.error('Error:', error);
  });
