import { Agent, PraisonAIAgents } from 'praisonai';

async function getWeather(location: string) {
  console.log(`Getting weather for ${location}...`);
  return `${Math.floor(Math.random() * 30)}°C`;
}

async function getTime(location: string) {
  console.log(`Getting time for ${location}...`);
  const now = new Date();
  return `${now.getHours()}:${now.getMinutes()}`;
}

// Create recipe agent
const recipeAgent = new Agent({
  instructions: `You are a Weather Agent`,
  name: "WeatherAgent",
  verbose: true,
  tools: [getWeather]
});

// Create blog agent
const blogAgent = new Agent({
  instructions: `You are a Time Agent`,
  name: "TimeAgent",
  verbose: true,
  tools: [getTime]
});

// Create PraisonAIAgents instance with tasks
const agents = new PraisonAIAgents({
  agents: [recipeAgent, blogAgent],
  tasks: [
    "Get the weather and express it in 5 lines with emojis",
    "Get the time and express it in 5 lines with emojis"
  ],
  verbose: true
});

// Start the agents
agents.start()
  .then(results => {
    console.log('\nFinal Results:');
    console.log('\nWeather Task Results:');
    console.log(results[0]);
    console.log('\nTime Task Results:');
    console.log(results[1]);
  })
  .catch(error => {
    console.error('Error:', error);
  });
