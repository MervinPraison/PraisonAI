import { Agent, PraisonAIAgents } from 'praisonai';

// Create two independent agents
const weatherAgent = new Agent({
  instructions: `You are a weather expert. Describe the typical weather in the given city.`,
  name: "WeatherAgent",
  verbose: true
});

const foodAgent = new Agent({
  instructions: `You are a food expert. Describe the local cuisine in the given city.`,
  name: "FoodAgent",
  verbose: true
});

// Create PraisonAIAgents instance with parallel processing
const agents = new PraisonAIAgents({
  agents: [weatherAgent, foodAgent],
  tasks: ["What is the weather like in Paris?", "What are some famous dishes in Paris?"],
  verbose: true,
  process: 'parallel'
});

// Chat with agents in parallel
agents.chat()
  .then(results => {
    console.log('\nFinal Results:');
    console.log('\nWeather Information:');
    console.log(results[0]);
    console.log('\nFood Information:');
    console.log(results[1]);
  })
  .catch(error => {
    console.error('Error:', error);
  });
