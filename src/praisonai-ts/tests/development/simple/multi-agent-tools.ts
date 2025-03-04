import { Agent, PraisonAIAgents } from '../../../src/agent/simple';

async function getWeather(location: string) {
  console.log(`Getting weather for ${location}...`);
  return `${Math.floor(Math.random() * 30)}°C`;
}

async function getTime(location: string) {
  console.log(`Getting time for ${location}...`);
  const now = new Date();
  return `${now.getHours()}:${now.getMinutes()}`;
}

const weatherAgent = new Agent({
  instructions: "You are a Weather Agent",
  name: "WeatherAgent",
  tools: [getWeather]
});

const timeAgent = new Agent({
  instructions: "You are a Time Agent",
  name: "TimeAgent",
  tools: [getTime]
});

const agents = new PraisonAIAgents({
  agents: [weatherAgent, timeAgent],
  tasks: [
    "Get the weather of London and express it in 5 lines with emojis",
    "Get the time and express it in 5 lines with emojis"
  ]
});

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