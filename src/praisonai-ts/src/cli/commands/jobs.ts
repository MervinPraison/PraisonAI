/**
 * CLI command: jobs
 * Background job queue management
 */

import { JobQueue, createJobQueue, createFileJobStorage } from '../features/background-jobs';

let globalQueue: JobQueue | null = null;

function getQueue(storagePath?: string): JobQueue {
  if (!globalQueue) {
    const storage = storagePath ? createFileJobStorage(storagePath) : undefined;
    globalQueue = createJobQueue({ storage });
  }
  return globalQueue;
}

export async function execute(args: string[], options: Record<string, unknown>): Promise<void> {
  const subcommand = args[0] || 'help';
  const isJson = Boolean(options.output === 'json' || options.json);
  const storagePath = options.storage as string | undefined;

  switch (subcommand) {
    case 'add':
      await handleAdd(args.slice(1), options, isJson, storagePath);
      break;
    case 'list':
      await handleList(options, isJson, storagePath);
      break;
    case 'get':
      await handleGet(args.slice(1), isJson, storagePath);
      break;
    case 'cancel':
      await handleCancel(args.slice(1), isJson, storagePath);
      break;
    case 'retry':
      await handleRetry(args.slice(1), isJson, storagePath);
      break;
    case 'process':
      await handleProcess(args.slice(1), isJson, storagePath);
      break;
    case 'stats':
      await handleStats(isJson, storagePath);
      break;
    case 'cleanup':
      await handleCleanup(options, isJson, storagePath);
      break;
    case 'help':
    default:
      showHelp(isJson);
  }
}

async function handleAdd(args: string[], options: Record<string, unknown>, isJson: boolean, storagePath?: string): Promise<void> {
  const name = args[0];
  const dataStr = args[1] || '{}';

  if (!name) {
    console.error('Error: Job name is required');
    process.exit(1);
  }

  let data: Record<string, unknown>;
  try {
    data = JSON.parse(dataStr);
  } catch {
    data = { input: dataStr };
  }

  const priority = (options.priority as string) || 'normal';
  const queue = getQueue(storagePath);
  
  const job = await queue.add(name, data, {
    priority: priority as 'low' | 'normal' | 'high' | 'critical'
  });

  if (isJson) {
    console.log(JSON.stringify({ success: true, job }, null, 2));
  } else {
    console.log(`✓ Job created: ${job.id}`);
    console.log(`  Name: ${job.name}`);
    console.log(`  Priority: ${job.priority}`);
    console.log(`  Status: ${job.status}`);
  }
}

async function handleList(options: Record<string, unknown>, isJson: boolean, storagePath?: string): Promise<void> {
  const queue = getQueue(storagePath);
  const status = options.status as string | undefined;
  
  let jobs = await queue.getAll();
  if (status) {
    jobs = jobs.filter(j => j.status === status);
  }

  if (isJson) {
    console.log(JSON.stringify({ success: true, jobs }, null, 2));
  } else {
    if (jobs.length === 0) {
      console.log('No jobs found');
    } else {
      console.log('Jobs:');
      for (const job of jobs) {
        console.log(`  ${job.id}`);
        console.log(`    Name: ${job.name}`);
        console.log(`    Status: ${job.status}`);
        console.log(`    Priority: ${job.priority}`);
        console.log(`    Attempts: ${job.attempts}/${job.maxAttempts}`);
        if (job.error) console.log(`    Error: ${job.error}`);
      }
    }
  }
}

async function handleGet(args: string[], isJson: boolean, storagePath?: string): Promise<void> {
  const id = args[0];
  if (!id) {
    console.error('Error: Job ID is required');
    process.exit(1);
  }

  const queue = getQueue(storagePath);
  const job = await queue.get(id);

  if (!job) {
    if (isJson) {
      console.log(JSON.stringify({ success: false, error: 'Job not found' }));
    } else {
      console.error(`Job ${id} not found`);
    }
    process.exit(1);
  }

  if (isJson) {
    console.log(JSON.stringify({ success: true, job }, null, 2));
  } else {
    console.log(`Job: ${job.id}`);
    console.log(`  Name: ${job.name}`);
    console.log(`  Status: ${job.status}`);
    console.log(`  Priority: ${job.priority}`);
    console.log(`  Attempts: ${job.attempts}/${job.maxAttempts}`);
    console.log(`  Created: ${job.createdAt}`);
    if (job.startedAt) console.log(`  Started: ${job.startedAt}`);
    if (job.completedAt) console.log(`  Completed: ${job.completedAt}`);
    if (job.error) console.log(`  Error: ${job.error}`);
    if (job.result) console.log(`  Result: ${JSON.stringify(job.result)}`);
  }
}

async function handleCancel(args: string[], isJson: boolean, storagePath?: string): Promise<void> {
  const id = args[0];
  if (!id) {
    console.error('Error: Job ID is required');
    process.exit(1);
  }

  const queue = getQueue(storagePath);
  const cancelled = await queue.cancel(id);

  if (isJson) {
    console.log(JSON.stringify({ success: cancelled, id }));
  } else {
    console.log(cancelled ? `✓ Job ${id} cancelled` : `Could not cancel job ${id}`);
  }
}

async function handleRetry(args: string[], isJson: boolean, storagePath?: string): Promise<void> {
  const id = args[0];
  if (!id) {
    console.error('Error: Job ID is required');
    process.exit(1);
  }

  const queue = getQueue(storagePath);
  const retried = await queue.retry(id);

  if (isJson) {
    console.log(JSON.stringify({ success: retried, id }));
  } else {
    console.log(retried ? `✓ Job ${id} queued for retry` : `Could not retry job ${id}`);
  }
}

async function handleProcess(args: string[], isJson: boolean, storagePath?: string): Promise<void> {
  const id = args[0];
  if (!id) {
    console.error('Error: Job ID is required');
    process.exit(1);
  }

  const queue = getQueue(storagePath);
  
  // Register a simple handler
  queue.register('default', async (job) => {
    return { processed: true, data: job.data };
  });

  try {
    const result = await queue.processNow(id);
    if (isJson) {
      console.log(JSON.stringify({ success: true, result }, null, 2));
    } else {
      console.log(`✓ Job ${id} processed`);
      console.log(`  Result: ${JSON.stringify(result)}`);
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

async function handleStats(isJson: boolean, storagePath?: string): Promise<void> {
  const queue = getQueue(storagePath);
  const stats = await queue.getStats();

  if (isJson) {
    console.log(JSON.stringify({ success: true, stats }, null, 2));
  } else {
    console.log('Job Queue Stats:');
    console.log(`  Pending: ${stats.pending}`);
    console.log(`  Running: ${stats.running}`);
    console.log(`  Completed: ${stats.completed}`);
    console.log(`  Failed: ${stats.failed}`);
    console.log(`  Cancelled: ${stats.cancelled}`);
  }
}

async function handleCleanup(options: Record<string, unknown>, isJson: boolean, storagePath?: string): Promise<void> {
  const queue = getQueue(storagePath);
  const days = (options.days as number) || 7;
  const olderThan = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
  
  const count = await queue.cleanup(olderThan);

  if (isJson) {
    console.log(JSON.stringify({ success: true, cleaned: count }));
  } else {
    console.log(`✓ Cleaned up ${count} jobs older than ${days} days`);
  }
}

function showHelp(isJson: boolean): void {
  const help = {
    command: 'jobs',
    description: 'Background job queue management',
    subcommands: {
      add: 'Add a new job to the queue',
      list: 'List all jobs',
      get: 'Get job details',
      cancel: 'Cancel a pending job',
      retry: 'Retry a failed job',
      process: 'Process a job immediately',
      stats: 'Show queue statistics',
      cleanup: 'Clean up old completed/failed jobs'
    },
    flags: {
      '--storage': 'Path to job storage file',
      '--priority': 'Job priority (low, normal, high, critical)',
      '--status': 'Filter by status',
      '--days': 'Days for cleanup threshold',
      '--json': 'Output in JSON format'
    },
    examples: [
      'praisonai-ts jobs add my-job \'{"input": "data"}\'',
      'praisonai-ts jobs add task --priority high',
      'praisonai-ts jobs list --status pending',
      'praisonai-ts jobs get <job-id>',
      'praisonai-ts jobs cancel <job-id>',
      'praisonai-ts jobs stats',
      'praisonai-ts jobs cleanup --days 30'
    ]
  };

  if (isJson) {
    console.log(JSON.stringify(help, null, 2));
  } else {
    console.log('Jobs - Background job queue management\n');
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
