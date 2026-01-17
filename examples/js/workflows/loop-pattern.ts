/**
 * Loop Pattern Integration Test
 * 
 * Tests the Loop workflow pattern with real data.
 * 
 * Run: npx ts-node loop-pattern.ts
 */

import { Loop, loopPattern, Agent, Workflow } from '../../../src/praisonai-ts/dist';

async function main() {
    console.log('=== Loop Pattern Integration Test ===\n');

    // Test 1: Basic Loop with array
    console.log('1. Testing Loop with array iteration:');
    const items = ['apple', 'banana', 'cherry'];

    const processor = (item: string) => `Processed: ${item.toUpperCase()}`;
    const arrayLoop = new Loop(processor, { over: 'items' });

    const result1 = await arrayLoop.run({ items });
    console.log('   Results:', result1.results);
    console.log('   Iterations:', result1.iterations);
    console.log('   Success:', result1.success ? '✅' : '❌');

    // Test 2: Loop with convenience function
    console.log('\n2. Testing loop() convenience function:');
    const doubler = (n: number) => n * 2;
    const numberLoop = loopPattern(doubler, { over: 'numbers' });

    const result2 = await numberLoop.run({ numbers: [1, 2, 3, 4, 5] });
    console.log('   Input: [1, 2, 3, 4, 5]');
    console.log('   Output:', result2.results);
    console.log('   Success:', result2.success ? '✅' : '❌');

    // Test 3: Loop with Agent (requires OPENAI_API_KEY)
    if (process.env.OPENAI_API_KEY) {
        console.log('\n3. Testing Loop with Agent (live API):');
        try {
            const agent = new Agent({
                name: 'Summarizer',
                instructions: 'Summarize the given topic in one sentence.',
                llm: 'openai/gpt-4o-mini'
            });

            const topics = ['AI', 'TypeScript'];
            const agentLoop = new Loop(agent, { over: 'topics', varName: 'topic' });

            console.log('   Processing topics:', topics);
            const result3 = await agentLoop.run({ topics });

            result3.results.forEach((res, i) => {
                console.log(`   [${topics[i]}]: ${res.slice(0, 80)}...`);
            });
            console.log('   Success:', result3.success ? '✅' : '❌');
        } catch (error: any) {
            console.log('   ⚠️ Agent test failed:', error.message);
        }
    } else {
        console.log('\n3. Agent Loop Test: Skipped (OPENAI_API_KEY not set)');
    }

    // Test 4: Loop with error handling
    console.log('\n4. Testing Loop with continueOnError:');
    const errorProneProcessor = (item: string) => {
        if (item === 'fail') throw new Error('Intentional failure');
        return `OK: ${item}`;
    };

    const errorLoop = new Loop(errorProneProcessor, {
        over: 'items',
        continueOnError: true
    });

    const result4 = await errorLoop.run({ items: ['a', 'fail', 'b'] });
    console.log('   Results:', result4.results);
    console.log('   Errors:', result4.errors.length);
    console.log('   Success:', result4.success ? '✅' : '❌ (expected - has errors)');

    // Test 5: Loop type exports
    console.log('\n5. Verifying exports:');
    console.log('   Loop class:', typeof Loop);
    console.log('   loop function:', typeof loopPattern);

    console.log('\n=== Loop Pattern Tests Complete ===');
}

main().catch(console.error);
