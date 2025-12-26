/**
 * Custom Tool Example
 * Demonstrates creating custom tools using BaseTool class (plugin pattern)
 */

import { BaseTool, createTool, tool, ToolRegistry } from 'praisonai';

// Method 1: Extend BaseTool class (recommended for complex tools)
class WeatherTool extends BaseTool<{ location: string; units?: string }, { temp: number; condition: string }> {
  name = 'get_weather';
  description = 'Get current weather for a location';
  parameters = {
    type: 'object' as const,
    properties: {
      location: { type: 'string', description: 'City name' },
      units: { type: 'string', description: 'celsius or fahrenheit', default: 'celsius' }
    },
    required: ['location']
  };

  async run(params: { location: string; units?: string }): Promise<{ temp: number; condition: string }> {
    // Simulate API call
    console.log(`Getting weather for ${params.location} in ${params.units || 'celsius'}`);
    return { temp: 22, condition: 'sunny' };
  }
}

// Method 2: Use createTool function (quick inline tools)
const calculatorTool = createTool({
  name: 'calculator',
  description: 'Evaluate a math expression',
  parameters: {
    type: 'object',
    properties: {
      expression: { type: 'string', description: 'Math expression to evaluate' }
    },
    required: ['expression']
  },
  run: (params: { expression: string }) => {
    try {
      return eval(params.expression);
    } catch {
      return 'Error: Invalid expression';
    }
  }
});

// Method 3: Use tool() function with config object
const greeterTool = tool({
  name: 'greeter',
  description: 'Generate a personalized greeting',
  parameters: {
    type: 'object',
    properties: {
      name: { type: 'string', description: 'Name to greet' },
      style: { type: 'string', description: 'Greeting style: formal or casual' }
    },
    required: ['name']
  },
  execute: async (params: { name: string; style?: string }) => {
    if (params.style === 'formal') {
      return `Good day, ${params.name}. How may I assist you?`;
    }
    return `Hey ${params.name}! What's up?`;
  }
});

async function main() {
  console.log('=== Custom Tool Examples ===\n');

  // Test WeatherTool (class-based)
  console.log('--- WeatherTool (class-based) ---');
  const weather = new WeatherTool();
  console.log('Name:', weather.name);
  console.log('Description:', weather.description);
  
  const weatherResult = await weather.run({ location: 'New York' });
  console.log('Result:', weatherResult);
  
  // Safe execution with error handling
  const safeResult = await weather.safeRun({ location: 'London' });
  console.log('Safe result:', safeResult);

  // Get OpenAI schema
  console.log('OpenAI Schema:', JSON.stringify(weather.getSchema(), null, 2));

  // Test calculatorTool (createTool)
  console.log('\n--- Calculator Tool (createTool) ---');
  const calcResult = await calculatorTool.run({ expression: '10 * 5 + 2' });
  console.log('10 * 5 + 2 =', calcResult);

  // Test greeterTool (tool function)
  console.log('\n--- Greeter Tool (tool function) ---');
  const greeting1 = await greeterTool.execute({ name: 'Alice' });
  console.log('Casual:', greeting1);
  
  const greeting2 = await greeterTool.execute({ name: 'Mr. Smith', style: 'formal' });
  console.log('Formal:', greeting2);

  // Register tools in registry
  console.log('\n--- Tool Registry ---');
  const registry = new ToolRegistry();
  registry.register(greeterTool);
  
  console.log('Registered tools:', registry.list().map(t => t.name));
  console.log('OpenAI tools format:', registry.toOpenAITools().length, 'tools');

  // Validate tool
  console.log('\n--- Validation ---');
  console.log('WeatherTool valid:', weather.validate());
}

main().catch(console.error);
