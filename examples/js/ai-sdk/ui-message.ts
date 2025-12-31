/**
 * UI Message Example (AI SDK v6 Parity)
 * 
 * Demonstrates UIMessage protocol for Next.js/React integration.
 * 
 * Run: npx ts-node ui-message.ts
 * Required: OPENAI_API_KEY
 */

import { 
  createTextMessage,
  createSystemMessage,
  convertToModelMessages,
  convertToUIMessages,
  validateUIMessages,
  hasPendingApprovals,
  type UIMessage,
} from '../../../src/praisonai-ts/src';

async function main() {
  console.log('=== UI Message Example ===\n');

  // Create UI messages
  const messages: UIMessage[] = [
    createSystemMessage('You are a helpful assistant.'),
    createTextMessage('user', 'What is the capital of France?'),
    createTextMessage('assistant', 'The capital of France is Paris.'),
    createTextMessage('user', 'What is its population?'),
  ];

  console.log('1. Created UI Messages:');
  messages.forEach((msg, i) => {
    const text = msg.parts.find(p => p.type === 'text');
    console.log(`   [${i}] ${msg.role}: ${text ? (text as any).text.substring(0, 50) : '...'}`);
  });

  // Validate messages
  console.log('\n2. Validating messages:');
  const isValid = validateUIMessages(messages);
  console.log(`   Valid: ${isValid}`);

  // Convert to model messages (for AI SDK)
  console.log('\n3. Converting to Model Messages:');
  const modelMessages = await convertToModelMessages(messages);
  modelMessages.forEach((msg, i) => {
    const content = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content);
    console.log(`   [${i}] ${msg.role}: ${content.substring(0, 50)}...`);
  });

  // Check for pending approvals
  console.log('\n4. Checking for pending approvals:');
  const hasPending = messages.some(m => hasPendingApprovals(m));
  console.log(`   Has pending approvals: ${hasPending}`);

  // Convert model messages back to UI messages
  console.log('\n5. Round-trip conversion:');
  const uiMessages = convertToUIMessages(modelMessages);
  console.log(`   Converted ${uiMessages.length} messages back to UI format`);

  console.log('\n✅ UI Message demo completed!');
}

main().catch(console.error);
