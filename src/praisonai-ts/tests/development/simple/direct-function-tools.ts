import { Agent } from '../../../src/agent/proxy';

/**
 * Example of a simple agent with direct function registration
 * 
 * This example demonstrates how to create a simple agent that uses directly
 * registered functions as tools without having to define tool schemas manually
 * or make functions globally available.
 */

// Define the functions directly
async function getWeather(location: string) {
  console.log(`Getting weather for ${location}...`);
  return `${Math.floor(Math.random() * 30)}°C`;
}

async function getTime(location: string) {
  console.log(`Getting time for ${location}...`);
  const now = new Date();
  return `${now.getHours()}:${now.getMinutes()}`;
}

// Create an agent with directly registered functions
const agent = new Agent({ 
  instructions: `You provide the current weather and time for requested locations.`,
  name: "DirectFunctionAgent",
  // Register functions directly as an array without needing to make them global
  tools: [getWeather, getTime]
});

// Start the agent with a prompt that will trigger tool usage
agent.start("What's the weather and time in Paris, France and Tokyo, Japan?");
