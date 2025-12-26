/**
 * CLI command: git
 * Git integration for repository operations
 */

import { GitManager, createGitManager, DiffViewer, createDiffViewer } from '../features/git-integration';

export async function execute(args: string[], options: Record<string, unknown>): Promise<void> {
  const subcommand = args[0] || 'help';
  const isJson = Boolean(options.output === 'json' || options.json);
  const cwd = (options.cwd as string) || process.cwd();

  switch (subcommand) {
    case 'status':
      await handleStatus(cwd, isJson);
      break;
    case 'diff':
      await handleDiff(options, cwd, isJson);
      break;
    case 'log':
      await handleLog(options, cwd, isJson);
      break;
    case 'branches':
      await handleBranches(cwd, isJson);
      break;
    case 'stash':
      await handleStash(args.slice(1), cwd, isJson);
      break;
    case 'help':
    default:
      showHelp(isJson);
  }
}

async function handleStatus(cwd: string, isJson: boolean): Promise<void> {
  const git = createGitManager({ cwd, safe: true });

  if (!await git.isRepo()) {
    console.error('Error: Not a git repository');
    process.exit(1);
  }

  const status = await git.getStatus();

  if (isJson) {
    console.log(JSON.stringify({ success: true, ...status }, null, 2));
  } else {
    console.log(await git.getStatusString());
  }
}

async function handleDiff(options: Record<string, unknown>, cwd: string, isJson: boolean): Promise<void> {
  const git = createGitManager({ cwd, safe: true });
  const staged = Boolean(options.staged);

  if (!await git.isRepo()) {
    console.error('Error: Not a git repository');
    process.exit(1);
  }

  const diff = await git.getDiff(staged);

  if (isJson) {
    console.log(JSON.stringify({ success: true, ...diff }, null, 2));
  } else {
    if (diff.files.length === 0) {
      console.log(staged ? 'No staged changes' : 'No changes');
    } else {
      console.log(`Changes (${diff.files.length} files):\n`);
      for (const file of diff.files) {
        console.log(`  ${file.path} (+${file.additions}/-${file.deletions})`);
      }
      if (options.full) {
        console.log('\n' + diff.summary);
      }
    }
  }
}

async function handleLog(options: Record<string, unknown>, cwd: string, isJson: boolean): Promise<void> {
  const git = createGitManager({ cwd, safe: true });
  const limit = (options.limit as number) || 10;

  if (!await git.isRepo()) {
    console.error('Error: Not a git repository');
    process.exit(1);
  }

  const commits = await git.getLog(limit);

  if (isJson) {
    console.log(JSON.stringify({ success: true, commits }, null, 2));
  } else {
    console.log('Recent commits:\n');
    for (const commit of commits) {
      console.log(`  ${commit.shortHash} ${commit.message}`);
      console.log(`    by ${commit.author} on ${commit.date.toLocaleDateString()}`);
    }
  }
}

async function handleBranches(cwd: string, isJson: boolean): Promise<void> {
  const git = createGitManager({ cwd, safe: true });

  if (!await git.isRepo()) {
    console.error('Error: Not a git repository');
    process.exit(1);
  }

  const branches = await git.getBranches();

  if (isJson) {
    console.log(JSON.stringify({ success: true, branches }, null, 2));
  } else {
    console.log('Branches:\n');
    for (const branch of branches) {
      const marker = branch.current ? '* ' : '  ';
      console.log(`${marker}${branch.name}`);
    }
  }
}

async function handleStash(args: string[], cwd: string, isJson: boolean): Promise<void> {
  const git = createGitManager({ cwd, safe: true });

  if (!await git.isRepo()) {
    console.error('Error: Not a git repository');
    process.exit(1);
  }

  const stashes = await git.getStashList();

  if (isJson) {
    console.log(JSON.stringify({ success: true, stashes }, null, 2));
  } else {
    if (stashes.length === 0) {
      console.log('No stashes');
    } else {
      console.log('Stashes:\n');
      for (const stash of stashes) {
        console.log(`  ${stash}`);
      }
    }
  }
}

function showHelp(isJson: boolean): void {
  const help = {
    command: 'git',
    description: 'Git integration for repository operations (read-only by default)',
    subcommands: {
      status: 'Show repository status',
      diff: 'Show changes',
      log: 'Show recent commits',
      branches: 'List branches',
      stash: 'List stashes'
    },
    flags: {
      '--cwd': 'Working directory (default: current)',
      '--staged': 'Show staged changes only (for diff)',
      '--full': 'Show full diff output',
      '--limit': 'Number of commits to show (default: 10)',
      '--json': 'Output in JSON format'
    },
    examples: [
      'praisonai-ts git status',
      'praisonai-ts git diff',
      'praisonai-ts git diff --staged',
      'praisonai-ts git log --limit 5',
      'praisonai-ts git branches',
      'praisonai-ts git stash'
    ]
  };

  if (isJson) {
    console.log(JSON.stringify(help, null, 2));
  } else {
    console.log('Git - Repository operations (read-only)\n');
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
