/**
 * MemoryHooks Integration Test
 * 
 * Tests pre/post hooks for memory operations.
 * 
 * Run: npx ts-node memory-hooks.ts
 */

import {
    MemoryHooks,
    createMemoryHooks,
    createLoggingHooks,
    createValidationHooks,
    Memory,
    createMemory
} from '../../../src/praisonai-ts/dist';

async function main() {
    console.log('=== MemoryHooks Integration Test ===\n');

    // Test 1: Basic hooks
    console.log('1. Testing basic MemoryHooks:');
    const logs: string[] = [];

    const hooks = new MemoryHooks({
        beforeStore: async (key, value) => {
            logs.push(`beforeStore: ${key}`);
            return { key, value };
        },
        afterStore: async (key) => {
            logs.push(`afterStore: ${key}`);
        },
        beforeRetrieve: async (key) => {
            logs.push(`beforeRetrieve: ${key}`);
            return key;
        },
        afterRetrieve: async (key, value) => {
            logs.push(`afterRetrieve: ${key}`);
            return value;
        }
    });

    await hooks.beforeStore('key1', { data: 'value1' });
    await hooks.afterStore('key1', { data: 'value1' });
    await hooks.beforeRetrieve('key1');
    await hooks.afterRetrieve('key1', { data: 'value1' });

    console.log('   Triggered hooks:', logs);
    console.log('   Success: ✅');

    // Test 2: Logging hooks
    console.log('\n2. Testing createLoggingHooks:');
    const logMessages: string[] = [];
    const loggingHooks = createLoggingHooks((msg) => logMessages.push(msg));

    await loggingHooks.beforeStore('test', 'data');
    await loggingHooks.afterStore('test', 'data');
    await loggingHooks.beforeRetrieve('test');
    await loggingHooks.afterRetrieve('test', 'data');

    console.log('   Log messages:', logMessages.length);
    logMessages.forEach(m => console.log('    -', m));
    console.log('   Success: ✅');

    // Test 3: Validation hooks
    console.log('\n3. Testing createValidationHooks:');
    const validationHooks = createValidationHooks((key, value) => {
        // Only allow non-empty strings
        if (typeof value !== 'string' || value.length === 0) {
            return { valid: false, reason: 'Value must be non-empty string' };
        }
        return { valid: true };
    });

    const validResult = await validationHooks.beforeStore('good', 'valid string');
    console.log('   Valid data allowed:', validResult !== null);

    const invalidResult = await validationHooks.beforeStore('bad', '');
    console.log('   Invalid data blocked:', invalidResult === null);
    console.log('   Success: ✅');

    // Test 4: Delete hooks
    console.log('\n4. Testing delete hooks:');
    const deleteHooks = new MemoryHooks({
        beforeDelete: async (key) => {
            console.log(`   [Hook] About to delete: ${key}`);
            return true; // Allow deletion
        },
        afterDelete: async (key, success) => {
            console.log(`   [Hook] Delete ${key}: ${success ? 'succeeded' : 'failed'}`);
        }
    });

    const canDelete = await deleteHooks.beforeDelete('item-to-delete');
    console.log('   Deletion allowed:', canDelete);
    await deleteHooks.afterDelete('item-to-delete', true);
    console.log('   Success: ✅');

    // Test 5: Search hooks
    console.log('\n5. Testing search hooks:');
    const searchHooks = new MemoryHooks({
        beforeSearch: async (query, options) => {
            console.log(`   [Hook] Searching: "${query}"`);
            // Could modify query here
            return { query: query.toLowerCase(), options };
        },
        afterSearch: async (query, results) => {
            console.log(`   [Hook] Found ${results.length} results for "${query}"`);
            return results;
        }
    });

    const searchParams = await searchHooks.beforeSearch('UPPERCASE QUERY');
    console.log('   Modified query:', searchParams?.query);

    await searchHooks.afterSearch('query', [{ id: '1' }, { id: '2' }]);
    console.log('   Success: ✅');

    // Test 6: Dynamic hook management
    console.log('\n6. Testing dynamic hook management:');
    const dynamicHooks = new MemoryHooks({});

    console.log('   Initial config:', Object.keys(dynamicHooks.getConfig()).length === 0 ? 'empty' : 'has hooks');

    dynamicHooks.addHook('logging', true);
    dynamicHooks.setLogging(true);

    console.log('   After adding logging:', dynamicHooks.getConfig().logging);

    dynamicHooks.removeHook('logging');
    console.log('   After removing:', dynamicHooks.getConfig().logging ?? 'undefined');
    console.log('   Success: ✅');

    console.log('\n=== MemoryHooks Tests Complete ===');
}

main().catch(console.error);
