/**
 * Git Integration - Git operations for CLI
 * Safe, read-focused operations with optional write capabilities
 */

export interface GitConfig {
  cwd?: string;
  safe?: boolean; // If true, only allow read operations
}

export interface GitStatus {
  branch: string;
  ahead: number;
  behind: number;
  staged: string[];
  modified: string[];
  untracked: string[];
  deleted: string[];
  conflicts: string[];
}

export interface GitCommit {
  hash: string;
  shortHash: string;
  author: string;
  email: string;
  date: Date;
  message: string;
}

export interface GitDiff {
  files: GitDiffFile[];
  summary: string;
}

export interface GitDiffFile {
  path: string;
  status: 'added' | 'modified' | 'deleted' | 'renamed';
  additions: number;
  deletions: number;
  diff?: string;
}

/**
 * Git Manager class
 */
export class GitManager {
  private cwd: string;
  private safe: boolean;

  constructor(config: GitConfig = {}) {
    this.cwd = config.cwd || process.cwd();
    this.safe = config.safe ?? true;
  }

  /**
   * Execute a git command
   */
  private async exec(args: string[]): Promise<string> {
    const { spawn } = await import('child_process');
    
    return new Promise((resolve, reject) => {
      const proc = spawn('git', args, {
        cwd: this.cwd,
        stdio: ['pipe', 'pipe', 'pipe']
      });

      let stdout = '';
      let stderr = '';

      proc.stdout?.on('data', (data) => {
        stdout += data.toString();
      });

      proc.stderr?.on('data', (data) => {
        stderr += data.toString();
      });

      proc.on('close', (code) => {
        if (code === 0) {
          resolve(stdout.trim());
        } else {
          reject(new Error(stderr || `Git command failed with code ${code}`));
        }
      });

      proc.on('error', reject);
    });
  }

  /**
   * Check if directory is a git repository
   */
  async isRepo(): Promise<boolean> {
    try {
      await this.exec(['rev-parse', '--git-dir']);
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Get current branch name
   */
  async getBranch(): Promise<string> {
    return this.exec(['rev-parse', '--abbrev-ref', 'HEAD']);
  }

  /**
   * Get repository status
   */
  async getStatus(): Promise<GitStatus> {
    const branch = await this.getBranch();
    const porcelain = await this.exec(['status', '--porcelain', '-b']);
    
    const lines = porcelain.split('\n');
    const status: GitStatus = {
      branch,
      ahead: 0,
      behind: 0,
      staged: [],
      modified: [],
      untracked: [],
      deleted: [],
      conflicts: []
    };

    // Parse branch line for ahead/behind
    const branchLine = lines[0];
    const aheadMatch = branchLine.match(/ahead (\d+)/);
    const behindMatch = branchLine.match(/behind (\d+)/);
    if (aheadMatch) status.ahead = parseInt(aheadMatch[1]);
    if (behindMatch) status.behind = parseInt(behindMatch[1]);

    // Parse file status
    for (const line of lines.slice(1)) {
      if (!line) continue;
      
      const indexStatus = line[0];
      const workStatus = line[1];
      const file = line.slice(3);

      if (indexStatus === 'U' || workStatus === 'U') {
        status.conflicts.push(file);
      } else if (indexStatus === '?' && workStatus === '?') {
        status.untracked.push(file);
      } else if (indexStatus === 'D' || workStatus === 'D') {
        status.deleted.push(file);
      } else if (indexStatus !== ' ') {
        status.staged.push(file);
      } else if (workStatus === 'M') {
        status.modified.push(file);
      }
    }

    return status;
  }

  /**
   * Get diff (staged or unstaged)
   */
  async getDiff(staged: boolean = false): Promise<GitDiff> {
    const args = ['diff', '--stat'];
    if (staged) args.push('--staged');
    
    const stat = await this.exec(args);
    const files: GitDiffFile[] = [];
    
    const lines = stat.split('\n');
    for (const line of lines) {
      const match = line.match(/^\s*(.+?)\s*\|\s*(\d+)\s*([+-]*)/);
      if (match) {
        const [, path, changes, indicators] = match;
        const additions = (indicators.match(/\+/g) || []).length;
        const deletions = (indicators.match(/-/g) || []).length;
        
        files.push({
          path: path.trim(),
          status: 'modified',
          additions,
          deletions
        });
      }
    }

    // Get full diff for summary
    const fullDiffArgs = ['diff'];
    if (staged) fullDiffArgs.push('--staged');
    const fullDiff = await this.exec(fullDiffArgs);

    return {
      files,
      summary: fullDiff
    };
  }

  /**
   * Get recent commits
   */
  async getLog(limit: number = 10): Promise<GitCommit[]> {
    const format = '%H|%h|%an|%ae|%aI|%s';
    const output = await this.exec(['log', `-${limit}`, `--format=${format}`]);
    
    return output.split('\n').filter(Boolean).map(line => {
      const [hash, shortHash, author, email, date, message] = line.split('|');
      return {
        hash,
        shortHash,
        author,
        email,
        date: new Date(date),
        message
      };
    });
  }

  /**
   * Get list of branches
   */
  async getBranches(): Promise<{ name: string; current: boolean }[]> {
    const output = await this.exec(['branch', '--list']);
    return output.split('\n').filter(Boolean).map(line => ({
      name: line.replace(/^\*?\s*/, '').trim(),
      current: line.startsWith('*')
    }));
  }

  /**
   * Stage files (requires safe=false)
   */
  async add(files: string[] = ['.']): Promise<void> {
    if (this.safe) {
      throw new Error('Write operations disabled in safe mode');
    }
    await this.exec(['add', ...files]);
  }

  /**
   * Commit staged changes (requires safe=false)
   */
  async commit(message: string): Promise<string> {
    if (this.safe) {
      throw new Error('Write operations disabled in safe mode');
    }
    return this.exec(['commit', '-m', message]);
  }

  /**
   * Stash changes (requires safe=false)
   */
  async stash(message?: string): Promise<void> {
    if (this.safe) {
      throw new Error('Write operations disabled in safe mode');
    }
    const args = ['stash', 'push'];
    if (message) args.push('-m', message);
    await this.exec(args);
  }

  /**
   * Pop stash (requires safe=false)
   */
  async stashPop(): Promise<void> {
    if (this.safe) {
      throw new Error('Write operations disabled in safe mode');
    }
    await this.exec(['stash', 'pop']);
  }

  /**
   * Get stash list
   */
  async getStashList(): Promise<string[]> {
    const output = await this.exec(['stash', 'list']);
    return output.split('\n').filter(Boolean);
  }

  /**
   * Get file content at a specific commit
   */
  async show(ref: string, path: string): Promise<string> {
    return this.exec(['show', `${ref}:${path}`]);
  }

  /**
   * Get blame for a file
   */
  async blame(path: string): Promise<string> {
    return this.exec(['blame', path]);
  }

  /**
   * Generate commit message from staged changes
   */
  async generateCommitMessage(): Promise<string> {
    const diff = await this.getDiff(true);
    
    if (diff.files.length === 0) {
      return 'No staged changes';
    }

    const fileList = diff.files.map(f => f.path).join(', ');
    const totalAdditions = diff.files.reduce((sum, f) => sum + f.additions, 0);
    const totalDeletions = diff.files.reduce((sum, f) => sum + f.deletions, 0);

    // Simple template-based message
    if (diff.files.length === 1) {
      return `Update ${diff.files[0].path}`;
    }

    return `Update ${diff.files.length} files (+${totalAdditions}/-${totalDeletions})`;
  }

  /**
   * Get formatted status string
   */
  async getStatusString(): Promise<string> {
    const status = await this.getStatus();
    const lines: string[] = [];

    lines.push(`Branch: ${status.branch}`);
    if (status.ahead > 0) lines.push(`  ↑ ${status.ahead} ahead`);
    if (status.behind > 0) lines.push(`  ↓ ${status.behind} behind`);

    if (status.staged.length > 0) {
      lines.push(`\nStaged (${status.staged.length}):`);
      status.staged.forEach(f => lines.push(`  + ${f}`));
    }

    if (status.modified.length > 0) {
      lines.push(`\nModified (${status.modified.length}):`);
      status.modified.forEach(f => lines.push(`  M ${f}`));
    }

    if (status.untracked.length > 0) {
      lines.push(`\nUntracked (${status.untracked.length}):`);
      status.untracked.forEach(f => lines.push(`  ? ${f}`));
    }

    if (status.deleted.length > 0) {
      lines.push(`\nDeleted (${status.deleted.length}):`);
      status.deleted.forEach(f => lines.push(`  - ${f}`));
    }

    if (status.conflicts.length > 0) {
      lines.push(`\nConflicts (${status.conflicts.length}):`);
      status.conflicts.forEach(f => lines.push(`  ! ${f}`));
    }

    return lines.join('\n');
  }
}

/**
 * Create a git manager instance
 */
export function createGitManager(config?: GitConfig): GitManager {
  return new GitManager(config);
}

/**
 * Diff viewer with syntax highlighting (text-based)
 */
export class DiffViewer {
  private diff: string;

  constructor(diff: string) {
    this.diff = diff;
  }

  /**
   * Get formatted diff with markers
   */
  format(): string {
    const lines = this.diff.split('\n');
    return lines.map(line => {
      if (line.startsWith('+') && !line.startsWith('+++')) {
        return `[+] ${line}`;
      }
      if (line.startsWith('-') && !line.startsWith('---')) {
        return `[-] ${line}`;
      }
      if (line.startsWith('@@')) {
        return `[~] ${line}`;
      }
      return `    ${line}`;
    }).join('\n');
  }

  /**
   * Get summary statistics
   */
  getStats(): { additions: number; deletions: number } {
    let additions = 0;
    let deletions = 0;

    for (const line of this.diff.split('\n')) {
      if (line.startsWith('+') && !line.startsWith('+++')) {
        additions++;
      }
      if (line.startsWith('-') && !line.startsWith('---')) {
        deletions++;
      }
    }

    return { additions, deletions };
  }
}

/**
 * Create a diff viewer
 */
export function createDiffViewer(diff: string): DiffViewer {
  return new DiffViewer(diff);
}
