import { Agent } from '../../../src/agent/proxy';

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
(global as any).get_weather = async function(location: string) {
    console.log(`Getting weather for ${location}...`);
    return `20°C`;
};

const agent = new Agent({ 
  instructions: `You provide the current weather for requested locations.`,
  name: "WeatherAgent",
  tools: [getWeather]
});

agent.start("What's the weather in Paris, France?");
