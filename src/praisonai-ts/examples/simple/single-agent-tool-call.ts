import { Agent } from 'praisonai';

/**
 * Example of a simple agent with tool calling capability
 * 
 * This example demonstrates how to create a simple agent that can use tools
 * to get weather information for a location.
 */

// Define a weather tool
const getWeather = {
  type: "function",
  function: {
    name: "get_weather",
    description: "Get current temperature for a given location.",
    parameters: {
      type: "object",
      properties: {
        location: {
          type: "string",
          description: "City and country e.g. Bogotá, Colombia"
        }
      },
      required: ["location"],
      additionalProperties: false
    },
    strict: true
  }
};

// Make the function globally available
// The agent will automatically find and use this function
(global as any).get_weather = async function(location: string) {
    console.log(`Getting weather for ${location}...`);
    return `20°C`;
};

// Create an agent with the weather tool
const agent = new Agent({ 
  instructions: `You provide the current weather for requested locations.`,
  name: "WeatherAgent",
  tools: [getWeather]
});

// Start the agent with a prompt that will trigger tool usage
agent.start("What's the weather in Paris, France?");
