/**
 * Observability Example
 * Demonstrates tracing and monitoring
 */

import { MemoryObservabilityAdapter, ConsoleObservabilityAdapter } from 'praisonai';

async function main() {
  // Memory adapter - stores traces in memory
  const memoryAdapter = new MemoryObservabilityAdapter();

  // Start a trace
  const trace = memoryAdapter.startTrace('agent-execution');
  console.log('Trace started:', trace.traceId);

  // Create spans for different operations
  const llmSpan = trace.startSpan('llm-call', 'llm');
  llmSpan.setAttribute('model', 'gpt-4o-mini');
  llmSpan.setAttribute('tokens', 150);
  await new Promise(r => setTimeout(r, 100)); // Simulate work
  llmSpan.end();

  const toolSpan = trace.startSpan('tool-execution', 'tool');
  toolSpan.setAttribute('tool', 'calculator');
  toolSpan.addEvent('tool-started', { input: '2+2' });
  await new Promise(r => setTimeout(r, 50)); // Simulate work
  toolSpan.addEvent('tool-completed', { output: '4' });
  toolSpan.end();

  // End trace
  trace.end();

  // Retrieve trace data
  const traceData = memoryAdapter.getTrace(trace.traceId);
  console.log('\n=== Trace Data ===');
  console.log('Trace ID:', traceData?.traceId);
  console.log('Spans:', traceData?.spans.length);
  console.log('Duration:', traceData?.endTime! - traceData?.startTime!, 'ms');

  // Show spans
  console.log('\n=== Spans ===');
  traceData?.spans.forEach(span => {
    console.log(`- ${span.name} (${span.kind}): ${span.endTime! - span.startTime}ms`);
    if (span.attributes) {
      Object.entries(span.attributes).forEach(([k, v]) => {
        console.log(`    ${k}: ${v}`);
      });
    }
  });

  // Console adapter example
  console.log('\n=== Console Adapter ===');
  const consoleAdapter = new ConsoleObservabilityAdapter();
  const trace2 = consoleAdapter.startTrace('demo-trace');
  const span = trace2.startSpan('demo-span', 'custom');
  span.end();
  trace2.end();
}

main().catch(console.error);
