/**
 * Hooks CLI command - Manage hooks and callbacks
 */

import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface HooksOptions {
    verbose?: boolean;
    output?: 'json' | 'text' | 'pretty';
    json?: boolean;
    event?: string;
    enabled?: boolean;
    logging?: boolean;
}

export async function execute(args: string[], options: HooksOptions): Promise<void> {
    const action = args[0] || 'help';
    const actionArgs = args.slice(1);
    const outputFormat = options.json ? 'json' : (options.output || 'pretty');

    try {
        const {
            HooksManager, createHooksManager,
            registerDisplayCallback, getRegisteredDisplayTypes, clearAllCallbacks,
            DisplayTypes
        } = await import('../../hooks');

        switch (action) {
            case 'list':
                await listHooks(outputFormat);
                break;
            case 'events':
                await listEvents(outputFormat);
                break;
            case 'display-types':
                await listDisplayTypes(outputFormat, getRegisteredDisplayTypes, DisplayTypes);
                break;
            case 'clear':
                await clearHooks(outputFormat, clearAllCallbacks);
                break;
            case 'stats':
                await showStats(outputFormat);
                break;
            case 'help':
            default:
                await showHelp(outputFormat);
                break;
        }
    } catch (error) {
        if (outputFormat === 'json') {
            outputJson(formatError(ERROR_CODES.UNKNOWN, error instanceof Error ? error.message : String(error)));
        } else {
            await pretty.error(error instanceof Error ? error.message : String(error));
        }
        process.exit(EXIT_CODES.RUNTIME_ERROR);
    }
}

async function listHooks(outputFormat: string): Promise<void> {
    const { HooksManager } = await import('../../hooks');
    const manager = new HooksManager({ logging: false });

    const hookEvents = [
        'pre_read_code', 'post_read_code',
        'pre_write_code', 'post_write_code',
        'pre_run_command', 'post_run_command',
        'pre_user_prompt', 'post_user_prompt',
        'pre_mcp_tool_use', 'post_mcp_tool_use',
        'pre_llm_call', 'post_llm_call',
        'pre_tool_call', 'post_tool_call',
        'agent_start', 'agent_complete',
        'run_started', 'run_completed'
    ];

    if (outputFormat === 'json') {
        outputJson(formatSuccess({ events: hookEvents, count: hookEvents.length }));
    } else {
        await pretty.heading('Available Hook Events');
        await pretty.plain(`\nOperation Hooks:`);
        await pretty.plain(`  pre_read_code, post_read_code`);
        await pretty.plain(`  pre_write_code, post_write_code`);
        await pretty.plain(`  pre_run_command, post_run_command`);
        await pretty.plain(`  pre_user_prompt, post_user_prompt`);
        await pretty.plain(`  pre_mcp_tool_use, post_mcp_tool_use`);
        await pretty.plain(`\nLLM/Tool Hooks:`);
        await pretty.plain(`  pre_llm_call, post_llm_call`);
        await pretty.plain(`  pre_tool_call, post_tool_call`);
        await pretty.plain(`\nLifecycle Hooks:`);
        await pretty.plain(`  agent_start, agent_complete`);
        await pretty.plain(`  run_started, run_completed`);
        await pretty.plain(`\nTotal: ${hookEvents.length} hook events`);
    }
}

async function listEvents(outputFormat: string): Promise<void> {
    await listHooks(outputFormat);
}

async function listDisplayTypes(
    outputFormat: string,
    getRegisteredDisplayTypes: () => string[],
    DisplayTypes: Record<string, string>
): Promise<void> {
    const registered = getRegisteredDisplayTypes();
    const builtIn = Object.values(DisplayTypes);

    if (outputFormat === 'json') {
        outputJson(formatSuccess({
            builtIn,
            registered,
            builtInCount: builtIn.length,
            registeredCount: registered.length
        }));
    } else {
        await pretty.heading('Display Types');
        await pretty.plain(`\nBuilt-in types (${builtIn.length}):`);
        for (const type of builtIn) {
            await pretty.plain(`  ${type}`);
        }
        await pretty.plain(`\nRegistered callbacks: ${registered.length}`);
    }
}

async function clearHooks(
    outputFormat: string,
    clearAllCallbacks: () => void
): Promise<void> {
    clearAllCallbacks();

    if (outputFormat === 'json') {
        outputJson(formatSuccess({ cleared: true }));
    } else {
        await pretty.success('All callbacks cleared');
    }
}

async function showStats(outputFormat: string): Promise<void> {
    const { getRegisteredDisplayTypes, hasApprovalCallback } = await import('../../hooks');

    const stats = {
        displayTypes: getRegisteredDisplayTypes().length,
        hasApprovalCallback: hasApprovalCallback(),
        hookEvents: 20  // Total available hook events
    };

    if (outputFormat === 'json') {
        outputJson(formatSuccess(stats));
    } else {
        await pretty.heading('Hooks Stats');
        await pretty.plain(`  Display callbacks: ${stats.displayTypes}`);
        await pretty.plain(`  Approval callback: ${stats.hasApprovalCallback ? 'Yes' : 'No'}`);
        await pretty.plain(`  Available events: ${stats.hookEvents}`);
    }
}

async function showHelp(outputFormat: string): Promise<void> {
    const help = {
        command: 'hooks',
        description: 'Manage hooks and callbacks',
        subcommands: [
            { name: 'list', description: 'List all available hook events' },
            { name: 'events', description: 'List hook events (alias for list)' },
            { name: 'display-types', description: 'List display callback types' },
            { name: 'stats', description: 'Show hooks statistics' },
            { name: 'clear', description: 'Clear all registered callbacks' },
            { name: 'help', description: 'Show this help' }
        ]
    };

    if (outputFormat === 'json') {
        outputJson(formatSuccess(help));
    } else {
        await pretty.heading('Hooks Command');
        await pretty.plain('Manage hooks and callbacks for agent operations\n');
        await pretty.plain('Subcommands:');
        for (const cmd of help.subcommands) {
            await pretty.plain(`  ${cmd.name.padEnd(20)} ${cmd.description}`);
        }
        await pretty.plain('\nExamples:');
        await pretty.plain('  praisonai-ts hooks list');
        await pretty.plain('  praisonai-ts hooks display-types --json');
        await pretty.plain('  praisonai-ts hooks stats');
    }
}
