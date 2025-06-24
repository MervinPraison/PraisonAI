import { Agent } from 'praisonai';

/**
 * Example of a simple agent with multiple tool calling capability
 * 
 * This example demonstrates how to create a simple agent that can use multiple tools
 * to get weather and time information for different locations.
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

// Define a time tool
const getTime = {
  type: "function",
  function: {
    name: "get_time",
    description: "Get current time for a given location.",
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

// Make the functions globally available
// The agent will automatically find and use these functions
(global as any).get_weather = async function(location: string) {
    console.log(`Getting weather for ${location}...`);
    return `${Math.floor(Math.random() * 30)}°C`;
};

(global as any).get_time = async function(location: string) {
    console.log(`Getting time for ${location}...`);
    const now = new Date();
    return `${now.getHours()}:${now.getMinutes()}`;
};

// Create an agent with both weather and time tools
const agent = new Agent({ 
  instructions: `You provide the current weather and time for requested locations.`,
  name: "WeatherTimeAgent",
  tools: [getWeather, getTime]
});

// Start the agent with a prompt that will trigger multiple tool calls
agent.start("What's the weather and time in Paris, France and Tokyo, Japan?");
