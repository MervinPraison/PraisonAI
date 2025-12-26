/**
 * CLI command: repo-map
 * Repository structure visualization and symbol extraction
 */

import { RepoMap, createRepoMap, getRepoTree } from '../features/repo-map';

export async function execute(args: string[], options: Record<string, unknown>): Promise<void> {
  const subcommand = args[0] || 'tree';
  const isJson = Boolean(options.output === 'json' || options.json);

  switch (subcommand) {
    case 'tree':
      await handleTree(args.slice(1), options, isJson);
      break;
    case 'symbols':
      await handleSymbols(args.slice(1), options, isJson);
      break;
    case 'help':
    default:
      if (subcommand !== 'help' && !subcommand.startsWith('-')) {
        // Treat as path for tree command
        await handleTree([subcommand, ...args.slice(1)], options, isJson);
      } else {
        showHelp(isJson);
      }
  }
}

async function handleTree(args: string[], options: Record<string, unknown>, isJson: boolean): Promise<void> {
  const rootPath = args[0] || process.cwd();
  const maxDepth = (options.depth as number) || 5;
  const includeSymbols = Boolean(options.symbols);

  const map = createRepoMap({
    rootPath,
    maxDepth,
    includeSymbols
  });

  try {
    const result = await map.generate();

    if (isJson) {
      console.log(JSON.stringify({
        success: true,
        root: result.root,
        totalFiles: result.totalFiles,
        totalDirectories: result.totalDirectories,
        symbolCount: result.symbols.length
      }, null, 2));
    } else {
      console.log(result.summary);
    }
  } catch (error: any) {
    if (isJson) {
      console.log(JSON.stringify({ success: false, error: error.message }));
    } else {
      console.error(`Error: ${error.message}`);
    }
    process.exit(1);
  }
}

async function handleSymbols(args: string[], options: Record<string, unknown>, isJson: boolean): Promise<void> {
  const rootPath = args[0] || process.cwd();
  const maxDepth = (options.depth as number) || 5;

  const map = createRepoMap({
    rootPath,
    maxDepth,
    includeSymbols: true
  });

  try {
    const result = await map.generate();

    if (isJson) {
      console.log(JSON.stringify({
        success: true,
        symbols: result.symbols,
        count: result.symbols.length
      }, null, 2));
    } else {
      console.log(`Symbols in ${rootPath}:\n`);
      
      const byType: Record<string, typeof result.symbols> = {};
      for (const sym of result.symbols) {
        if (!byType[sym.type]) byType[sym.type] = [];
        byType[sym.type].push(sym);
      }

      for (const [type, symbols] of Object.entries(byType)) {
        console.log(`${type}s (${symbols.length}):`);
        for (const sym of symbols.slice(0, 20)) {
          const exported = sym.exported ? ' [exported]' : '';
          console.log(`  ${sym.name}${exported} (line ${sym.line})`);
        }
        if (symbols.length > 20) {
          console.log(`  ... and ${symbols.length - 20} more`);
        }
        console.log();
      }
    }
  } catch (error: any) {
    if (isJson) {
      console.log(JSON.stringify({ success: false, error: error.message }));
    } else {
      console.error(`Error: ${error.message}`);
    }
    process.exit(1);
  }
}

function showHelp(isJson: boolean): void {
  const help = {
    command: 'repo-map',
    description: 'Repository structure visualization and symbol extraction',
    subcommands: {
      tree: 'Show repository tree structure',
      symbols: 'Extract and list code symbols'
    },
    flags: {
      '--depth': 'Maximum directory depth (default: 5)',
      '--symbols': 'Include symbols in tree output',
      '--json': 'Output in JSON format'
    },
    examples: [
      'praisonai-ts repo-map',
      'praisonai-ts repo-map tree ./src',
      'praisonai-ts repo-map tree --depth 3',
      'praisonai-ts repo-map symbols ./src',
      'praisonai-ts repo-map tree --symbols'
    ]
  };

  if (isJson) {
    console.log(JSON.stringify(help, null, 2));
  } else {
    console.log('Repo Map - Repository visualization\n');
    console.log('Subcommands:');
    for (const [cmd, desc] of Object.entries(help.subcommands)) {
      console.log(`  ${cmd.padEnd(12)} ${desc}`);
    }
    console.log('\nFlags:');
    for (const [flag, desc] of Object.entries(help.flags)) {
      console.log(`  ${flag.padEnd(12)} ${desc}`);
    }
    console.log('\nExamples:');
    for (const ex of help.examples) {
      console.log(`  ${ex}`);
    }
  }
}
