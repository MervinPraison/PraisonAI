/**
 * Agent with Tools - Pass plain functions as tools (5 lines)
 * 
 * Run: npx ts-node examples/quickstart/with-tools.ts
 */

import { Agent } from '../../src';

// Define a simple tool as a plain function
const getWeather = (city: string) => `Weather in ${city}: 22°C, Sunny`;

const agent = new Agent({
  instructions: "You are a weather assistant. Use the getWeather tool to answer questions.",
  tools: [getWeather]
});

agent.chat("What's the weather like in Paris?").then(console.log);
