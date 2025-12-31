/**
 * AI SDK v6 Parity - Basic Usage Examples
 * 
 * This example demonstrates the new AI SDK v6 compatible features in praisonai-ts.
 */

import {
  // Core Agent
  Agent,
  // Tool Approval
  ApprovalManager,
  getApprovalManager,
  withApproval,
  createDangerousPatternChecker,
  // UI Messages
  UIMessage,
  convertToModelMessages,
  createTextMessage,
  toUIMessageStreamResponse,
  // Speech & Transcription
  generateSpeech,
  transcribe,
  // DevTools
  enableDevTools,
  isDevToolsEnabled,
  // Telemetry
  configureTelemetry,
  createAISpan,
  // MCP
  createMCP,
} from '../../src';

// ============================================================================
// Example 1: Tool with Approval
// ============================================================================

async function toolApprovalExample() {
  console.log('\n=== Tool Approval Example ===\n');

  // Create a tool that requires approval
  const deleteFile = withApproval({
    name: 'deleteFile',
    description: 'Delete a file from the filesystem',
    needsApproval: true, // Always require approval
    execute: async (input: { path: string }) => {
      console.log(`Would delete: ${input.path}`);
      return { success: true, path: input.path };
    },
    onDenied: (input) => {
      console.log(`Deletion denied for: ${input.path}`);
      return { success: false, path: input.path };
    },
  });

  // Create a tool with conditional approval
  const runCommand = withApproval({
    name: 'runCommand',
    description: 'Run a shell command',
    needsApproval: createDangerousPatternChecker(), // Only approve dangerous commands
    execute: async (input: { command: string }) => {
      console.log(`Would run: ${input.command}`);
      return { output: 'command output' };
    },
  });

  // Set up approval handler
  const manager = getApprovalManager();
  manager.onApprovalRequest(async (request) => {
    console.log(`\n🔐 Approval requested for: ${request.toolName}`);
    console.log(`   Input: ${JSON.stringify(request.input)}`);
    // Auto-approve for demo
    return true;
  });

  // Test the tools
  try {
    const result1 = await deleteFile({ path: '/tmp/test.txt' });
    console.log('Delete result:', result1);

    const result2 = await runCommand({ command: 'ls -la' });
    console.log('Command result:', result2);
  } catch (error) {
    console.error('Error:', error);
  }
}

// ============================================================================
// Example 2: UI Messages
// ============================================================================

async function uiMessageExample() {
  console.log('\n=== UI Message Example ===\n');

  // Create UI messages
  const messages: UIMessage[] = [
    createTextMessage('user', 'Hello, how are you?'),
    createTextMessage('assistant', 'I am doing well, thank you for asking!'),
  ];

  console.log('UI Messages:', JSON.stringify(messages, null, 2));

  // Convert to model messages
  const modelMessages = await convertToModelMessages(messages);
  console.log('\nModel Messages:', JSON.stringify(modelMessages, null, 2));
}

// ============================================================================
// Example 3: DevTools
// ============================================================================

async function devToolsExample() {
  console.log('\n=== DevTools Example ===\n');

  // Check if DevTools is enabled
  console.log('DevTools enabled:', isDevToolsEnabled());

  // Enable DevTools (in development)
  if (process.env.NODE_ENV === 'development') {
    await enableDevTools({
      port: 3001,
      projectName: 'PraisonAI Demo',
    });
    console.log('DevTools enabled:', isDevToolsEnabled());
  }
}

// ============================================================================
// Example 4: Telemetry
// ============================================================================

async function telemetryExample() {
  console.log('\n=== Telemetry Example ===\n');

  // Configure telemetry
  configureTelemetry({
    isEnabled: true,
    functionId: 'demo-app',
    metadata: {
      version: '1.0.0',
      environment: 'development',
    },
  });

  // Create a span
  const span = createAISpan('generateText', {
    model: 'gpt-4o',
    provider: 'openai',
  });

  try {
    // Simulate some work
    console.log('Performing AI operation...');
    await new Promise(resolve => setTimeout(resolve, 100));
    
    span.setAttribute('tokens', 150);
    span.setStatus({ code: 'ok' });
  } catch (error: any) {
    span.recordException(error);
    span.setStatus({ code: 'error', message: error.message });
  } finally {
    span.end();
  }

  console.log('Telemetry span completed');
}

// ============================================================================
// Example 5: MCP with HTTP Transport
// ============================================================================

async function mcpExample() {
  console.log('\n=== MCP Example ===\n');

  // Note: This requires an MCP server to be running
  console.log('MCP HTTP transport configuration example:');
  console.log(`
const client = await createMCP({
  transport: {
    type: 'http',
    url: 'https://mcp-server.example.com/mcp',
    headers: { Authorization: 'Bearer token' },
  }
});

const tools = await client.tools();
const resources = await client.listResources();
const prompts = await client.listPrompts();
`);
}

// ============================================================================
// Main
// ============================================================================

async function main() {
  console.log('🚀 AI SDK v6 Parity Examples\n');
  console.log('=' .repeat(50));

  await toolApprovalExample();
  await uiMessageExample();
  await devToolsExample();
  await telemetryExample();
  await mcpExample();

  console.log('\n' + '='.repeat(50));
  console.log('✅ All examples completed!');
}

main().catch(console.error);
