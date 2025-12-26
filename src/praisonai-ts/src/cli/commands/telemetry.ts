/**
 * Telemetry command - Usage monitoring and analytics
 */

import { getTelemetry, enableTelemetry, disableTelemetry, cleanupTelemetry } from '../../telemetry';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface TelemetryOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

export async function execute(args: string[], options: TelemetryOptions): Promise<void> {
  const action = args[0] || 'status';
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    switch (action) {
      case 'enable':
        enableTelemetry();
        if (outputFormat === 'json') {
          outputJson(formatSuccess({ enabled: true }));
        } else {
          await pretty.success('Telemetry enabled');
        }
        break;
      case 'disable':
        disableTelemetry();
        if (outputFormat === 'json') {
          outputJson(formatSuccess({ enabled: false }));
        } else {
          await pretty.success('Telemetry disabled');
        }
        break;
      case 'status':
        await showStatus(outputFormat);
        break;
      case 'clear':
        cleanupTelemetry();
        if (outputFormat === 'json') {
          outputJson(formatSuccess({ cleared: true }));
        } else {
          await pretty.success('Telemetry data cleared');
        }
        break;
      case 'export':
        await exportTelemetry(outputFormat);
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

async function showStatus(outputFormat: string): Promise<void> {
  const telemetry = getTelemetry();
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      enabled: telemetry.isEnabled()
    }));
  } else {
    await pretty.heading('Telemetry Status');
    await pretty.plain(`Enabled: ${telemetry.isEnabled() ? 'Yes' : 'No'}`);
  }
}

async function exportTelemetry(outputFormat: string): Promise<void> {
  const telemetry = getTelemetry();
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      enabled: telemetry.isEnabled(),
      exportedAt: new Date().toISOString()
    }));
  } else {
    await pretty.plain(`Telemetry enabled: ${telemetry.isEnabled()}`);
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'telemetry',
    subcommands: [
      { name: 'status', description: 'Show telemetry status' },
      { name: 'enable', description: 'Enable telemetry collection' },
      { name: 'disable', description: 'Disable telemetry collection' },
      { name: 'clear', description: 'Clear collected telemetry data' },
      { name: 'export', description: 'Export telemetry data' },
      { name: 'help', description: 'Show this help' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Telemetry Command');
    await pretty.plain('Usage monitoring and analytics\n');
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(15)} ${cmd.description}`);
    }
  }
}
