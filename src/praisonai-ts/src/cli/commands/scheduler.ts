/**
 * CLI command: scheduler
 * Agent task scheduling with cron-like patterns
 */

import { Scheduler, createScheduler, cronExpressions } from '../features/scheduler';

export async function execute(args: string[], options: Record<string, unknown>): Promise<void> {
  const subcommand = args[0] || 'help';
  const isJson = Boolean(options.output === 'json' || options.json);

  switch (subcommand) {
    case 'create':
      await handleCreate(args.slice(1), options, isJson);
      break;
    case 'list':
      await handleList(options, isJson);
      break;
    case 'run':
      await handleRun(args.slice(1), options, isJson);
      break;
    case 'remove':
      await handleRemove(args.slice(1), options, isJson);
      break;
    case 'enable':
      await handleEnable(args.slice(1), options, isJson);
      break;
    case 'disable':
      await handleDisable(args.slice(1), options, isJson);
      break;
    case 'patterns':
      await handlePatterns(isJson);
      break;
    case 'help':
    default:
      showHelp(isJson);
  }
}

async function handleCreate(args: string[], options: Record<string, unknown>, isJson: boolean): Promise<void> {
  const name = args[0];
  const cron = options.cron as string | undefined;
  const interval = options.interval as number | undefined;

  if (!name) {
    const error = { error: 'Task name is required' };
    if (isJson) {
      console.log(JSON.stringify(error));
    } else {
      console.error('Error: Task name is required');
      console.log('Usage: praisonai-ts scheduler create <name> --cron "* * * * *"');
    }
    process.exit(1);
  }

  if (!cron && !interval) {
    const error = { error: 'Either --cron or --interval is required' };
    if (isJson) {
      console.log(JSON.stringify(error));
    } else {
      console.error('Error: Either --cron or --interval is required');
    }
    process.exit(1);
  }

  const scheduler = createScheduler();
  const id = scheduler.add({
    name,
    cron,
    interval: interval ? interval * 1000 : undefined,
    task: async () => {
      console.log(`Task ${name} executed at ${new Date().toISOString()}`);
      return { executed: true };
    }
  });

  const result = {
    success: true,
    id,
    name,
    cron,
    interval,
    message: `Task '${name}' created with ID: ${id}`
  };

  if (isJson) {
    console.log(JSON.stringify(result, null, 2));
  } else {
    console.log(`✓ Task '${name}' created`);
    console.log(`  ID: ${id}`);
    if (cron) console.log(`  Cron: ${cron}`);
    if (interval) console.log(`  Interval: ${interval}s`);
  }
}

async function handleList(options: Record<string, unknown>, isJson: boolean): Promise<void> {
  const scheduler = createScheduler();
  const tasks = scheduler.getAllTasks();

  if (isJson) {
    console.log(JSON.stringify({ success: true, tasks }, null, 2));
  } else {
    if (tasks.length === 0) {
      console.log('No scheduled tasks');
    } else {
      console.log('Scheduled Tasks:');
      for (const task of tasks) {
        console.log(`  ${task.name} (${task.id})`);
        console.log(`    Status: ${task.status}`);
        console.log(`    Enabled: ${task.enabled}`);
        console.log(`    Run count: ${task.runCount}`);
        if (task.nextRun) console.log(`    Next run: ${task.nextRun.toISOString()}`);
      }
    }
  }
}

async function handleRun(args: string[], options: Record<string, unknown>, isJson: boolean): Promise<void> {
  const id = args[0];
  if (!id) {
    console.error('Error: Task ID is required');
    process.exit(1);
  }

  const scheduler = createScheduler();
  try {
    const result = await scheduler.runNow(id);
    if (isJson) {
      console.log(JSON.stringify({ success: true, result }, null, 2));
    } else {
      console.log(`✓ Task ${id} executed successfully`);
    }
  } catch (error: any) {
    if (isJson) {
      console.log(JSON.stringify({ success: false, error: error.message }));
    } else {
      console.error(`Error: ${error.message}`);
    }
    process.exit(1);
  }
}

async function handleRemove(args: string[], options: Record<string, unknown>, isJson: boolean): Promise<void> {
  const id = args[0];
  if (!id) {
    console.error('Error: Task ID is required');
    process.exit(1);
  }

  const scheduler = createScheduler();
  const removed = scheduler.remove(id);

  if (isJson) {
    console.log(JSON.stringify({ success: removed, id }));
  } else {
    if (removed) {
      console.log(`✓ Task ${id} removed`);
    } else {
      console.error(`Task ${id} not found`);
      process.exit(1);
    }
  }
}

async function handleEnable(args: string[], options: Record<string, unknown>, isJson: boolean): Promise<void> {
  const id = args[0];
  if (!id) {
    console.error('Error: Task ID is required');
    process.exit(1);
  }

  const scheduler = createScheduler();
  const enabled = scheduler.enable(id);

  if (isJson) {
    console.log(JSON.stringify({ success: enabled, id }));
  } else {
    console.log(enabled ? `✓ Task ${id} enabled` : `Task ${id} not found`);
  }
}

async function handleDisable(args: string[], options: Record<string, unknown>, isJson: boolean): Promise<void> {
  const id = args[0];
  if (!id) {
    console.error('Error: Task ID is required');
    process.exit(1);
  }

  const scheduler = createScheduler();
  const disabled = scheduler.disable(id);

  if (isJson) {
    console.log(JSON.stringify({ success: disabled, id }));
  } else {
    console.log(disabled ? `✓ Task ${id} disabled` : `Task ${id} not found`);
  }
}

async function handlePatterns(isJson: boolean): Promise<void> {
  const patterns = {
    everyMinute: cronExpressions.everyMinute,
    every5Minutes: cronExpressions.every5Minutes,
    every15Minutes: cronExpressions.every15Minutes,
    everyHour: cronExpressions.everyHour,
    everyDay: cronExpressions.everyDay,
    everyWeek: cronExpressions.everyWeek,
    everyMonth: cronExpressions.everyMonth,
    weekdays: cronExpressions.weekdays,
    weekends: cronExpressions.weekends
  };

  if (isJson) {
    console.log(JSON.stringify({ success: true, patterns }, null, 2));
  } else {
    console.log('Common Cron Patterns:');
    for (const [name, pattern] of Object.entries(patterns)) {
      console.log(`  ${name}: ${pattern}`);
    }
  }
}

function showHelp(isJson: boolean): void {
  const help = {
    command: 'scheduler',
    description: 'Agent task scheduling with cron-like patterns',
    subcommands: {
      create: 'Create a scheduled task',
      list: 'List all scheduled tasks',
      run: 'Run a task immediately',
      remove: 'Remove a scheduled task',
      enable: 'Enable a task',
      disable: 'Disable a task',
      patterns: 'Show common cron patterns'
    },
    flags: {
      '--cron': 'Cron expression (e.g., "*/5 * * * *")',
      '--interval': 'Interval in seconds',
      '--json': 'Output in JSON format'
    },
    examples: [
      'praisonai-ts scheduler create my-task --cron "*/5 * * * *"',
      'praisonai-ts scheduler create backup --interval 3600',
      'praisonai-ts scheduler list',
      'praisonai-ts scheduler run <task-id>',
      'praisonai-ts scheduler patterns'
    ]
  };

  if (isJson) {
    console.log(JSON.stringify(help, null, 2));
  } else {
    console.log('Scheduler - Agent task scheduling\n');
    console.log('Subcommands:');
    for (const [cmd, desc] of Object.entries(help.subcommands)) {
      console.log(`  ${cmd.padEnd(12)} ${desc}`);
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
