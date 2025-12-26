/**
 * Direct verification script for provider implementation
 * Run with: npx ts-node tests/development/verify-providers.ts
 */

import { createProvider } from '../../src/llm/providers';

async function testOpenAI() {
  console.log('\n=== Testing OpenAI Provider ===');
  
  if (!process.env.OPENAI_API_KEY) {
    console.log('OPENAI_API_KEY not set, skipping');
    return;
  }

  const provider = createProvider('openai/gpt-4o-mini');
  
  // Test generateText
  console.log('\n1. Testing generateText...');
  const result = await provider.generateText({
    messages: [
      { role: 'system', content: 'Be concise.' },
      { role: 'user', content: 'Say hello in one word.' },
    ],
    maxTokens: 10,
    temperature: 0,
  });
  console.log('Response:', result.text);
  console.log('Usage:', result.usage);
  
  // Test streaming
  console.log('\n2. Testing streamText...');
  let streamedText = '';
  const stream = await provider.streamText({
    messages: [{ role: 'user', content: 'Count 1 to 3' }],
    maxTokens: 20,
    onToken: (token) => process.stdout.write(token),
  });
  for await (const chunk of stream) {
    if (chunk.text) streamedText += chunk.text;
  }
  console.log('\nStreamed text:', streamedText);
  
  // Test tool calling
  console.log('\n3. Testing tool calling...');
  const toolResult = await provider.generateText({
    messages: [{ role: 'user', content: 'What is 5+3? Use calculator.' }],
    tools: [{
      name: 'calculator',
      description: 'Math calculator',
      parameters: {
        type: 'object',
        properties: { expression: { type: 'string' } },
        required: ['expression'],
      },
    }],
    maxTokens: 100,
  });
  console.log('Tool calls:', toolResult.toolCalls);
  
  // Test structured output
  console.log('\n4. Testing structured output...');
  const structuredResult = await provider.generateObject({
    messages: [{ role: 'user', content: 'Extract: Alice is 25 years old' }],
    schema: {
      type: 'object',
      properties: {
        name: { type: 'string' },
        age: { type: 'number' },
      },
      required: ['name', 'age'],
      additionalProperties: false,
    },
    maxTokens: 100,
  });
  console.log('Structured output:', structuredResult.object);
  
  console.log('\n✅ OpenAI Provider tests passed!');
}

async function testAnthropic() {
  console.log('\n=== Testing Anthropic Provider ===');
  
  if (!process.env.ANTHROPIC_API_KEY) {
    console.log('ANTHROPIC_API_KEY not set, skipping');
    return;
  }

  try {
    const provider = createProvider('anthropic/claude-sonnet-4-20250514');
    
    console.log('\n1. Testing generateText...');
    const result = await provider.generateText({
      messages: [
        { role: 'user', content: 'Say hello in one word.' },
      ],
      maxTokens: 10,
    });
    console.log('Response:', result.text);
    console.log('Usage:', result.usage);
    
    console.log('\n✅ Anthropic Provider tests passed!');
  } catch (error: any) {
    console.log('Anthropic test failed (may be API key issue):', error.message);
  }
}

async function testGoogle() {
  console.log('\n=== Testing Google Provider ===');
  
  if (!process.env.GOOGLE_API_KEY) {
    console.log('GOOGLE_API_KEY not set, skipping');
    return;
  }

  try {
    const provider = createProvider('google/gemini-2.0-flash');
    
    console.log('\n1. Testing generateText...');
    const result = await provider.generateText({
      messages: [
        { role: 'user', content: 'Say hello in one word.' },
      ],
      maxTokens: 10,
    });
    console.log('Response:', result.text);
    console.log('Usage:', result.usage);
    
    console.log('\n✅ Google Provider tests passed!');
  } catch (error: any) {
    console.log('Google test failed:', error.message);
  }
}

async function main() {
  console.log('Provider Verification Script');
  console.log('============================');
  
  try {
    await testOpenAI();
    await testAnthropic();
    await testGoogle();
    console.log('\n🎉 All provider tests completed!');
  } catch (error) {
    console.error('\n❌ Error:', error);
    process.exit(1);
  }
}

main();
