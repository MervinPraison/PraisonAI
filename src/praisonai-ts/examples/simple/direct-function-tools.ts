import { Agent } from 'praisonai';

async function getWeather(location: string) {
  console.log(`Getting weather for ${location}...`);
  return `${Math.floor(Math.random() * 30)}°C`;
}

async function getTime(location: string) {
  console.log(`Getting time for ${location}...`);
  const now = new Date();
  return `${now.getHours()}:${now.getMinutes()}`;
}

const agent = new Agent({ 
  instructions: `You provide the current weather and time for requested locations.`,
  name: "DirectFunctionAgent",
  tools: [getWeather, getTime]
});

agent.start("What's the weather and time in Paris, France and Tokyo, Japan?");