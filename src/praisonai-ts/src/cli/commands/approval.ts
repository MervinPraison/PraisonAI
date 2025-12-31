/**
 * Approval command - Tool approval management for AI SDK v6 parity
 */

import { 
  getApprovalManager, 
  ApprovalManager,
  createCLIApprovalPrompt 
} from '../../ai/tool-approval';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface ApprovalOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  timeout?: number;
}

export async function execute(args: string[], options: ApprovalOptions): Promise<void> {
  const action = args[0] || 'status';
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    switch (action) {
      case 'status':
        await showStatus(outputFormat);
        break;
      case 'pending':
        await showPending(outputFormat);
        break;
      case 'approve':
        await approveRequest(args[1], outputFormat);
        break;
      case 'deny':
        await denyRequest(args[1], outputFormat);
        break;
      case 'cancel':
        await cancelRequest(args[1], outputFormat);
        break;
      case 'cancel-all':
        await cancelAll(outputFormat);
        break;
      case 'auto-approve':
        await addAutoApprove(args.slice(1), outputFormat);
        break;
      case 'auto-deny':
        await addAutoDeny(args.slice(1), outputFormat);
        break;
      case 'interactive':
        await startInteractive(options);
        break;
      case 'help':
      default:
        await showHelp(outputFormat);
        break;
    }
  } catch (error) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, error instanceof Error ? error.message : String(error)));
    } else {
      await pretty.error(error instanceof Error ? error.message : String(error));
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }
}

async function showStatus(outputFormat: string): Promise<void> {
  const manager = getApprovalManager();
  const pending = manager.getPendingRequests();
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      pendingCount: pending.length,
      pending: pending.map(r => ({
        requestId: r.requestId,
        toolName: r.toolName,
        timestamp: r.timestamp,
      })),
    }));
  } else {
    await pretty.heading('Approval Status');
    await pretty.plain(`Pending requests: ${pending.length}`);
    if (pending.length > 0) {
      await pretty.plain('\nPending:');
      for (const req of pending) {
        await pretty.plain(`  - ${req.toolName} (${req.requestId})`);
      }
    }
  }
}

async function showPending(outputFormat: string): Promise<void> {
  const manager = getApprovalManager();
  const pending = manager.getPendingRequests();
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({ pending }));
  } else {
    if (pending.length === 0) {
      await pretty.plain('No pending approval requests');
      return;
    }
    
    await pretty.heading('Pending Approval Requests');
    for (const req of pending) {
      await pretty.plain(`\n🔐 ${req.toolName}`);
      await pretty.plain(`   ID: ${req.requestId}`);
      await pretty.plain(`   Input: ${JSON.stringify(req.input)}`);
      await pretty.plain(`   Time: ${new Date(req.timestamp).toISOString()}`);
      if (req.reason) {
        await pretty.plain(`   Reason: ${req.reason}`);
      }
    }
  }
}

async function approveRequest(requestId: string, outputFormat: string): Promise<void> {
  if (!requestId) {
    throw new Error('Request ID required. Usage: praisonai approval approve <requestId>');
  }
  
  const manager = getApprovalManager();
  manager.respond({
    requestId,
    approved: true,
    timestamp: Date.now(),
  });
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({ requestId, approved: true }));
  } else {
    await pretty.success(`Approved request: ${requestId}`);
  }
}

async function denyRequest(requestId: string, outputFormat: string): Promise<void> {
  if (!requestId) {
    throw new Error('Request ID required. Usage: praisonai approval deny <requestId>');
  }
  
  const manager = getApprovalManager();
  manager.respond({
    requestId,
    approved: false,
    timestamp: Date.now(),
  });
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({ requestId, approved: false }));
  } else {
    await pretty.success(`Denied request: ${requestId}`);
  }
}

async function cancelRequest(requestId: string, outputFormat: string): Promise<void> {
  if (!requestId) {
    throw new Error('Request ID required. Usage: praisonai approval cancel <requestId>');
  }
  
  const manager = getApprovalManager();
  manager.cancel(requestId);
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({ requestId, cancelled: true }));
  } else {
    await pretty.success(`Cancelled request: ${requestId}`);
  }
}

async function cancelAll(outputFormat: string): Promise<void> {
  const manager = getApprovalManager();
  const pending = manager.getPendingRequests();
  const count = pending.length;
  
  manager.cancelAll();
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({ cancelled: count }));
  } else {
    await pretty.success(`Cancelled ${count} pending requests`);
  }
}

async function addAutoApprove(args: string[], outputFormat: string): Promise<void> {
  const toolName = args[0];
  if (!toolName) {
    throw new Error('Tool name required. Usage: praisonai approval auto-approve <toolName>');
  }
  
  const manager = getApprovalManager();
  manager.addAutoApprove(toolName);
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({ toolName, autoApprove: true }));
  } else {
    await pretty.success(`Added auto-approve for: ${toolName}`);
  }
}

async function addAutoDeny(args: string[], outputFormat: string): Promise<void> {
  const toolName = args[0];
  if (!toolName) {
    throw new Error('Tool name required. Usage: praisonai approval auto-deny <toolName>');
  }
  
  const manager = getApprovalManager();
  manager.addAutoDeny(toolName);
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({ toolName, autoDeny: true }));
  } else {
    await pretty.success(`Added auto-deny for: ${toolName}`);
  }
}

async function startInteractive(options: ApprovalOptions): Promise<void> {
  await pretty.heading('Interactive Approval Mode');
  await pretty.plain('Waiting for approval requests... (Ctrl+C to exit)\n');
  
  const manager = getApprovalManager();
  const handler = createCLIApprovalPrompt();
  
  manager.onApprovalRequest(handler);
  
  // Keep process alive
  await new Promise(() => {});
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'approval',
    description: 'Manage tool approval requests (AI SDK v6 parity)',
    subcommands: [
      { name: 'status', description: 'Show approval status' },
      { name: 'pending', description: 'List pending approval requests' },
      { name: 'approve <id>', description: 'Approve a pending request' },
      { name: 'deny <id>', description: 'Deny a pending request' },
      { name: 'cancel <id>', description: 'Cancel a pending request' },
      { name: 'cancel-all', description: 'Cancel all pending requests' },
      { name: 'auto-approve <tool>', description: 'Auto-approve a tool' },
      { name: 'auto-deny <tool>', description: 'Auto-deny a tool' },
      { name: 'interactive', description: 'Start interactive approval mode' },
    ],
    examples: [
      'praisonai approval status',
      'praisonai approval pending',
      'praisonai approval approve abc123',
      'praisonai approval auto-approve readFile',
      'praisonai approval interactive',
    ],
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Approval Command');
    await pretty.plain('Manage tool approval requests for safe AI agent execution.\n');
    
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(20)} ${cmd.description}`);
    }
    
    await pretty.plain('\nExamples:');
    for (const ex of help.examples) {
      await pretty.plain(`  ${ex}`);
    }
  }
}
