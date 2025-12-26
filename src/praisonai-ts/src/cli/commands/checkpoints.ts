/**
 * CLI command: checkpoints
 * Session state checkpointing and recovery
 */

import { CheckpointManager, createCheckpointManager, createFileCheckpointStorage } from '../features/checkpoints';

let manager: CheckpointManager | null = null;

function getManager(storagePath?: string): CheckpointManager {
  if (!manager) {
    const storage = storagePath ? createFileCheckpointStorage(storagePath) : undefined;
    manager = createCheckpointManager({ storage });
  }
  return manager;
}

export async function execute(args: string[], options: Record<string, unknown>): Promise<void> {
  const subcommand = args[0] || 'help';
  const isJson = Boolean(options.output === 'json' || options.json);
  const storagePath = options.storage as string | undefined;

  switch (subcommand) {
    case 'create':
      await handleCreate(args.slice(1), options, isJson, storagePath);
      break;
    case 'list':
      await handleList(isJson, storagePath);
      break;
    case 'get':
      await handleGet(args.slice(1), isJson, storagePath);
      break;
    case 'restore':
      await handleRestore(args.slice(1), isJson, storagePath);
      break;
    case 'delete':
      await handleDelete(args.slice(1), isJson, storagePath);
      break;
    case 'export':
      await handleExport(args.slice(1), isJson, storagePath);
      break;
    case 'import':
      await handleImport(args.slice(1), isJson, storagePath);
      break;
    case 'help':
    default:
      showHelp(isJson);
  }
}

async function handleCreate(args: string[], options: Record<string, unknown>, isJson: boolean, storagePath?: string): Promise<void> {
  const name = args[0] || `checkpoint-${Date.now()}`;
  const mgr = getManager(storagePath);
  
  // Set state from options if provided
  const state = options.state ? JSON.parse(options.state as string) : {};
  mgr.setState(state);
  
  const checkpoint = await mgr.create(name, {
    sessionId: options.session as string,
    metadata: options.metadata ? JSON.parse(options.metadata as string) : undefined
  });

  if (isJson) {
    console.log(JSON.stringify({ success: true, checkpoint }, null, 2));
  } else {
    console.log(`✓ Checkpoint created: ${checkpoint.id}`);
    console.log(`  Name: ${checkpoint.name}`);
    console.log(`  Time: ${checkpoint.timestamp.toISOString()}`);
  }
}

async function handleList(isJson: boolean, storagePath?: string): Promise<void> {
  const mgr = getManager(storagePath);
  const checkpoints = await mgr.list();

  if (isJson) {
    console.log(JSON.stringify({ success: true, checkpoints }, null, 2));
  } else {
    if (checkpoints.length === 0) {
      console.log('No checkpoints found');
    } else {
      console.log('Checkpoints:');
      for (const cp of checkpoints) {
        console.log(`  ${cp.name} (${cp.id})`);
        console.log(`    Created: ${cp.timestamp.toISOString()}`);
        if (cp.sessionId) console.log(`    Session: ${cp.sessionId}`);
      }
    }
  }
}

async function handleGet(args: string[], isJson: boolean, storagePath?: string): Promise<void> {
  const id = args[0];
  if (!id) {
    console.error('Error: Checkpoint ID is required');
    process.exit(1);
  }

  const mgr = getManager(storagePath);
  const checkpoint = await mgr.get(id);

  if (!checkpoint) {
    if (isJson) {
      console.log(JSON.stringify({ success: false, error: 'Checkpoint not found' }));
    } else {
      console.error(`Checkpoint ${id} not found`);
    }
    process.exit(1);
  }

  if (isJson) {
    console.log(JSON.stringify({ success: true, checkpoint }, null, 2));
  } else {
    console.log(`Checkpoint: ${checkpoint.id}`);
    console.log(`  Name: ${checkpoint.name}`);
    console.log(`  Created: ${checkpoint.timestamp.toISOString()}`);
    console.log(`  State: ${JSON.stringify(checkpoint.state, null, 2)}`);
  }
}

async function handleRestore(args: string[], isJson: boolean, storagePath?: string): Promise<void> {
  const id = args[0];
  const mgr = getManager(storagePath);
  
  let checkpoint;
  if (id) {
    checkpoint = await mgr.restore(id);
  } else {
    checkpoint = await mgr.restoreLatest();
  }

  if (!checkpoint) {
    if (isJson) {
      console.log(JSON.stringify({ success: false, error: 'No checkpoint to restore' }));
    } else {
      console.error('No checkpoint to restore');
    }
    process.exit(1);
  }

  if (isJson) {
    console.log(JSON.stringify({ success: true, restored: checkpoint }, null, 2));
  } else {
    console.log(`✓ Restored checkpoint: ${checkpoint.id}`);
    console.log(`  Name: ${checkpoint.name}`);
    console.log(`  State keys: ${Object.keys(checkpoint.state).join(', ') || 'none'}`);
  }
}

async function handleDelete(args: string[], isJson: boolean, storagePath?: string): Promise<void> {
  const id = args[0];
  if (!id) {
    console.error('Error: Checkpoint ID is required');
    process.exit(1);
  }

  const mgr = getManager(storagePath);
  await mgr.delete(id);

  if (isJson) {
    console.log(JSON.stringify({ success: true, deleted: id }));
  } else {
    console.log(`✓ Checkpoint ${id} deleted`);
  }
}

async function handleExport(args: string[], isJson: boolean, storagePath?: string): Promise<void> {
  const id = args[0];
  if (!id) {
    console.error('Error: Checkpoint ID is required');
    process.exit(1);
  }

  const mgr = getManager(storagePath);
  const exported = await mgr.export(id);

  if (!exported) {
    console.error(`Checkpoint ${id} not found`);
    process.exit(1);
  }

  console.log(exported);
}

async function handleImport(args: string[], isJson: boolean, storagePath?: string): Promise<void> {
  const jsonData = args[0];
  if (!jsonData) {
    console.error('Error: JSON data is required');
    process.exit(1);
  }

  const mgr = getManager(storagePath);
  const checkpoint = await mgr.import(jsonData);

  if (isJson) {
    console.log(JSON.stringify({ success: true, imported: checkpoint }, null, 2));
  } else {
    console.log(`✓ Checkpoint imported: ${checkpoint.id}`);
  }
}

function showHelp(isJson: boolean): void {
  const help = {
    command: 'checkpoints',
    description: 'Session state checkpointing and recovery',
    subcommands: {
      create: 'Create a new checkpoint',
      list: 'List all checkpoints',
      get: 'Get checkpoint details',
      restore: 'Restore from a checkpoint',
      delete: 'Delete a checkpoint',
      export: 'Export checkpoint as JSON',
      import: 'Import checkpoint from JSON'
    },
    flags: {
      '--storage': 'Path to checkpoint storage directory',
      '--state': 'JSON state to save with checkpoint',
      '--session': 'Session ID to associate',
      '--metadata': 'JSON metadata',
      '--json': 'Output in JSON format'
    },
    examples: [
      'praisonai-ts checkpoints create my-checkpoint',
      'praisonai-ts checkpoints create --state \'{"key": "value"}\'',
      'praisonai-ts checkpoints list',
      'praisonai-ts checkpoints restore <id>',
      'praisonai-ts checkpoints restore  # restores latest',
      'praisonai-ts checkpoints export <id> > checkpoint.json',
      'praisonai-ts checkpoints import \'{"name": "imported"}\'',
      'praisonai-ts checkpoints delete <id>'
    ]
  };

  if (isJson) {
    console.log(JSON.stringify(help, null, 2));
  } else {
    console.log('Checkpoints - Session state checkpointing\n');
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
