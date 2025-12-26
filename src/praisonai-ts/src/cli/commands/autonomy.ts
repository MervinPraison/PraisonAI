/**
 * CLI command: autonomy
 * Autonomy mode management for agent actions
 */

import { AutonomyManager, createAutonomyManager, MODE_POLICIES, type AutonomyMode } from '../features/autonomy-mode';

let manager: AutonomyManager | null = null;

function getManager(): AutonomyManager {
  if (!manager) {
    manager = createAutonomyManager();
  }
  return manager;
}

export async function execute(args: string[], options: Record<string, unknown>): Promise<void> {
  const subcommand = args[0] || 'help';
  const isJson = Boolean(options.output === 'json' || options.json);

  switch (subcommand) {
    case 'status':
      await handleStatus(isJson);
      break;
    case 'set':
      await handleSet(args.slice(1), isJson);
      break;
    case 'policies':
      await handlePolicies(args.slice(1), isJson);
      break;
    case 'reset':
      await handleReset(isJson);
      break;
    case 'help':
    default:
      showHelp(isJson);
  }
}

async function handleStatus(isJson: boolean): Promise<void> {
  const mgr = getManager();
  const summary = mgr.getSummary();
  const mode = mgr.getMode();
  const actionCount = mgr.getActionCount();

  if (isJson) {
    console.log(JSON.stringify({
      success: true,
      mode,
      actionCount,
      policies: MODE_POLICIES[mode]
    }, null, 2));
  } else {
    console.log(summary);
  }
}

async function handleSet(args: string[], isJson: boolean): Promise<void> {
  const mode = args[0] as AutonomyMode;
  
  if (!mode || !['suggest', 'auto_edit', 'full_auto'].includes(mode)) {
    console.error('Error: Valid mode required (suggest, auto_edit, full_auto)');
    process.exit(1);
  }

  const mgr = getManager();
  mgr.setMode(mode);

  if (isJson) {
    console.log(JSON.stringify({ success: true, mode }));
  } else {
    console.log(`✓ Autonomy mode set to: ${mode}`);
    console.log('\nPolicies for this mode:');
    for (const policy of MODE_POLICIES[mode]) {
      const status = policy.requiresApproval ? '⚠️ requires approval' : '✓ auto-approved';
      console.log(`  ${policy.action}: ${status}`);
    }
  }
}

async function handlePolicies(args: string[], isJson: boolean): Promise<void> {
  const mode = (args[0] as AutonomyMode) || 'suggest';
  
  if (!['suggest', 'auto_edit', 'full_auto'].includes(mode)) {
    console.error('Error: Valid mode required (suggest, auto_edit, full_auto)');
    process.exit(1);
  }

  const policies = MODE_POLICIES[mode];

  if (isJson) {
    console.log(JSON.stringify({ success: true, mode, policies }, null, 2));
  } else {
    console.log(`Policies for mode: ${mode}\n`);
    for (const policy of policies) {
      const status = policy.requiresApproval ? '⚠️ requires approval' : '✓ auto-approved';
      console.log(`  ${policy.action.padEnd(20)} ${status}`);
    }
  }
}

async function handleReset(isJson: boolean): Promise<void> {
  const mgr = getManager();
  mgr.clearRemembered();
  mgr.resetActionCount();
  mgr.setMode('suggest');

  if (isJson) {
    console.log(JSON.stringify({ success: true, message: 'Autonomy state reset' }));
  } else {
    console.log('✓ Autonomy state reset');
    console.log('  Mode: suggest');
    console.log('  Remembered decisions: cleared');
    console.log('  Action count: 0');
  }
}

function showHelp(isJson: boolean): void {
  const help = {
    command: 'autonomy',
    description: 'Autonomy mode management for agent actions',
    subcommands: {
      status: 'Show current autonomy status',
      set: 'Set autonomy mode',
      policies: 'Show policies for a mode',
      reset: 'Reset autonomy state'
    },
    modes: {
      suggest: 'Requires approval for most actions (default)',
      auto_edit: 'Auto-approves file edits, requires approval for others',
      full_auto: 'Auto-approves most actions (use with caution)'
    },
    flags: {
      '--json': 'Output in JSON format'
    },
    examples: [
      'praisonai-ts autonomy status',
      'praisonai-ts autonomy set suggest',
      'praisonai-ts autonomy set auto_edit',
      'praisonai-ts autonomy set full_auto',
      'praisonai-ts autonomy policies suggest',
      'praisonai-ts autonomy reset'
    ]
  };

  if (isJson) {
    console.log(JSON.stringify(help, null, 2));
  } else {
    console.log('Autonomy - Agent action approval management\n');
    console.log('Subcommands:');
    for (const [cmd, desc] of Object.entries(help.subcommands)) {
      console.log(`  ${cmd.padEnd(12)} ${desc}`);
    }
    console.log('\nModes:');
    for (const [mode, desc] of Object.entries(help.modes)) {
      console.log(`  ${mode.padEnd(12)} ${desc}`);
    }
    console.log('\nExamples:');
    for (const ex of help.examples) {
      console.log(`  ${ex}`);
    }
  }
}
