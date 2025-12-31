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
    features: tool.features
  }));
  
  const ready = providers.filter(p => p.hasEnvKey);
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
      const status = p.hasEnvKey ? '✅' : '⚠️';
      const keyInfo = p.envKey ? ` (${p.envKey})` : '';
      await pretty.plain(`    ${status} ${p.name.padEnd(12)} ${p.description}${options.verbose ? keyInfo : ''}`);
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
      package: tool.package
    }));
    
    const ready = results.filter(r => r.hasKey);
    
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
      status: hasKey || !tool.envKey ? 'ready' : 'missing_key'
    }));
  } else {
    await pretty.heading(`Observability Doctor: ${tool.name}`);
    await pretty.plain(`  Description: ${tool.description}`);
    if (tool.package) {
      await pretty.plain(`  Package: ${tool.package}`);
    }
    if (tool.envKey) {
      await pretty.plain(`  Environment Variable: ${tool.envKey}`);
      await pretty.plain(`  Status: ${hasKey ? '✅ Ready' : '❌ Missing API Key'}`);
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
    
    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        tool,
        status: 'success',
        latency_ms: latency,
        trace_id: trace.traceId
      }));
    } else {
      await pretty.plain(`\n  ✅ Test Passed`);
      await pretty.plain(`  Tool: ${tool}`);
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
      { name: 'info', description: 'Show observability feature information' },
      { name: 'providers', description: 'List available observability providers' },
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
  }
}
