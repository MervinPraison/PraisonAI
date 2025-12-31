/**
 * Telemetry Example (AI SDK v6 Parity)
 * 
 * Demonstrates telemetry and tracing with optional OpenTelemetry integration.
 * 
 * Run: npx ts-node telemetry.ts
 * Required: OPENAI_API_KEY
 */

import { 
  configureTelemetry,
  isTelemetryEnabled,
  createAISpan,
  recordEvent,
  getEvents,
  clearEvents,
  Agent,
} from '../../../src/praisonai-ts/src';

async function main() {
  console.log('=== Telemetry Example ===\n');

  // Configure telemetry
  configureTelemetry({
    isEnabled: true,
    functionId: 'telemetry-demo',
    metadata: {
      version: '1.0.0',
      environment: 'development',
    },
  });

  console.log('1. Telemetry Status:');
  console.log(`   Enabled: ${isTelemetryEnabled()}`);

  // Create a span for an operation
  console.log('\n2. Creating AI Span:');
  const span = createAISpan('generateText', {
    model: 'gpt-4o-mini',
    provider: 'openai',
  });

  try {
    // Simulate AI operation
    console.log('   Performing AI operation...');
    await new Promise(resolve => setTimeout(resolve, 100));
    
    span.setAttribute('tokens', 150);
    span.setStatus({ code: 'ok' });
    console.log('   Span completed successfully');
  } catch (error: any) {
    span.recordException(error);
    span.setStatus({ code: 'error', message: error.message });
  } finally {
    span.end();
  }

  // Record custom events
  console.log('\n3. Recording Events:');
  recordEvent('agent.started', { agentName: 'demo-agent' });
  recordEvent('tool.called', { toolName: 'search', duration: 250 });
  recordEvent('agent.completed', { success: true });

  const events = getEvents();
  console.log(`   Recorded ${events.length} events:`);
  events.forEach(e => {
    console.log(`   - ${e.name}: ${JSON.stringify(e.attributes)}`);
  });

  // Clear events
  console.log('\n4. Clearing Events:');
  clearEvents();
  console.log(`   Events after clear: ${getEvents().length}`);

  console.log('\n✅ Telemetry demo completed!');
}

main().catch(console.error);
