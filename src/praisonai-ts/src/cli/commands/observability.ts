/**
 * Observability command - Monitoring and tracing
 * 
 * Supports 14+ observability integrations:
 * - list: List all available observability tools
 * - doctor: Check environment variables for selected tool
 * - test: Run a test trace to verify tool works
 * - info: Show observability feature information
 */

import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';
import {
  OBSERVABILITY_TOOLS,
  listObservabilityTools,
  hasObservabilityToolEnvVar,
  type ObservabilityToolName
} from '../../observability/types';

export interface ObservabilityOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  tool?: string;
}

export async function execute(args: string[], options: ObservabilityOptions): Promise<void> {
  const action = args[0] || 'help';
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    switch (action) {
      case 'list':
      case 'providers':
        await listProvidersCommand(options, outputFormat);
        break;
      case 'doctor':
        await doctorCommand(args[1] || options.tool, options, outputFormat);
        break;
      case 'test':
        await testCommand(args[1] || options.tool, options, outputFormat);
        break;
      case 'info':
        await showInfo(outputFormat);
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

async function showInfo(outputFormat: string): Promise<void> {
  const info = {
    feature: 'Observability',
    description: 'Monitoring, tracing, and logging for agent operations',
    providers: [
      { name: 'ConsoleObservabilityProvider', description: 'Console-based logging' },
      { name: 'MemoryObservabilityProvider', description: 'In-memory trace storage' },
      { name: 'LangfuseObservabilityProvider', description: 'Langfuse integration' }
    ],
    capabilities: [
      'Trace agent executions',
      'Log LLM calls and responses',
      'Track tool invocations',
      'Measure performance metrics',
      'Export traces to external systems'
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(info));
  } else {
    await pretty.heading('Observability');
    await pretty.plain(info.description);
    await pretty.newline();
    await pretty.plain('Providers:');
    for (const p of info.providers) {
      await pretty.plain(`  • ${p.name}: ${p.description}`);
    }
    await pretty.newline();
    await pretty.plain('Capabilities:');
    for (const cap of info.capabilities) {
      await pretty.plain(`  • ${cap}`);
    }
  }
}

/**
 * List all observability tools
 */
async function listProvidersCommand(options: ObservabilityOptions, outputFormat: string): Promise<void> {
  const tools = listObservabilityTools();

  const providers = tools.map(tool => ({
    name: tool.name,
    description: tool.description,
    package: tool.package,
    envKey: tool.envKey,
    hasEnvKey: hasObservabilityToolEnvVar(tool.name),
    delivers: tool.delivers,
    features: tool.features
  }));

  // "Ready" must mean traces will actually arrive, not merely that a key is set.
  // A tool that cannot deliver (e.g. weave) is never ready however its key is set;
  // key-less built-ins are ready because they need no configuration to do their job.
  // This mirrors the same predicate used by the aggregate doctor command below.
  const ready = providers.filter(p => p.hasEnvKey && (p.delivers || !p.envKey));
  const builtIn = providers.filter(p => ['console', 'memory', 'noop'].includes(p.name));
  const external = providers.filter(p => !['console', 'memory', 'noop'].includes(p.name));

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      providers,
      total: providers.length,
      ready: ready.length,
      builtin: builtIn.length,
      external: external.length
    }));
  } else {
    await pretty.heading('Observability Tools');
    await pretty.plain(`\n  Total: ${providers.length} tools (${ready.length} ready)`);

    await pretty.plain('\n  Built-in (no setup required):');
    for (const p of builtIn) {
      await pretty.plain(`    ✅ ${p.name.padEnd(12)} ${p.description}`);
    }

    await pretty.plain('\n  External Integrations:');
    for (const p of external) {
      const status = !p.delivers ? '❌' : (p.hasEnvKey ? '✅' : '⚠️');
      const keyInfo = p.envKey ? ` (${p.envKey})` : '';
      const note = p.delivers ? '' : '  [no delivery - in-memory only]';
      await pretty.plain(`    ${status} ${p.name.padEnd(12)} ${p.description}${options.verbose ? keyInfo : ''}${note}`);
    }

    await pretty.newline();
    await pretty.info('Run "observability doctor <tool>" for setup instructions');
  }
}

/**
 * Doctor command - Check environment for a tool
 */
async function doctorCommand(toolName: string | undefined, options: ObservabilityOptions, outputFormat: string): Promise<void> {
  if (!toolName) {
    // Check all tools
    const tools = listObservabilityTools();
    const results = tools.map(tool => ({
      name: tool.name,
      envKey: tool.envKey,
      hasKey: hasObservabilityToolEnvVar(tool.name),
      delivers: tool.delivers,
      package: tool.package
    }));

    // "Ready" must mean traces will actually arrive, not merely that a key is set.
    const ready = results.filter(r => r.hasKey && (r.delivers || !r.envKey));

    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        total: results.length,
        ready: ready.length,
        tools: results
      }));
    } else {
      await pretty.heading('Observability Environment Check');
      await pretty.plain(`\n  Total Tools: ${results.length}`);
      await pretty.plain(`  Ready: ${ready.length} ✅`);

      if (ready.length > 0) {
        await pretty.plain('\n  Ready Tools:');
        for (const t of ready) {
          await pretty.plain(`    ✅ ${t.name}`);
        }
      }

      await pretty.newline();
      await pretty.info('Run "observability doctor <tool>" for specific tool setup');
    }
    return;
  }

  // Check specific tool
  const tool = OBSERVABILITY_TOOLS[toolName.toLowerCase() as ObservabilityToolName];

  if (!tool) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.INVALID_ARGS, `Unknown tool: ${toolName}`));
    } else {
      await pretty.error(`Unknown tool: ${toolName}`);
      await pretty.info(`Available: ${Object.keys(OBSERVABILITY_TOOLS).join(', ')}`);
    }
    return;
  }

  const hasKey = hasObservabilityToolEnvVar(tool.name);
  const keyValue = tool.envKey ? process.env[tool.envKey] : null;
  const maskedKey = keyValue ? `${keyValue.slice(0, 4)}...${keyValue.slice(-4)}` : 'not set';

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      tool: tool.name,
      env_key: tool.envKey,
      has_key: hasKey,
      key_preview: hasKey ? maskedKey : null,
      package: tool.package,
      description: tool.description,
      features: tool.features,
      delivers: tool.delivers,
      status: !tool.delivers && tool.envKey
        ? 'not_implemented'
        : (hasKey || !tool.envKey ? 'ready' : 'missing_key')
    }));
  } else {
    await pretty.heading(`Observability Doctor: ${tool.name}`);
    await pretty.plain(`  Description: ${tool.description}`);
    if (!tool.delivers && tool.envKey) {
      await pretty.plain(`  Delivery: ❌ NOT IMPLEMENTED - traces are kept in memory and never sent to ${tool.name}.`);
      await pretty.plain(`            Setting ${tool.envKey} will not change this.`);
    } else if (tool.delivers) {
      await pretty.plain(`  Delivery: ✅ Implemented`);
    }
    if (tool.package) {
      await pretty.plain(`  Package: ${tool.package}`);
    }
    if (tool.envKey) {
      await pretty.plain(`  Environment Variable: ${tool.envKey}`);
      await pretty.plain(`  Status: ${!tool.delivers ? '❌ Not Implemented' : (hasKey ? '✅ Ready' : '❌ Missing API Key')}`);
      if (hasKey) {
        await pretty.dim(`  Key Preview: ${maskedKey}`);
      } else {
        await pretty.newline();
        await pretty.info(`Set the API key with:`);
        await pretty.dim(`  export ${tool.envKey}=your-api-key`);
      }
    } else {
      await pretty.plain(`  Status: ✅ Ready (no API key required)`);
    }

    await pretty.newline();
    await pretty.plain('  Features:');
    const f = tool.features;
    await pretty.plain(`    Traces: ${f.traces ? '✅' : '❌'}  Spans: ${f.spans ? '✅' : '❌'}  Events: ${f.events ? '✅' : '❌'}`);
    await pretty.plain(`    Errors: ${f.errors ? '✅' : '❌'}  Metrics: ${f.metrics ? '✅' : '❌'}  Export: ${f.export ? '✅' : '❌'}`);
  }
}

/**
 * Test command - Run a test trace
 */
async function testCommand(toolName: string | undefined, options: ObservabilityOptions, outputFormat: string): Promise<void> {
  const tool = toolName?.toLowerCase() || 'memory';

  if (!OBSERVABILITY_TOOLS[tool as ObservabilityToolName]) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.INVALID_ARGS, `Unknown tool: ${toolName}`));
    } else {
      await pretty.error(`Unknown tool: ${toolName}`);
    }
    return;
  }

  if (outputFormat !== 'json') {
    await pretty.info(`Testing ${tool} observability...`);
  }

  const startTime = Date.now();

  try {
    const { createObservabilityAdapter } = await import('../../observability/adapters');
    const adapter = await createObservabilityAdapter(tool as ObservabilityToolName);

    // Run a test trace
    const trace = adapter.startTrace('test-trace', { test: true });
    const span = adapter.startSpan(trace.traceId, 'test-span', 'custom');
    adapter.addEvent(span.spanId, 'test-event', { message: 'hello' });
    adapter.endSpan(span.spanId, 'completed');
    adapter.endTrace(trace.traceId, 'completed');
    await adapter.flush();

    const latency = Date.now() - startTime;
    const info = OBSERVABILITY_TOOLS[tool as ObservabilityToolName];

    // "delivered" means the trace reached an external backend. That requires a
    // delivery implementation (registry `delivers`) AND a live transport
    // (`isEnabled`). The in-process memory adapter reports isEnabled === true,
    // but it sends nothing anywhere, so isEnabled alone is not proof of delivery.
    const delivered = info.delivers === true && adapter.isEnabled;

    // A built-in local recorder (console/memory) has no envKey and never
    // delivers externally, yet it does exactly what it claims: record locally.
    // That is a genuine pass, distinct from a non-delivering external
    // integration that silently drops the trace it advertised it would send.
    const isLocalRecorder = !info.envKey && !info.delivers && adapter.isEnabled;

    if (outputFormat === 'json' && delivered) {
      outputJson(formatSuccess({
        tool,
        status: 'delivered',
        delivered: true,
        latency_ms: latency,
        trace_id: trace.traceId
      }));
    } else if (outputFormat === 'json' && isLocalRecorder) {
      // success:true, but delivered:false — the trace was recorded in this
      // process and never left it. A CI script must be able to tell local
      // recording apart from real delivery via the `delivered` field.
      outputJson(formatSuccess({
        tool,
        status: 'recorded',
        delivered: false,
        latency_ms: latency,
        trace_id: trace.traceId
      }));
    } else if (outputFormat === 'json') {
      // success:false matters here. A CI script doing `... --json | jq .success`
      // must not be told the tool works when nothing was delivered.
      outputJson(formatError(
        ERROR_CODES.RUNTIME_ERROR,
        `The "${tool}" adapter recorded the trace in memory but did not send it anywhere. This integration has no delivery implementation.`,
        { tool, status: 'not_delivered', delivered: false, latency_ms: latency, trace_id: trace.traceId }
      ));
    } else if (delivered) {
      await pretty.plain(`\n  ✅ Test Passed`);
      await pretty.plain(`  Tool: ${tool}`);
      await pretty.plain(`  Delivered: ✅ sent to ${tool}`);
      await pretty.plain(`  Latency: ${latency}ms`);
      await pretty.dim(`  Trace ID: ${trace.traceId}`);
    } else if (isLocalRecorder) {
      await pretty.plain(`\n  ✅ Test Passed`);
      await pretty.plain(`  Tool: ${tool}`);
      await pretty.plain(`  Recorded in memory (built-in). Nothing is sent to an external backend.`);
      await pretty.plain(`  Latency: ${latency}ms`);
      await pretty.dim(`  Trace ID: ${trace.traceId}`);
    } else {
      await pretty.plain(`\n  ⚠️  Not Delivered`);
      await pretty.plain(`  Tool: ${tool}`);
      await pretty.plain(`  The trace was recorded in memory but NOT sent to ${tool}.`);
      await pretty.plain(`  This integration has no delivery implementation (isEnabled is false).`);
      await pretty.plain(`  Latency: ${latency}ms`);
      await pretty.dim(`  Trace ID: ${trace.traceId}`);
    }
  } catch (error: any) {
    const latency = Date.now() - startTime;
    const errorMessage = error.message || String(error);

    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, errorMessage, {
        tool,
        latency_ms: latency
      }));
    } else {
      await pretty.error(`Test Failed: ${errorMessage}`);
      await pretty.plain(`  Tool: ${tool}`);
      await pretty.plain(`  Latency: ${latency}ms`);
    }
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'observability',
    description: 'Monitoring and tracing for agent operations',
    subcommands: [
      { name: 'list', description: 'List all observability tools' },
      { name: 'doctor [tool]', description: 'Check environment for a tool' },
      { name: 'test [tool]', description: 'Run a test trace' },
      { name: 'info', description: 'Show observability feature information' },
      { name: 'help', description: 'Show this help' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Observability Command');
    await pretty.plain(help.description);
    await pretty.newline();
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(20)} ${cmd.description}`);
    }
    await pretty.newline();
    await pretty.dim('Examples:');
    await pretty.dim('  praisonai-ts observability list');
    await pretty.dim('  praisonai-ts observability doctor langfuse');
    await pretty.dim('  praisonai-ts observability test memory');
  }
}
