/**
 * LLM-as-Judge Example
 * 
 * Demonstrates how to use the Judge class for evaluating agent outputs.
 */

import { Judge, AccuracyJudge, CriteriaJudge, RecipeJudge, addJudge, listJudges } from '../../src/eval/judge';

async function main() {
  console.log('=== LLM-as-Judge Examples ===\n');

  // Example 1: Simple accuracy evaluation
  console.log('1. Accuracy Evaluation');
  console.log('-'.repeat(40));
  
  const accuracyJudge = new Judge();
  const accuracyResult = await accuracyJudge.run({
    output: '4',
    expected: '4',
    input: 'What is 2+2?',
  });
  
  console.log(`Score: ${accuracyResult.score}/10`);
  console.log(`Passed: ${accuracyResult.passed}`);
  console.log(`Reasoning: ${accuracyResult.reasoning}`);
  console.log();

  // Example 2: Criteria-based evaluation
  console.log('2. Criteria Evaluation');
  console.log('-'.repeat(40));
  
  const criteriaJudge = new Judge({
    criteria: 'Response is helpful, friendly, and professional',
    threshold: 7.0,
  });
  
  const criteriaResult = await criteriaJudge.run({
    output: 'Hello! I\'d be happy to help you with that. What would you like to know?',
  });
  
  console.log(`Score: ${criteriaResult.score}/10`);
  console.log(`Passed: ${criteriaResult.passed}`);
  console.log(`Suggestions: ${criteriaResult.suggestions.join(', ') || 'None'}`);
  console.log();

  // Example 3: Recipe/Workflow evaluation
  console.log('3. Recipe Evaluation');
  console.log('-'.repeat(40));
  
  const recipeJudge = new RecipeJudge({ mode: 'context' });
  const recipeResult = await recipeJudge.run({
    output: 'Research complete. Analysis shows positive trends.',
    expected: 'Complete research with citations and analysis',
  });
  
  console.log(`Score: ${recipeResult.score}/10`);
  console.log(`Mode: ${recipeJudge.mode}`);
  console.log();

  // Example 4: Custom Judge
  console.log('4. Custom Judge Registration');
  console.log('-'.repeat(40));
  
  class CodeReviewJudge extends Judge {
    constructor() {
      super({
        criteria: 'Code follows best practices, is readable, and well-documented',
        threshold: 8.0,
      });
    }
  }
  
  addJudge('code_review', CodeReviewJudge);
  console.log(`Registered judges: ${listJudges().join(', ')}`);
  console.log();

  // Example 5: Domain-agnostic evaluation
  console.log('5. Domain-Agnostic Evaluation');
  console.log('-'.repeat(40));
  
  const domainJudge = new Judge({
    criteriaConfig: {
      name: 'data_quality',
      description: 'Evaluate data pipeline output quality',
      promptTemplate: `Evaluate the data quality:
{output}

Score based on completeness, accuracy, and format.

SCORE: [1-10]
REASONING: [explanation]
SUGGESTIONS: [improvements]`,
      scoringDimensions: ['completeness', 'accuracy', 'format'],
      threshold: 7.0,
    },
  });
  
  const domainResult = await domainJudge.run({
    output: 'Records processed: 1000, Errors: 2, Format: JSON',
  });
  
  console.log(`Score: ${domainResult.score}/10`);
  console.log(`Passed: ${domainResult.passed}`);
  console.log();

  // Example 6: Batch evaluation
  console.log('6. Batch Evaluation');
  console.log('-'.repeat(40));
  
  const outputs = [
    'Hello! How can I assist you today?',
    'I don\'t know.',
    'Let me help you find the answer to that question.',
  ];
  
  const batchJudge = new Judge({ criteria: 'Response is helpful' });
  
  const results = await Promise.all(
    outputs.map(output => batchJudge.run({ output }))
  );
  
  results.forEach((result, i) => {
    const status = result.passed ? '✅' : '❌';
    console.log(`${status} "${outputs[i].slice(0, 30)}..." → ${result.score}/10`);
  });
  
  console.log('\n=== Examples Complete ===');
}

// Run if executed directly
main().catch(console.error);
