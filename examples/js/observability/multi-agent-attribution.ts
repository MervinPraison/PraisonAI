/**
 * Multi-Agent Attribution Example
 * 
 * Demonstrates tracking agent_id, run_id, and trace_id across
 * multi-agent workflows for proper attribution.
 */

import { Agent, Agents, MemoryObservabilityAdapter, setObservabilityAdapter } from 'praisonai';

async function main() {
  // Create memory adapter
  const obs = new MemoryObservabilityAdapter();
  setObservabilityAdapter(obs);

  // Create agents
  const researcher = new Agent({
    name: 'Researcher',
    instructions: 'Research topics and gather information.'
  });

  const writer = new Agent({
    name: 'Writer',
    instructions: 'Write clear summaries based on research.'
  });

  // Create multi-agent workflow
  const agents = new Agents({
    agents: [researcher, writer],
    tasks: [
      { agent: researcher, description: 'Research: {topic}' },
      { agent: writer, description: 'Summarize the research findings' }
    ]
  });

  console.log('Running multi-agent workflow with attribution...\n');

  await agents.start({ topic: 'TypeScript best practices' });

  // View traces with attribution
  const traces = obs.getAllTraces();
  
  console.log('\n=== Attribution Report ===');
  for (const trace of traces) {
    console.log(`\nTrace ID: ${trace.id}`);
    console.log(`  Name: ${trace.name}`);
    
    if (trace.attribution) {
      console.log(`  Agent ID: ${trace.attribution.agentId || 'N/A'}`);
      console.log(`  Run ID: ${trace.attribution.runId || 'N/A'}`);
      console.log(`  Session ID: ${trace.attribution.sessionId || 'N/A'}`);
    }
    
    console.log(`  Spans: ${trace.spans.length}`);
    for (const span of trace.spans) {
      console.log(`    - [${span.kind}] ${span.name}`);
    }
  }
}

main().catch(console.error);
