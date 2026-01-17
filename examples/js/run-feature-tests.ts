/**
 * Feature Parity Integration Test Runner
 * 
 * Runs all integration tests for the new TypeScript features.
 * Tests include real API calls when OPENAI_API_KEY is available.
 * 
 * Run: npx ts-node run-feature-tests.ts
 */

import { execSync, spawn } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

interface TestResult {
    name: string;
    passed: boolean;
    duration: number;
    output: string;
    error?: string;
}

const TEST_FILES = [
    // Workflow patterns
    'workflows/loop-pattern.ts',
    'workflows/repeat-pattern.ts',
    // Agents
    'agents/audio-agent.ts',
    // Knowledge
    'knowledge/chonkie-adapter.ts',
    // MCP
    'mcp/mcp-client-test.ts',
];

async function runTest(testFile: string): Promise<TestResult> {
    const startTime = Date.now();
    const fullPath = path.join(__dirname, testFile);
    const name = path.basename(testFile, '.ts');

    return new Promise((resolve) => {
        const proc = spawn('npx', ['ts-node', fullPath], {
            cwd: __dirname,
            env: { ...process.env },
            stdio: ['pipe', 'pipe', 'pipe']
        });

        let stdout = '';
        let stderr = '';

        proc.stdout.on('data', (data) => {
            stdout += data.toString();
        });

        proc.stderr.on('data', (data) => {
            stderr += data.toString();
        });

        proc.on('close', (code) => {
            const duration = Date.now() - startTime;
            resolve({
                name,
                passed: code === 0,
                duration,
                output: stdout,
                error: stderr || undefined
            });
        });

        proc.on('error', (error) => {
            const duration = Date.now() - startTime;
            resolve({
                name,
                passed: false,
                duration,
                output: '',
                error: error.message
            });
        });

        // Timeout after 60 seconds
        setTimeout(() => {
            proc.kill();
            resolve({
                name,
                passed: false,
                duration: 60000,
                output: stdout,
                error: 'Test timed out after 60 seconds'
            });
        }, 60000);
    });
}

async function main() {
    console.log('╔════════════════════════════════════════════════════════════╗');
    console.log('║     PraisonAI TypeScript Feature Parity Integration Tests  ║');
    console.log('╚════════════════════════════════════════════════════════════╝\n');

    // Environment info
    console.log('Environment:');
    console.log(`  OPENAI_API_KEY: ${process.env.OPENAI_API_KEY ? '✅ Set' : '❌ Not set'}`);
    console.log(`  MCP_SERVER_URL: ${process.env.MCP_SERVER_URL ? '✅ Set' : '❌ Not set'}`);
    console.log(`  Node version: ${process.version}`);
    console.log('');

    // Check if test files exist
    console.log('Test Files:');
    for (const file of TEST_FILES) {
        const fullPath = path.join(__dirname, file);
        const exists = fs.existsSync(fullPath);
        console.log(`  ${exists ? '✅' : '❌'} ${file}`);
    }
    console.log('');

    // Run tests
    console.log('Running Tests...\n');
    console.log('─'.repeat(60));

    const results: TestResult[] = [];
    for (const testFile of TEST_FILES) {
        const fullPath = path.join(__dirname, testFile);
        if (!fs.existsSync(fullPath)) {
            results.push({
                name: path.basename(testFile, '.ts'),
                passed: false,
                duration: 0,
                output: '',
                error: 'File not found'
            });
            continue;
        }

        console.log(`\n▶ Running: ${testFile}`);
        const result = await runTest(testFile);
        results.push(result);

        if (result.passed) {
            console.log(`  ✅ PASSED (${result.duration}ms)`);
        } else {
            console.log(`  ❌ FAILED (${result.duration}ms)`);
            if (result.error) {
                console.log(`     Error: ${result.error.slice(0, 200)}...`);
            }
        }
    }

    console.log('\n' + '─'.repeat(60));

    // Summary
    const passed = results.filter(r => r.passed).length;
    const failed = results.filter(r => !r.passed).length;
    const totalDuration = results.reduce((sum, r) => sum + r.duration, 0);

    console.log('\n╔════════════════════════════════════════════════════════════╗');
    console.log('║                      TEST SUMMARY                          ║');
    console.log('╚════════════════════════════════════════════════════════════╝');
    console.log(`  Total Tests: ${results.length}`);
    console.log(`  Passed: ${passed} ✅`);
    console.log(`  Failed: ${failed} ${failed > 0 ? '❌' : ''}`);
    console.log(`  Duration: ${(totalDuration / 1000).toFixed(2)}s`);
    console.log('');

    // Detailed results
    if (failed > 0) {
        console.log('Failed Tests:');
        for (const result of results.filter(r => !r.passed)) {
            console.log(`  ❌ ${result.name}`);
            if (result.error) {
                console.log(`     ${result.error.slice(0, 100)}`);
            }
        }
        console.log('');
    }

    // Exit with appropriate code
    process.exit(failed > 0 ? 1 : 0);
}

main().catch((error) => {
    console.error('Test runner failed:', error);
    process.exit(1);
});
