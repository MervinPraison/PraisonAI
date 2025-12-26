/**
 * CLI command: n8n
 * N8N workflow integration
 */

import { N8NIntegration, createN8NIntegration } from '../features/n8n-integration';

export async function execute(args: string[], options: Record<string, unknown>): Promise<void> {
  const subcommand = args[0] || 'help';
  const isJson = Boolean(options.output === 'json' || options.json);

  switch (subcommand) {
    case 'trigger':
      await handleTrigger(args.slice(1), options, isJson);
      break;
    case 'export':
      await handleExport(args.slice(1), options, isJson);
      break;
    case 'help':
    default:
      showHelp(isJson);
  }
}

async function handleTrigger(args: string[], options: Record<string, unknown>, isJson: boolean): Promise<void> {
  const webhookId = args[0];
  const payloadStr = args[1] || '{}';

  if (!webhookId) {
    console.error('Error: Webhook ID is required');
    process.exit(1);
  }

  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(payloadStr);
  } catch {
    payload = { data: payloadStr };
  }

  const baseUrl = options['base-url'] as string | undefined;
  const apiKey = options['api-key'] as string | undefined;

  const n8n = createN8NIntegration({ baseUrl, apiKey });
  const result = await n8n.triggerWebhook(webhookId, payload);

  if (isJson) {
    console.log(JSON.stringify(result, null, 2));
  } else {
    if (result.success) {
      console.log(`✓ Webhook triggered: ${webhookId}`);
      if (result.response) {
        console.log('Response:', JSON.stringify(result.response, null, 2));
      }
    } else {
      console.error(`✗ Webhook failed: ${result.error}`);
      process.exit(1);
    }
  }
}

async function handleExport(args: string[], options: Record<string, unknown>, isJson: boolean): Promise<void> {
  const name = args[0] || 'workflow';
  const stepsStr = options.steps as string | undefined;

  let steps: Array<{ name: string; type: 'agent' | 'tool' | 'condition' }> = [];
  
  if (stepsStr) {
    try {
      steps = JSON.parse(stepsStr);
    } catch {
      // Parse simple format: "step1:agent,step2:tool"
      steps = stepsStr.split(',').map(s => {
        const [stepName, type] = s.split(':');
        return { name: stepName, type: (type || 'agent') as 'agent' | 'tool' | 'condition' };
      });
    }
  } else {
    // Default example workflow
    steps = [
      { name: 'Process Input', type: 'agent' },
      { name: 'Validate', type: 'condition' },
      { name: 'Execute', type: 'tool' }
    ];
  }

  const n8n = createN8NIntegration();
  const workflow = n8n.exportWorkflowJSON(name, steps);

  if (isJson || !options.pretty) {
    console.log(workflow);
  } else {
    console.log(`N8N Workflow: ${name}\n`);
    console.log('Steps:');
    for (const step of steps) {
      console.log(`  - ${step.name} (${step.type})`);
    }
    console.log('\nExported workflow JSON:');
    console.log(workflow);
  }
}

function showHelp(isJson: boolean): void {
  const help = {
    command: 'n8n',
    description: 'N8N workflow integration',
    subcommands: {
      trigger: 'Trigger an N8N webhook',
      export: 'Export workflow to N8N format'
    },
    flags: {
      '--base-url': 'N8N base URL (default: http://localhost:5678)',
      '--api-key': 'N8N API key',
      '--steps': 'Workflow steps as JSON or "name:type,name:type"',
      '--pretty': 'Pretty print export',
      '--json': 'Output in JSON format'
    },
    examples: [
      'praisonai-ts n8n trigger my-webhook \'{"data": "test"}\'',
      'praisonai-ts n8n trigger webhook-id --base-url https://n8n.example.com',
      'praisonai-ts n8n export my-workflow',
      'praisonai-ts n8n export workflow --steps "Process:agent,Validate:condition"'
    ]
  };

  if (isJson) {
    console.log(JSON.stringify(help, null, 2));
  } else {
    console.log('N8N - Workflow integration\n');
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
