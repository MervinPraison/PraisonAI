/**
 * Incremental Indexing Infrastructure for PraisonAI Agents.
 *
 * Port of `praisonaiagents/knowledge/indexing.py`.
 *
 * Provides:
 * - CorpusStats: Statistics about indexed corpus
 * - IndexResult: Result of indexing operation
 * - IgnoreMatcher: .praisonignore pattern matching
 * - FileTracker: File hash/mtime tracking for incremental updates
 *
 * No heavy imports - only Node stdlib.
 *
 * Serialised shapes (`toDict()`, the FileTracker state file) keep the Python
 * snake_case keys so the JSON written by either runtime is readable by the
 * other. Constructor/method parameters use camelCase.
 */

import * as fs from 'fs';
import * as path from 'path';
import { createHash } from 'crypto';

/**
 * Strategy thresholds based on corpus size.
 * Mirrors `STRATEGY_THRESHOLDS` in indexing.py:24-30.
 */
export const STRATEGY_THRESHOLDS: Record<number, string> = {
  10: 'direct', // < 10 files: load all
  100: 'basic', // < 100 files: semantic search only
  1000: 'hybrid', // < 1000 files: keyword + semantic
  10000: 'reranked', // < 10000 files: hybrid + rerank
  100000: 'compressed', // < 100000 files: reranked + compression
};

/** Strategy for corpora above every threshold. indexing.py:31 */
export const DEFAULT_STRATEGY = 'hierarchical'; // > 100000 files

/**
 * Default extensions scanned by `CorpusStats.fromDirectory`. indexing.py:87-90
 */
export const DEFAULT_CORPUS_EXTENSIONS: readonly string[] = [
  '.txt', '.md', '.py', '.js', '.ts', '.json', '.yaml', '.yml',
  '.html', '.css', '.csv', '.xml', '.rst', '.pdf', '.docx',
];

/**
 * Simple token estimation (~4 chars per token).
 * Port of `estimate_tokens_simple` (indexing.py:34-38).
 */
export function estimateTokensSimple(text: string): number {
  if (!text) {
    return 0;
  }
  return Math.floor(text.length / 4) + 1;
}

// ---------------------------------------------------------------------------
// fnmatch port
// ---------------------------------------------------------------------------

/**
 * Translate a shell-style pattern to a RegExp source, following Python's
 * `fnmatch.translate`: `*` matches any run of characters (including `/`),
 * `?` matches one character, `[seq]` / `[!seq]` are character classes and
 * everything else is literal. The result anchors to the whole string.
 */
export function fnmatchTranslate(pattern: string): string {
  let i = 0;
  const n = pattern.length;
  let res = '';
  while (i < n) {
    const c = pattern[i];
    i += 1;
    if (c === '*') {
      res += '.*';
    } else if (c === '?') {
      res += '.';
    } else if (c === '[') {
      let j = i;
      if (j < n && pattern[j] === '!') {
        j += 1;
      }
      if (j < n && pattern[j] === ']') {
        j += 1;
      }
      while (j < n && pattern[j] !== ']') {
        j += 1;
      }
      if (j >= n) {
        res += '\\[';
      } else {
        let stuff = pattern.slice(i, j);
        if (stuff.startsWith('!')) {
          stuff = '^' + stuff.slice(1);
        } else if (stuff.startsWith('^')) {
          stuff = '\\' + stuff;
        }
        // Escape backslashes and a closing bracket that survived the scan.
        stuff = stuff.replace(/\\/g, '\\\\').replace(/\]/g, '\\]');
        i = j + 1;
        res += '[' + stuff + ']';
      }
    } else {
      res += escapeRegExp(c);
    }
  }
  return '^(?:' + res + ')$';
}

/**
 * Shell-style pattern match with Python `fnmatch.fnmatch` semantics
 * (case-sensitive, as on POSIX).
 */
export function fnmatch(name: string, pattern: string): boolean {
  try {
    return new RegExp(fnmatchTranslate(pattern), 's').test(name);
  } catch {
    return false;
  }
}

/** Escape a string for literal use inside a RegExp (Python `re.escape`). */
function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\\/-]/g, '\\$&');
}

/** `os.path.basename` for an already `/`-normalised path (empty for `a/b/`). */
function posixBasename(p: string): string {
  return p.slice(p.lastIndexOf('/') + 1);
}

// ---------------------------------------------------------------------------
// CorpusStats
// ---------------------------------------------------------------------------

/** Constructor options for {@link CorpusStats}. indexing.py:56-60 */
export interface CorpusStatsOptions {
  /** Number of files in corpus (Python `file_count`, default 0). */
  fileCount?: number;
  /** Number of chunks created (Python `chunk_count`, default 0). */
  chunkCount?: number;
  /** Estimated total tokens (Python `total_tokens`, default 0). */
  totalTokens?: number;
  /** ISO timestamp of last indexing (Python `indexed_at`, default None). */
  indexedAt?: string | null;
  /** Path to corpus root (Python `path`, default None). */
  path?: string | null;
}

/** Serialised form produced by `CorpusStats.toDict()`. indexing.py:117-124 */
export interface CorpusStatsDict {
  file_count: number;
  chunk_count: number;
  total_tokens: number;
  indexed_at: string | null;
  path: string | null;
  strategy_recommendation: string;
}

/**
 * Statistics about an indexed corpus.
 *
 * Used for strategy selection and monitoring.
 * Port of `CorpusStats` (indexing.py:41-135).
 */
export class CorpusStats {
  fileCount: number;
  chunkCount: number;
  totalTokens: number;
  indexedAt: string | null;
  path: string | null;

  /**
   * @param options - dataclass fields, all optional. indexing.py:56-60
   */
  constructor(options: CorpusStatsOptions = {}) {
    this.fileCount = options.fileCount ?? 0;
    this.chunkCount = options.chunkCount ?? 0;
    this.totalTokens = options.totalTokens ?? 0;
    this.indexedAt = options.indexedAt ?? null;
    this.path = options.path ?? null;
  }

  /**
   * Recommend retrieval strategy based on corpus size.
   * Port of the `strategy_recommendation` property (indexing.py:62-68).
   */
  get strategyRecommendation(): string {
    const thresholds = Object.keys(STRATEGY_THRESHOLDS)
      .map(Number)
      .sort((a, b) => a - b);
    for (const threshold of thresholds) {
      if (this.fileCount < threshold) {
        return STRATEGY_THRESHOLDS[threshold];
      }
    }
    return DEFAULT_STRATEGY;
  }

  /**
   * Create CorpusStats from a directory scan.
   * Port of `CorpusStats.from_directory` (indexing.py:70-113).
   *
   * @param path - Directory path to scan
   * @param extensions - Optional list of extensions to include
   *   (default: {@link DEFAULT_CORPUS_EXTENSIONS})
   * @returns CorpusStats with file count and token estimate
   */
  static fromDirectory(dirPath: string, extensions: string[] | null = null): CorpusStats {
    const allowed = new Set(extensions ?? DEFAULT_CORPUS_EXTENSIONS);

    let fileCount = 0;
    let totalTokens = 0;

    for (const filePath of walkFiles(dirPath)) {
      const ext = path.extname(filePath).toLowerCase();
      if (allowed.has(ext)) {
        fileCount += 1;
        try {
          const size = fs.statSync(filePath).size;
          // Rough estimate: 4 chars per token
          totalTokens += Math.floor(size / 4);
        } catch {
          // Unreadable file: counted but contributes no tokens (Python `except OSError: pass`)
        }
      }
    }

    return new CorpusStats({
      fileCount,
      totalTokens,
      path: dirPath,
      indexedAt: new Date().toISOString(),
    });
  }

  /** Convert to dictionary. Port of `to_dict` (indexing.py:115-124). */
  toDict(): CorpusStatsDict {
    return {
      file_count: this.fileCount,
      chunk_count: this.chunkCount,
      total_tokens: this.totalTokens,
      indexed_at: this.indexedAt,
      path: this.path,
      strategy_recommendation: this.strategyRecommendation,
    };
  }

  /** Create from dictionary. Port of `from_dict` (indexing.py:126-135). */
  static fromDict(data: Partial<CorpusStatsDict> & Record<string, any>): CorpusStats {
    return new CorpusStats({
      fileCount: data.file_count ?? 0,
      chunkCount: data.chunk_count ?? 0,
      totalTokens: data.total_tokens ?? 0,
      indexedAt: data.indexed_at ?? null,
      path: data.path ?? null,
    });
  }
}

/**
 * Yield every regular file below `root`, recursively (`os.walk` equivalent).
 * A missing or unreadable directory yields nothing, as `os.walk` does.
 */
function* walkFiles(root: string): Generator<string> {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(root, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    const full = path.join(root, entry.name);
    if (entry.isDirectory()) {
      yield* walkFiles(full);
    } else if (entry.isFile()) {
      yield full;
    }
  }
}

// ---------------------------------------------------------------------------
// IndexResult
// ---------------------------------------------------------------------------

/** Constructor options for {@link IndexResult}. indexing.py:152-158 */
export interface IndexResultOptions {
  /** Whether indexing succeeded (Python `success`, default True). */
  success?: boolean;
  /** Number of files indexed (Python `files_indexed`, default 0). */
  filesIndexed?: number;
  /** Number of files skipped as unchanged (Python `files_skipped`, default 0). */
  filesSkipped?: number;
  /** Number of chunks created (Python `chunks_created`, default 0). */
  chunksCreated?: number;
  /** Error messages (Python `errors`, default []). */
  errors?: string[];
  /** Time taken for indexing (Python `duration_seconds`, default 0.0). */
  durationSeconds?: number;
  /** Stats about the indexed corpus (Python `corpus_stats`, default None). */
  corpusStats?: CorpusStats | null;
}

/** Serialised form produced by `IndexResult.toDict()`. indexing.py:167-176 */
export interface IndexResultDict {
  success: boolean;
  files_indexed: number;
  files_skipped: number;
  chunks_created: number;
  total_files: number;
  errors: string[];
  duration_seconds: number;
  corpus_stats: CorpusStatsDict | null;
}

/**
 * Result of an indexing operation.
 * Port of `IndexResult` (indexing.py:138-176).
 */
export class IndexResult {
  success: boolean;
  filesIndexed: number;
  filesSkipped: number;
  chunksCreated: number;
  errors: string[];
  durationSeconds: number;
  corpusStats: CorpusStats | null;

  /**
   * @param options - dataclass fields, all optional. indexing.py:152-158
   */
  constructor(options: IndexResultOptions = {}) {
    this.success = options.success ?? true;
    this.filesIndexed = options.filesIndexed ?? 0;
    this.filesSkipped = options.filesSkipped ?? 0;
    this.chunksCreated = options.chunksCreated ?? 0;
    this.errors = options.errors ?? [];
    this.durationSeconds = options.durationSeconds ?? 0.0;
    this.corpusStats = options.corpusStats ?? null;
  }

  /** Total files processed (indexed + skipped). indexing.py:160-163 */
  get totalFiles(): number {
    return this.filesIndexed + this.filesSkipped;
  }

  /** Convert to dictionary. Port of `to_dict` (indexing.py:165-176). */
  toDict(): IndexResultDict {
    return {
      success: this.success,
      files_indexed: this.filesIndexed,
      files_skipped: this.filesSkipped,
      chunks_created: this.chunksCreated,
      total_files: this.totalFiles,
      errors: this.errors,
      duration_seconds: this.durationSeconds,
      corpus_stats: this.corpusStats ? this.corpusStats.toDict() : null,
    };
  }
}

// ---------------------------------------------------------------------------
// IgnoreMatcher
// ---------------------------------------------------------------------------

/**
 * Matcher for .praisonignore patterns.
 *
 * Supports gitignore-style patterns:
 * - `*` matches any sequence of characters
 * - `**` matches any path segments
 * - `!` negates a pattern
 * - `#` starts a comment
 *
 * Port of `IgnoreMatcher` (indexing.py:179-323).
 */
export class IgnoreMatcher {
  private readonly includePatterns: string[] = [];
  private readonly excludePatterns: string[] = [];

  /**
   * Initialize with patterns. indexing.py:190-208
   *
   * @param patterns - List of gitignore-style patterns (default None)
   */
  constructor(patterns: string[] | null = null) {
    if (patterns) {
      for (const raw of patterns) {
        const pattern = raw.trim();
        if (!pattern || pattern.startsWith('#')) {
          continue;
        }
        if (pattern.startsWith('!')) {
          this.includePatterns.push(pattern.slice(1));
        } else {
          this.excludePatterns.push(pattern);
        }
      }
    }
  }

  /**
   * Check if path should be ignored. Port of `should_ignore` (indexing.py:210-237).
   *
   * @param filePath - Path to check (relative or absolute)
   * @returns True if path should be ignored
   */
  shouldIgnore(filePath: string): boolean {
    // Normalize path
    const normalized = filePath.replace(/\\/g, '/');
    const basename = posixBasename(normalized);

    // Check exclude patterns
    let ignored = false;
    for (const pattern of this.excludePatterns) {
      if (this.matches(normalized, pattern) || this.matches(basename, pattern)) {
        ignored = true;
        break;
      }
    }

    // Check include patterns (negation)
    if (ignored) {
      for (const pattern of this.includePatterns) {
        if (this.matches(normalized, pattern) || this.matches(basename, pattern)) {
          return false;
        }
      }
    }

    return ignored;
  }

  /** Check if path matches pattern. Port of `_matches` (indexing.py:239-269). */
  private matches(filePath: string, pattern: string): boolean {
    // Handle ** for recursive matching
    if (pattern.includes('**')) {
      // Convert gitignore pattern to regex: escape everything, then restore
      // `**` as "anything" and `*` as "anything but a path separator".
      let regexPattern = escapeRegExp(pattern);
      regexPattern = regexPattern.split('\\*\\*').join('.*');
      regexPattern = regexPattern.split('\\*').join('[^/]*');
      // Match anywhere in path
      try {
        return new RegExp(regexPattern).test(filePath);
      } catch {
        return false;
      }
    }

    // Handle trailing slash for directories
    if (pattern.endsWith('/')) {
      const dir = pattern.slice(0, -1);
      return (
        filePath === dir ||
        filePath.startsWith(dir + '/') ||
        ('/' + filePath + '/').includes('/' + dir + '/')
      );
    }

    // Standard fnmatch - check full path and basename
    if (fnmatch(filePath, pattern)) {
      return true;
    }
    if (fnmatch(posixBasename(filePath), pattern)) {
      return true;
    }
    // Also check if pattern matches any path segment
    for (const segment of filePath.split('/')) {
      if (fnmatch(segment, pattern)) {
        return true;
      }
    }
    return false;
  }

  /**
   * Load patterns from file. Port of `from_file` (indexing.py:271-288).
   * An unreadable file yields an empty matcher.
   *
   * @param filepath - Path to .praisonignore file
   */
  static fromFile(filepath: string): IgnoreMatcher {
    let patterns: string[] = [];
    try {
      patterns = fs.readFileSync(filepath, 'utf-8').split(/\r?\n/);
    } catch {
      // Missing/unreadable file: no patterns (Python `except (OSError, IOError): pass`)
    }
    return new IgnoreMatcher(patterns);
  }

  /**
   * Auto-detect and load .praisonignore from directory; also reads .gitignore.
   * Port of `from_directory` (indexing.py:290-323).
   *
   * @param directory - Directory to search
   */
  static fromDirectory(directory: string): IgnoreMatcher {
    const patterns: string[] = [];
    for (const name of ['.praisonignore', '.gitignore']) {
      const candidate = path.join(directory, name);
      if (fs.existsSync(candidate)) {
        try {
          patterns.push(...fs.readFileSync(candidate, 'utf-8').split(/\r?\n/));
        } catch {
          // Unreadable: skip this file
        }
      }
    }
    return new IgnoreMatcher(patterns);
  }
}

// ---------------------------------------------------------------------------
// FileTracker
// ---------------------------------------------------------------------------

/**
 * Record returned by `FileTracker.getFileInfo()` and persisted in the state
 * file. Keys are the Python names (indexing.py:363-368, 382) so state files
 * are interchangeable between runtimes.
 */
export interface FileInfo {
  path: string;
  hash: string;
  /** Modification time in seconds (Python `st_mtime`). */
  mtime: number;
  size: number;
  memory_ids?: string[];
  [key: string]: any;
}

/** Files at or above this size are fingerprinted by mtime+size instead of SHA-256. indexing.py:356 */
const HASH_SIZE_LIMIT = 1024 * 1024; // 1MB

/**
 * Track file hashes and modification times for incremental indexing.
 *
 * Persists state to a JSON file for cross-session tracking.
 * Port of `FileTracker` (indexing.py:326-451).
 */
export class FileTracker {
  private readonly stateFile: string | null;
  private tracked: Record<string, FileInfo> = {};

  /**
   * Initialize tracker. indexing.py:333-341
   *
   * @param stateFile - Path to state file for persistence (default None)
   */
  constructor(stateFile: string | null = null) {
    this.stateFile = stateFile;
  }

  /**
   * Get file information (hash, mtime, size). Port of `get_file_info` (indexing.py:343-368).
   * Throws (like `os.stat`) if the file does not exist.
   *
   * @param filepath - Path to file
   */
  getFileInfo(filepath: string): FileInfo {
    const stat = fs.statSync(filepath);
    const mtime = stat.mtimeMs / 1000;

    // Calculate hash for small files, use mtime+size for large files
    let fileHash: string;
    if (stat.size < HASH_SIZE_LIMIT) {
      fileHash = createHash('sha256').update(fs.readFileSync(filepath)).digest('hex');
    } else {
      // For large files, use mtime + size as proxy
      fileHash = `${mtime}:${stat.size}`;
    }

    return {
      path: filepath,
      hash: fileHash,
      mtime,
      size: stat.size,
    };
  }

  /**
   * Mark file as indexed. Port of `mark_indexed` (indexing.py:370-383).
   *
   * @param filepath - Path to file
   * @param info - File info from `getFileInfo()`
   * @param memoryIds - Optional list of vector-store memory IDs produced for this
   *   file, so a later re-index can delete stale chunks before re-adding.
   */
  markIndexed(filepath: string, info: FileInfo, memoryIds: string[] | null = null): void {
    const record: FileInfo = { ...info };
    if (memoryIds !== null && memoryIds !== undefined) {
      record.memory_ids = [...memoryIds];
    }
    this.tracked[filepath] = record;
  }

  /** Return the memory IDs previously stored for a file (empty if none). indexing.py:385-390 */
  getMemoryIds(filepath: string): string[] {
    const tracked = this.tracked[filepath];
    if (!tracked) {
      return [];
    }
    return [...(tracked.memory_ids ?? [])];
  }

  /**
   * Check if file has changed since last indexing. Port of `has_changed` (indexing.py:392-419).
   *
   * @param filepath - Path to file
   * @returns True if file is new, changed, or no longer readable
   */
  hasChanged(filepath: string): boolean {
    if (!(filepath in this.tracked)) {
      return true;
    }

    try {
      const current = this.getFileInfo(filepath);
      const tracked = this.tracked[filepath];

      // Compare hash
      if (current.hash !== tracked.hash) {
        return true;
      }

      // Compare mtime as backup
      if (current.mtime !== tracked.mtime) {
        return true;
      }

      return false;
    } catch {
      return true;
    }
  }

  /** Paths currently tracked (helper; not in the Python class). */
  trackedPaths(): string[] {
    return Object.keys(this.tracked);
  }

  /**
   * Save state to file. Port of `save` (indexing.py:421-431).
   * Write failures are swallowed, as in Python.
   */
  save(): void {
    if (!this.stateFile) {
      return;
    }

    try {
      const dir = path.dirname(this.stateFile);
      // Python's `os.makedirs(os.path.dirname(...))` fails on a bare filename;
      // `path.dirname` returns "." here, which mkdirSync accepts.
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(this.stateFile, JSON.stringify(this.tracked, null, 2), 'utf-8');
    } catch {
      // Ignore write failures
    }
  }

  /**
   * Load state from file. Port of `load` (indexing.py:433-442).
   * A missing file is a no-op; a corrupt file resets the tracker.
   */
  load(): void {
    if (!this.stateFile || !fs.existsSync(this.stateFile)) {
      return;
    }

    try {
      const parsed = JSON.parse(fs.readFileSync(this.stateFile, 'utf-8'));
      this.tracked = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
    } catch {
      this.tracked = {};
    }
  }

  /** Clear all tracked files and remove the state file. Port of `clear` (indexing.py:444-451). */
  clear(): void {
    this.tracked = {};
    if (this.stateFile && fs.existsSync(this.stateFile)) {
      try {
        fs.unlinkSync(this.stateFile);
      } catch {
        // Ignore removal failures
      }
    }
  }
}
