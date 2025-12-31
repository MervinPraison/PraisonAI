/**
 * Basic Tracing Example
 * 
 * Demonstrates basic observability with the built-in memory adapter.
 * No external API keys required.
 */

import { Agent, MemoryObservabilityAdapter, setObservabilityAdapter } from 'praisonai';

async function main() {
  // Create memory adapter (stores traces in memory)
  const obs = new MemoryObservabilityAdapter();
  setObservabilityAdapter(obs);

  // Create agent with observability enabled
  const agent = new Agent({
    name: 'TracedAgent',
    instructions: 'You are a helpful assistant. Answer questions concisely.'
  });

  console.log('Running agent with tracing...\n');

  // Run some interactions
  await agent.chat('What is 2 + 2?');
  await agent.chat('What is the capital of France?');

  // View traces
  const traces = obs.getAllTraces();
  
  console.log('\n=== Trace Summary ===');
  console.log(`Total traces: ${traces.length}`);
  
  for (const trace of traces) {
    console.log(`\nTrace: ${trace.name}`);
    console.log(`  Status: ${trace.status}`);
    console.log(`  Spans: ${trace.spans.length}`);
    
    for (const span of trace.spans) {
      const duration = span.endTime ? span.endTime - span.startTime : 'running';
      console.log(`    - ${span.kind}: ${span.name} (${duration}ms)`);
    }
  }
}

main().catch(console.error);
