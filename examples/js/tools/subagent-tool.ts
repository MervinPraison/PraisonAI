/**
 * SubagentTool Integration Test
 * 
 * Tests the agent-as-tool pattern with real agents.
 * 
 * Run: npx ts-node subagent-tool.ts
 * Requires: OPENAI_API_KEY
 */

import {
    Agent,
    SubagentTool,
    createSubagentTool,
    createSubagentTools,
    createDelegator
} from '../../../src/praisonai-ts/dist';

async function main() {
    console.log('=== SubagentTool Integration Test ===\n');

    // Test 1: Create SubagentTool
    console.log('1. Testing SubagentTool creation:');
    const mockAgent = {
        name: 'MockAgent',
        chat: async (input: string) => `Echo: ${input}`
    };

    const tool = new SubagentTool(mockAgent, {
        name: 'echo',
        description: 'Echo the input'
    });

    console.log('   Tool name:', tool.name);
    console.log('   Tool ID:', tool.id);
    console.log('   Schema:', JSON.stringify(tool.getSchema()));
    console.log('   Success: ✅');

    // Test 2: Execute tool with mock agent
    console.log('\n2. Testing tool execution:');
    const mockResult = await tool.execute({ input: 'Hello World' });
    console.log('   Input: "Hello World"');
    console.log('   Output:', mockResult);
    console.log('   Success: ✅');

    // Test 3: Factory function
    console.log('\n3. Testing createSubagentTool factory:');
    const factoryTool = createSubagentTool(mockAgent, { name: 'factory_echo' });
    console.log('   Tool name:', factoryTool.name);
    console.log('   Success: ✅');

    // Test 4: Multiple subagent tools
    console.log('\n4. Testing createSubagentTools (batch):');
    const agents = [
        { name: 'Agent1', chat: async (i: string) => `A1: ${i}` },
        { name: 'Agent2', chat: async (i: string) => `A2: ${i}` }
    ];
    const tools = createSubagentTools(agents);
    console.log('   Created tools:', tools.length);
    tools.forEach(t => console.log('    -', t.name));
    console.log('   Success: ✅');

    // Test 5: AI SDK format conversion
    console.log('\n5. Testing AI SDK format conversion:');
    const aiTool = tool.toAISDKTool();
    console.log('   Type:', aiTool.type);
    console.log('   Function name:', aiTool.function.name);
    console.log('   Has execute:', typeof aiTool.execute === 'function');
    console.log('   Success: ✅');

    // Test 6: Live test with real agent
    if (process.env.OPENAI_API_KEY) {
        console.log('\n6. Testing with real Agent (live API):');
        try {
            const researcher = new Agent({
                name: 'QuickResearcher',
                instructions: 'Answer in exactly 5 words.',
                llm: 'openai/gpt-4o-mini'
            });

            const researchTool = createSubagentTool(researcher, {
                name: 'quick_research',
                description: 'Get a quick 5-word answer'
            });

            const result = await researchTool.execute({ input: 'What is AI?' });
            console.log('   Question: "What is AI?"');
            console.log('   Answer:', result);
            console.log('   Success: ✅');
        } catch (error: any) {
            console.log('   Error:', error.message);
        }
    } else {
        console.log('\n6. Live test: Skipped (OPENAI_API_KEY not set)');
    }

    // Test 7: Input/Output transforms
    console.log('\n7. Testing transforms:');
    const transformTool = createSubagentTool(mockAgent, {
        name: 'transform_echo',
        inputTransform: (input) => input.toUpperCase(),
        outputTransform: (output) => `[TRANSFORMED] ${output}`
    });

    const transformResult = await transformTool.execute({ input: 'hello' });
    console.log('   Input: "hello"');
    console.log('   Output:', transformResult);
    console.log('   Success: ✅');

    console.log('\n=== SubagentTool Tests Complete ===');
}

main().catch(console.error);
