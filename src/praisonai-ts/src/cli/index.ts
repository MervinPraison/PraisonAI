#!/usr/bin/env node
/**
 * PraisonAI TypeScript CLI
 */

import { createProvider, isProviderAvailable, getAvailableProviders } from '../llm/providers';
import { Session } from '../session';
import { tool, ToolRegistry } from '../tools/decorator';

interface CLIOptions {
  model?: string;
  stream?: boolean;
  verbose?: boolean;
  sessionId?: string;
}

async function chat(prompt: string, options: CLIOptions = {}): Promise<string> {
  const model = options.model || process.env.PRAISONAI_MODEL || 'openai/gpt-4o-mini';
  const provider = createProvider(model);
  
  const session = new Session({ id: options.sessionId });
  session.addMessage({ role: 'user', content: prompt });

  if (options.stream) {
    let fullText = '';
    const stream = await provider.streamText({
      messages: [{ role: 'user', content: prompt }],
      onToken: (token) => {
        process.stdout.write(token);
        fullText += token;
      }
    });
    
    for await (const chunk of stream) {
      // Stream is consumed by onToken
    }
    console.log(); // New line after streaming
    return fullText;
  } else {
    const result = await provider.generateText({
      messages: [{ role: 'user', content: prompt }]
    });
    console.log(result.text);
    return result.text;
  }
}

async function listProviders(): Promise<void> {
  console.log('Available Providers:');
  const available = getAvailableProviders();
  
  const providers = ['openai', 'anthropic', 'google'];
  for (const p of providers) {
    const status = available.includes(p) ? '✅' : '❌';
    console.log(`  ${status} ${p}`);
  }
}

async function version(): Promise<void> {
  const pkg = require('../../package.json');
  console.log(`praisonai v${pkg.version}`);
}

async function help(): Promise<void> {
  console.log(`
PraisonAI TypeScript CLI

Usage:
  praisonai-ts chat <prompt>     Chat with an AI agent
  praisonai-ts providers         List available providers
  praisonai-ts version           Show version
  praisonai-ts help              Show this help

Options:
  --model, -m <model>     Model to use (e.g., openai/gpt-4o-mini)
  --stream, -s            Enable streaming output
  --verbose, -v           Verbose output
  --session <id>          Session ID for conversation continuity

Environment Variables:
  OPENAI_API_KEY          OpenAI API key
  ANTHROPIC_API_KEY       Anthropic API key
  GOOGLE_API_KEY          Google API key
  PRAISONAI_MODEL         Default model

Examples:
  praisonai-ts chat "Hello, how are you?"
  praisonai-ts chat "Write a poem" --stream
  praisonai-ts chat "Explain AI" -m anthropic/claude-sonnet-4-20250514
  praisonai-ts providers
`);
}

function parseArgs(args: string[]): { command: string; prompt: string; options: CLIOptions } {
  const options: CLIOptions = {};
  let command = 'help';
  let prompt = '';
  
  let i = 0;
  while (i < args.length) {
    const arg = args[i];
    
    if (arg === '--model' || arg === '-m') {
      options.model = args[++i];
    } else if (arg === '--stream' || arg === '-s') {
      options.stream = true;
    } else if (arg === '--verbose' || arg === '-v') {
      options.verbose = true;
    } else if (arg === '--session') {
      options.sessionId = args[++i];
    } else if (!arg.startsWith('-')) {
      if (!command || command === 'help') {
        command = arg;
      } else {
        prompt = arg;
      }
    }
    i++;
  }
  
  return { command, prompt, options };
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const { command, prompt, options } = parseArgs(args);
  
  try {
    switch (command) {
      case 'chat':
        if (!prompt) {
          console.error('Error: Please provide a prompt');
          process.exit(1);
        }
        await chat(prompt, options);
        break;
      case 'providers':
        await listProviders();
        break;
      case 'version':
        await version();
        break;
      case 'help':
      default:
        await help();
        break;
    }
  } catch (error: any) {
    console.error('Error:', error.message);
    if (options.verbose) {
      console.error(error.stack);
    }
    process.exit(1);
  }
}

// Export for programmatic use
export { chat, listProviders, version, help, parseArgs };

// Run CLI if executed directly
if (require.main === module) {
  main();
}
