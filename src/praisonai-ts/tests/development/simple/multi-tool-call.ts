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
(global as any).get_weather = async function(location: string) {
    console.log(`Getting weather for ${location}...`);
    return `${Math.floor(Math.random() * 30)}°C`;
};

(global as any).get_time = async function(location: string) {
    console.log(`Getting time for ${location}...`);
    const now = new Date();
    return `${now.getHours()}:${now.getMinutes()}`;
};

const agent = new Agent({ 
  instructions: `You provide the current weather and time for requested locations.`,
  name: "WeatherTimeAgent",
  tools: [getWeather, getTime]
});

agent.start("What's the weather and time in Paris, France and Tokyo, Japan?");
