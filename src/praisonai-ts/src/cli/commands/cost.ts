/**
 * CLI command: cost
 * Token usage and cost tracking
 */

import { CostTracker, createCostTracker, MODEL_PRICING, formatCost } from '../features/cost-tracker';

let tracker: CostTracker | null = null;

function getTracker(): CostTracker {
  if (!tracker) {
    tracker = createCostTracker();
  }
  return tracker;
}

export async function execute(args: string[], options: Record<string, unknown>): Promise<void> {
  const subcommand = args[0] || 'help';
  const isJson = Boolean(options.output === 'json' || options.json);

  switch (subcommand) {
    case 'summary':
      await handleSummary(isJson);
      break;
    case 'add':
      await handleAdd(args.slice(1), options, isJson);
      break;
    case 'reset':
      await handleReset(isJson);
      break;
    case 'pricing':
      await handlePricing(args.slice(1), isJson);
      break;
    case 'help':
    default:
      showHelp(isJson);
  }
}

async function handleSummary(isJson: boolean): Promise<void> {
  const t = getTracker();
  const stats = t.getStats();
  const breakdown = t.getBreakdownByModel();

  if (isJson) {
    console.log(JSON.stringify({ success: true, stats, breakdown }, null, 2));
  } else {
    console.log(t.getSummary());
    
    if (Object.keys(breakdown).length > 0) {
      console.log('\nBreakdown by model:');
      for (const [model, data] of Object.entries(breakdown)) {
        console.log(`  ${model}: ${data.tokens} tokens, ${formatCost(data.cost)}, ${data.requests} requests`);
      }
    }
  }
}

async function handleAdd(args: string[], options: Record<string, unknown>, isJson: boolean): Promise<void> {
  const model = args[0] || 'gpt-4o-mini';
  const inputTokens = parseInt(args[1] || '0');
  const outputTokens = parseInt(args[2] || '0');

  if (isNaN(inputTokens) || isNaN(outputTokens)) {
    console.error('Error: Invalid token counts');
    process.exit(1);
  }

  const t = getTracker();
  const request = t.addUsage(model, inputTokens, outputTokens);

  if (isJson) {
    console.log(JSON.stringify({ success: true, request }, null, 2));
  } else {
    console.log(`✓ Added usage: ${model}`);
    console.log(`  Input: ${inputTokens} tokens`);
    console.log(`  Output: ${outputTokens} tokens`);
    console.log(`  Cost: ${formatCost(request.cost)}`);
  }
}

async function handleReset(isJson: boolean): Promise<void> {
  const t = getTracker();
  t.reset();

  if (isJson) {
    console.log(JSON.stringify({ success: true, message: 'Cost tracker reset' }));
  } else {
    console.log('✓ Cost tracker reset');
  }
}

async function handlePricing(args: string[], isJson: boolean): Promise<void> {
  const model = args[0];

  if (model) {
    const pricing = MODEL_PRICING[model] || MODEL_PRICING['default'];
    if (isJson) {
      console.log(JSON.stringify({ success: true, model, pricing }, null, 2));
    } else {
      console.log(`Pricing for ${model}:`);
      console.log(`  Input: $${pricing.inputCostPer1k}/1K tokens`);
      console.log(`  Output: $${pricing.outputCostPer1k}/1K tokens`);
    }
  } else {
    if (isJson) {
      console.log(JSON.stringify({ success: true, pricing: MODEL_PRICING }, null, 2));
    } else {
      console.log('Model Pricing (per 1K tokens):\n');
      for (const [name, pricing] of Object.entries(MODEL_PRICING)) {
        if (name === 'default') continue;
        console.log(`  ${name.padEnd(30)} in: $${pricing.inputCostPer1k.toFixed(5)}  out: $${pricing.outputCostPer1k.toFixed(5)}`);
      }
    }
  }
}

function showHelp(isJson: boolean): void {
  const help = {
    command: 'cost',
    description: 'Token usage and cost tracking',
    subcommands: {
      summary: 'Show cost summary',
      add: 'Add token usage',
      reset: 'Reset cost tracker',
      pricing: 'Show model pricing'
    },
    flags: {
      '--json': 'Output in JSON format'
    },
    examples: [
      'praisonai-ts cost summary',
      'praisonai-ts cost add gpt-4o 1000 500',
      'praisonai-ts cost pricing',
      'praisonai-ts cost pricing gpt-4o',
      'praisonai-ts cost reset'
    ]
  };

  if (isJson) {
    console.log(JSON.stringify(help, null, 2));
  } else {
    console.log('Cost - Token usage and cost tracking\n');
    console.log('Subcommands:');
    for (const [cmd, desc] of Object.entries(help.subcommands)) {
      console.log(`  ${cmd.padEnd(12)} ${desc}`);
    }
    console.log('\nExamples:');
    for (const ex of help.examples) {
      console.log(`  ${ex}`);
    }
  }
}
