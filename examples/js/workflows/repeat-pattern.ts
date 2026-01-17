/**
 * Repeat Pattern Integration Test
 * 
 * Tests the Repeat workflow pattern for evaluator-optimizer loops.
 * 
 * Run: npx ts-node repeat-pattern.ts
 */

import { Repeat, repeatPattern, Agent } from '../../../src/praisonai-ts/dist';

async function main() {
    console.log('=== Repeat Pattern Integration Test ===\n');

    // Test 1: Basic repeat until condition
    console.log('1. Testing Repeat with condition:');
    let counter = 0;
    const incrementer = () => {
        counter++;
        return `Iteration ${counter}`;
    };

    const repeat1 = new Repeat(incrementer, {
        until: (ctx) => ctx.iteration >= 3,
        maxIterations: 10
    });

    const result1 = await repeat1.run('start');
    console.log('   Results:', result1.iterations);
    console.log('   Final:', result1.result);
    console.log('   Condition met:', result1.conditionMet ? '✅' : '❌');
    console.log('   Max reached:', result1.maxReached ? '⚠️' : 'No');

    // Test 2: Repeat with content condition
    console.log('\n2. Testing Repeat with content-based condition:');
    let quality = 0;
    const improver = (input: string, prev: string | null) => {
        quality += 25;
        return `Quality: ${quality}% - ${prev || input}`;
    };

    const repeat2 = new Repeat(improver, {
        until: (ctx) => ctx.lastResult?.includes('100%') ?? false,
        maxIterations: 5
    });

    quality = 0; // Reset
    const result2 = await repeat2.run('Initial draft');
    console.log('   Iterations:', result2.count);
    console.log('   Final:', result2.result);
    console.log('   Condition met:', result2.conditionMet ? '✅' : '❌');

    // Test 3: Repeat reaching max iterations
    console.log('\n3. Testing Repeat hitting max iterations:');
    const neverDone = () => 'still working...';

    const repeat3 = new Repeat(neverDone, {
        until: () => false, // Never satisfied
        maxIterations: 3
    });

    const result3 = await repeat3.run('start');
    console.log('   Iterations:', result3.count);
    console.log('   Max reached:', result3.maxReached ? '✅ (expected)' : '❌');

    // Test 4: Repeat with Agent (requires OPENAI_API_KEY)
    if (process.env.OPENAI_API_KEY) {
        console.log('\n4. Testing Repeat with Agent (live API):');
        try {
            const agent = new Agent({
                name: 'Optimizer',
                instructions: 'Improve the given text. Add more detail and clarity. Say "DONE" when satisfied.',
                llm: 'openai/gpt-4o-mini'
            });

            const repeat4 = new Repeat(agent, {
                until: (ctx) => ctx.lastResult?.includes('DONE') ?? false,
                maxIterations: 3
            });

            const result4 = await repeat4.run('Make this better: Hello world');
            console.log('   Iterations:', result4.count);
            console.log('   Final (truncated):', result4.result.slice(0, 100) + '...');
            console.log('   Condition met:', result4.conditionMet ? '✅' : 'Max reached');
        } catch (error: any) {
            console.log('   ⚠️ Agent test failed:', error.message);
        }
    } else {
        console.log('\n4. Agent Repeat Test: Skipped (OPENAI_API_KEY not set)');
    }

    // Test 5: Convenience function
    console.log('\n5. Testing repeatPattern() convenience function:');
    let seq = 0;
    const sequencer = () => `seq-${++seq}`;

    const repeat5 = repeatPattern(sequencer, {
        until: (ctx) => ctx.iteration >= 2,
        maxIterations: 5
    });

    seq = 0; // Reset
    const result5 = await repeat5.run('');
    console.log('   Results:', result5.iterations);
    console.log('   Success:', result5.conditionMet ? '✅' : '❌');

    // Test 6: Verify exports
    console.log('\n6. Verifying exports:');
    console.log('   Repeat class:', typeof Repeat);
    console.log('   repeatPattern function:', typeof repeatPattern);

    console.log('\n=== Repeat Pattern Tests Complete ===');
}

main().catch(console.error);
