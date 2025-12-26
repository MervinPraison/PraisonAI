/**
 * Version command - Show CLI version
 */

import { CLI_SPEC_VERSION } from '../spec/cli-spec';
import { outputJson, formatSuccess } from '../output/json';
import * as pretty from '../output/pretty';

export interface VersionOptions {
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

export async function execute(args: string[], options: VersionOptions): Promise<void> {
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');
  
  // Load package.json for version
  let packageVersion = '0.0.0';
  try {
    const pkg = require('../../../package.json');
    packageVersion = pkg.version;
  } catch {
    // Fallback if package.json not found
  }

  const versionInfo = {
    version: packageVersion,
    cli_spec: CLI_SPEC_VERSION,
    runtime: 'node',
    node_version: process.version
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(versionInfo));
  } else {
    await pretty.plain(`praisonai-ts v${packageVersion}`);
    await pretty.dim(`CLI Spec: v${CLI_SPEC_VERSION}`);
    await pretty.dim(`Node: ${process.version}`);
  }
}
