/**
 * CLI command: interactive
 * Interactive TUI mode with slash commands
 */

import { InteractiveTUI, createInteractiveTUI } from '../features/interactive-tui';
import { createCostTracker } from '../features/cost-tracker';

export async function execute(args: string[], options: Record<string, unknown>): Promise<void> {
  const isJson = Boolean(options.output === 'json' || options.json);

  if (isJson) {
    console.log(JSON.stringify({
      success: false,
      error: 'Interactive mode does not support JSON output'
    }));
    process.exit(1);
  }

  const historyFile = options.history as string | undefined;
  const model = options.model as string | undefined;

  console.log('Starting interactive mode...');
  console.log('Type /help for available commands, /exit to quit.\n');

  const tui = createInteractiveTUI({
    prompt: options.prompt as string || '> ',
    historyFile,
    welcomeMessage: `PraisonAI Interactive Mode
Model: ${model || 'default'}
Type /help for commands, /exit to quit.`,
    onMessage: async (message) => {
      // Simple echo for now - in real usage this would call the agent
      return `You said: ${message}`;
    },
    onExit: () => {
      console.log('\nGoodbye!');
    }
  });

  // Update context with model if provided
  if (model) {
    tui.updateContext({ model });
  }

  try {
    await tui.start();
  } catch (error: any) {
    console.error(`Error: ${error.message}`);
    process.exit(1);
  }
}

export function showHelp(): void {
  console.log(`Interactive - Interactive TUI mode

Usage:
  praisonai-ts interactive [options]

Options:
  --model, -m     Model to use
  --prompt        Custom prompt string (default: "> ")
  --history       Path to history file

Slash Commands (in interactive mode):
  /help           Show available commands
  /cost           Show token usage and cost
  /clear          Clear conversation history
  /model [name]   Show or change model
  /tokens         Show token count
  /plan           Manage task plan
  /undo           Undo last action
  /diff           Show pending changes
  /commit         Commit pending changes
  /settings       Show or modify settings
  /map            Show repository map
  /exit           Exit interactive mode

Examples:
  praisonai-ts interactive
  praisonai-ts interactive --model gpt-4o
  praisonai-ts interactive --history ~/.praisonai_history
`);
}
