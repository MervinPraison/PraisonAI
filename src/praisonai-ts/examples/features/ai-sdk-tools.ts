/**
 * AI SDK Tools Registry Example
 * 
 * Demonstrates how to use the built-in AI SDK tools with PraisonAI agents.
 */

import { Agent } from '../../src/agent';
import { tools, registerBuiltinTools } from '../../src/tools/tools';
import { getToolsRegistry } from '../../src/tools/registry/registry';
import { createLoggingMiddleware, createTimeoutMiddleware, createRedactionMiddleware } from '../../src/tools/registry/middleware';
import type { ToolExecutionContext } from '../../src/tools/registry/types';

// Register all built-in tools
registerBuiltinTools();

// Example 1: Web Research Agent with Tavily
async function webResearchExample() {
  console.log('\n=== Web Research Agent ===\n');
  
  const agent = new Agent({
    name: 'WebResearcher',
    instructions: 'You are a web research assistant. Search the web to find information.',
    tools: [tools.tavily()],
  });

  // Note: Requires TAVILY_API_KEY environment variable
  // const result = await agent.run('What are the latest developments in AI?');
  // console.log(result.text);
  
  console.log('Web research agent created with Tavily search tool.');
  console.log('Set TAVILY_API_KEY to use this agent.');
}

// Example 2: Code Execution Agent
async function codeExecutionExample() {
  console.log('\n=== Code Execution Agent ===\n');
  
  const agent = new Agent({
    name: 'CodeRunner',
    instructions: 'You can execute Python code to solve computational problems.',
    tools: [tools.codeExecution()],
  });

  // Note: Requires Vercel deployment or VERCEL_OIDC_TOKEN
  // const result = await agent.run('Calculate the first 10 Fibonacci numbers');
  // console.log(result.text);
  
  console.log('Code execution agent created.');
  console.log('Deploy to Vercel or set VERCEL_OIDC_TOKEN to use.');
}

// Example 3: Secure Agent with Guardrails
async function secureAgentExample() {
  console.log('\n=== Secure Agent with Guardrails ===\n');
  
  const agent = new Agent({
    name: 'SecureAssistant',
    instructions: 'You are a secure assistant that protects user data.',
    tools: [
      tools.guard(),   // Check for prompt injection
      tools.redact(),  // Remove PII from responses
      tools.verify(),  // Verify claims
    ],
  });

  // Note: Requires SUPERAGENT_API_KEY
  console.log('Secure agent created with guard, redact, and verify tools.');
  console.log('Set SUPERAGENT_API_KEY to use security features.');
}

// Example 4: Finance Research Agent with Valyu
async function financeResearchExample() {
  console.log('\n=== Finance Research Agent ===\n');
  
  const agent = new Agent({
    name: 'FinanceAnalyst',
    instructions: 'You are a financial analyst. Research stocks, SEC filings, and economic data.',
    tools: [
      tools.valyuFinanceSearch(),
      tools.valyuSecSearch(),
      tools.valyuEconomicsSearch(),
    ],
  });

  // Note: Requires VALYU_API_KEY
  console.log('Finance research agent created with Valyu tools.');
  console.log('Set VALYU_API_KEY to use finance search features.');
}

// Example 5: Multi-Tool Agent
async function multiToolExample() {
  console.log('\n=== Multi-Tool Research Agent ===\n');
  
  const agent = new Agent({
    name: 'ResearchAssistant',
    instructions: 'You are a comprehensive research assistant with access to multiple search tools.',
    tools: [
      tools.tavily(),           // General web search
      tools.exa(),              // Semantic search
      tools.valyuPaperSearch(), // Academic papers
      tools.firecrawl(),        // Web scraping
    ],
  });

  console.log('Multi-tool agent created with 4 different search tools.');
}

// Example 6: Using Middleware
async function middlewareExample() {
  console.log('\n=== Registry with Middleware ===\n');
  
  const registry = getToolsRegistry();
  
  // Add logging middleware
  registry.use(createLoggingMiddleware());
  
  // Add timeout middleware (30 second timeout)
  registry.use(createTimeoutMiddleware(30000));
  
  // Add PII redaction middleware
  registry.use(createRedactionMiddleware());
  
  // Set hooks for monitoring
  registry.setHooks({
    beforeToolCall: (name: string, input: unknown, ctx: ToolExecutionContext) => {
      console.log(`[Hook] Starting tool: ${name}`);
    },
    afterToolCall: (name: string, input: unknown, output: unknown, ctx: ToolExecutionContext) => {
      console.log(`[Hook] Completed tool: ${name}`);
    },
    onError: (name: string, error: Error, ctx: ToolExecutionContext) => {
      console.error(`[Hook] Error in tool ${name}:`, error.message);
    },
  });

  console.log('Registry configured with logging, timeout, and redaction middleware.');
}

// Example 7: Custom Tool Registration
async function customToolExample() {
  console.log('\n=== Custom Tool Registration ===\n');
  
  // Register a custom tool
  const customTool = tools.custom({
    id: 'my-calculator',
    name: 'calculator',
    description: 'Perform basic arithmetic calculations',
    parameters: {
      type: 'object',
      properties: {
        expression: {
          type: 'string',
          description: 'Mathematical expression to evaluate',
        },
      },
      required: ['expression'],
    },
    execute: async (input: { expression: string }) => {
      // Simple eval for demo (use a proper math parser in production)
      try {
        const result = Function(`"use strict"; return (${input.expression})`)();
        return { result, expression: input.expression };
      } catch (error) {
        return { error: 'Invalid expression', expression: input.expression };
      }
    },
  });

  const agent = new Agent({
    name: 'Calculator',
    instructions: 'You can perform calculations.',
    tools: [customTool],
  });

  console.log('Custom calculator tool registered and agent created.');
}

// Example 8: List Available Tools
async function listToolsExample() {
  console.log('\n=== Available Tools ===\n');
  
  const allTools = tools.list();
  
  console.log(`Total registered tools: ${allTools.length}\n`);
  
  for (const tool of allTools) {
    console.log(`• ${tool.id} (${tool.displayName})`);
    console.log(`  Tags: ${tool.tags.join(', ')}`);
    console.log(`  Package: ${tool.packageName}`);
    console.log('');
  }
}

// Run all examples
async function main() {
  console.log('='.repeat(60));
  console.log('AI SDK Tools Registry Examples');
  console.log('='.repeat(60));

  await webResearchExample();
  await codeExecutionExample();
  await secureAgentExample();
  await financeResearchExample();
  await multiToolExample();
  await middlewareExample();
  await customToolExample();
  await listToolsExample();

  console.log('\n' + '='.repeat(60));
  console.log('Examples completed!');
  console.log('='.repeat(60));
}

main().catch(console.error);
