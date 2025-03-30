# PraisonAI Tool Registration Examples

This document demonstrates the three different ways to register tool functions in PraisonAI.

## Method 1: Using the `tools` array with function objects directly

```typescript
import { Agent } from 'praisonai';

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
  // Register functions directly as an array
  tools: [getWeather, getTime]
});

// Start the agent with a prompt that will trigger tool usage
agent.start("What's the weather and time in Paris, France?");
```

## Method 2: Using the `toolFunctions` object with name-function pairs

```typescript
import { Agent } from 'praisonai';

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
  // Register functions with custom names
  toolFunctions: {
    get_weather: getWeather,
    get_time: getTime
  }
});

// Start the agent with a prompt that will trigger tool usage
agent.start("What's the weather and time in Paris, France?");
```

## Method 3: Using the `tools` array with pre-defined tool definitions

```typescript
import { Agent } from 'praisonai';

// Define the functions
async function getWeather(location: string) {
  console.log(`Getting weather for ${location}...`);
  return `${Math.floor(Math.random() * 30)}°C`;
}

async function getTime(location: string) {
  console.log(`Getting time for ${location}...`);
  const now = new Date();
  return `${now.getHours()}:${now.getMinutes()}`;
}

// Register functions globally
import { registerFunction } from 'praisonai';
registerFunction('get_weather', getWeather);
registerFunction('get_time', getTime);

// Define tool definitions
const weatherTool = {
  type: "function",
  function: {
    name: "get_weather",
    description: "Get the current weather for a location",
    parameters: {
      type: "object",
      properties: {
        location: {
          type: "string",
          description: "The location to get weather for"
        }
      },
      required: ["location"]
    }
  }
};

const timeTool = {
  type: "function",
  function: {
    name: "get_time",
    description: "Get the current time for a location",
    parameters: {
      type: "object",
      properties: {
        location: {
          type: "string",
          description: "The location to get time for"
        }
      },
      required: ["location"]
    }
  }
};

// Create an agent with pre-defined tool definitions
const agent = new Agent({ 
  instructions: `You provide the current weather and time for requested locations.`,
  name: "ToolDefinitionAgent",
  // Register pre-defined tool definitions
  tools: [weatherTool, timeTool]
});

// Start the agent with a prompt that will trigger tool usage
agent.start("What's the weather and time in Paris, France?");
```

## Combined Approach

You can also combine these approaches as needed:

```typescript
import { Agent } from 'praisonai';

// Define the functions
async function getWeather(location: string) {
  console.log(`Getting weather for ${location}...`);
  return `${Math.floor(Math.random() * 30)}°C`;
}

async function getTime(location: string) {
  console.log(`Getting time for ${location}...`);
  const now = new Date();
  return `${now.getHours()}:${now.getMinutes()}`;
}

// Define a custom tool definition
const calculatorTool = {
  type: "function",
  function: {
    name: "calculate",
    description: "Perform a calculation",
    parameters: {
      type: "object",
      properties: {
        expression: {
          type: "string",
          description: "The mathematical expression to calculate"
        }
      },
      required: ["expression"]
    }
  }
};

// Register the calculator function globally
import { registerFunction } from 'praisonai';
registerFunction('calculate', async (expression: string) => {
  console.log(`Calculating ${expression}...`);
  // Simple eval for demonstration purposes only
  return eval(expression).toString();
});

// Create an agent with mixed tool registration approaches
const agent = new Agent({ 
  instructions: `You can provide weather, time, and perform calculations.`,
  name: "MixedToolAgent",
  // Register functions directly as an array
  tools: [getWeather, getTime, calculatorTool]
});

// Start the agent with a prompt that will trigger tool usage
agent.start("What's the weather in Paris, the time in Tokyo, and what is 25 * 4?");
```
