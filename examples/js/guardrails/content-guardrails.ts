/**
 * Content Guardrails Example
 * Demonstrates input/output validation
 */

import { guardrail, GuardrailManager, builtinGuardrails, LLMGuardrail } from 'praisonai';

async function main() {
  // Create custom guardrail
  const noSpamGuardrail = guardrail({
    name: 'no_spam',
    check: (content) => {
      const spamWords = ['buy now', 'free money', 'click here'];
      const hasSpam = spamWords.some(word => 
        content.toLowerCase().includes(word)
      );
      return {
        status: hasSpam ? 'failed' : 'passed',
        message: hasSpam ? 'Content contains spam' : undefined
      };
    }
  });

  // Use built-in guardrails
  const maxLength = builtinGuardrails.maxLength(500);
  const minLength = builtinGuardrails.minLength(10);
  const blockedWords = builtinGuardrails.blockedWords(['badword1', 'badword2']);

  // Create manager
  const manager = new GuardrailManager();
  manager.add(noSpamGuardrail);
  manager.add(maxLength);
  manager.add(minLength);
  manager.add(blockedWords);

  // Test content
  const testCases = [
    'This is a normal, helpful response about programming.',
    'BUY NOW! Free money if you click here!',
    'Short',
    'This is a valid response that provides useful information about TypeScript and its benefits for developers.'
  ];

  console.log('=== Guardrail Tests ===\n');

  for (const content of testCases) {
    console.log(`Content: "${content.substring(0, 40)}..."`);
    const result = await manager.runAll(content);
    console.log(`  Passed: ${result.passed}`);
    if (!result.passed) {
      result.results
        .filter(r => r.status === 'failed')
        .forEach(r => console.log(`  Failed: ${r.message}`));
    }
    console.log();
  }

  // LLM Guardrail example
  console.log('=== LLM Guardrail ===');
  const llmGuard = new LLMGuardrail({
    name: 'quality_check',
    criteria: 'Content must be helpful and professional'
  });
  console.log('LLM Guardrail created:', llmGuard.name);
}

main().catch(console.error);
