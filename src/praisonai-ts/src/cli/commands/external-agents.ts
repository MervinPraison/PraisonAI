/**
 * CLI command: external-agents
 * Integration with external AI CLI tools
 */

import { 
  getExternalAgentRegistry, 
  createExternalAgent,
  ClaudeCodeAgent,
  GeminiCliAgent,
  CodexCliAgent,
  AiderAgent
} from '../features/external-agents';

export async function execute(args: string[], options: Record<string, unknown>): Promise<void> {
  const subcommand = args[0] || 'help';
  const isJson = Boolean(options.output === 'json' || options.json);

  switch (subcommand) {
    case 'list':
      await handleList(isJson);
      break;
    case 'check':
      await handleCheck(args.slice(1), isJson);
      break;
    case 'run':
      await handleRun(args.slice(1), options, isJson);
      break;
    case 'help':
    default:
      showHelp(isJson);
  }
}

async function handleList(isJson: boolean): Promise<void> {
  const registry = getExternalAgentRegistry();
  const all = registry.list();
  const available = await registry.getAvailable();

  if (isJson) {
    console.log(JSON.stringify({
      success: true,
      agents: all,
      available
    }, null, 2));
  } else {
    console.log('External Agents:\n');
    for (const name of all) {
      const status = available.includes(name) ? '✓' : '✗';
      console.log(`  ${status} ${name}`);
    }
    console.log(`\n${available.length}/${all.length} available`);
  }
}

async function handleCheck(args: string[], isJson: boolean): Promise<void> {
  const name = args[0];
  
  if (!name) {
    console.error('Error: Agent name is required');
    process.exit(1);
  }

  const agent = createExternalAgent(name);
  
  if (!agent) {
    if (isJson) {
      console.log(JSON.stringify({ success: false, error: `Unknown agent: ${name}` }));
    } else {
      console.error(`Unknown agent: ${name}`);
    }
    process.exit(1);
  }

  const available = await agent.isAvailable();

  if (isJson) {
    console.log(JSON.stringify({ success: true, agent: name, available }));
  } else {
    if (available) {
      console.log(`✓ ${name} is available`);
    } else {
      console.log(`✗ ${name} is not available (CLI not found)`);
    }
  }
}

async function handleRun(args: string[], options: Record<string, unknown>, isJson: boolean): Promise<void> {
  const name = args[0];
  const prompt = args.slice(1).join(' ');

  if (!name) {
    console.error('Error: Agent name is required');
    process.exit(1);
  }

  if (!prompt) {
    console.error('Error: Prompt is required');
    process.exit(1);
  }

  const cwd = options.cwd as string | undefined;
  const agent = createExternalAgent(name, cwd);

  if (!agent) {
    if (isJson) {
      console.log(JSON.stringify({ success: false, error: `Unknown agent: ${name}` }));
    } else {
      console.error(`Unknown agent: ${name}`);
    }
    process.exit(1);
  }

  if (!await agent.isAvailable()) {
    if (isJson) {
      console.log(JSON.stringify({ success: false, error: `${name} CLI not available` }));
    } else {
      console.error(`${name} CLI not available`);
    }
    process.exit(1);
  }

  const result = await agent.execute(prompt);

  if (isJson) {
    console.log(JSON.stringify(result, null, 2));
  } else {
    if (result.success) {
      console.log(result.output);
    } else {
      console.error(`Error: ${result.error}`);
      process.exit(result.exitCode);
    }
  }
}

function showHelp(isJson: boolean): void {
  const help = {
    command: 'external-agents',
    description: 'Integration with external AI CLI tools',
    subcommands: {
      list: 'List all external agents and availability',
      check: 'Check if an agent is available',
      run: 'Run a prompt with an external agent'
    },
    agents: {
      claude: 'Claude Code CLI',
      gemini: 'Gemini CLI',
      codex: 'OpenAI Codex CLI',
      aider: 'Aider CLI'
    },
    flags: {
      '--cwd': 'Working directory for the agent',
      '--json': 'Output in JSON format'
    },
    examples: [
      'praisonai-ts external-agents list',
      'praisonai-ts external-agents check claude',
      'praisonai-ts external-agents run claude "Explain this code"',
      'praisonai-ts external-agents run gemini "Refactor this function" --cwd ./src'
    ]
  };

  if (isJson) {
    console.log(JSON.stringify(help, null, 2));
  } else {
    console.log('External Agents - AI CLI tool integration\n');
    console.log('Subcommands:');
    for (const [cmd, desc] of Object.entries(help.subcommands)) {
      console.log(`  ${cmd.padEnd(12)} ${desc}`);
    }
    console.log('\nSupported Agents:');
    for (const [agent, desc] of Object.entries(help.agents)) {
      console.log(`  ${agent.padEnd(12)} ${desc}`);
    }
    console.log('\nFlags:');
    for (const [flag, desc] of Object.entries(help.flags)) {
      console.log(`  ${flag.padEnd(12)} ${desc}`);
    }
    console.log('\nExamples:');
    for (const ex of help.examples) {
      console.log(`  ${ex}`);
    }
  }
}
