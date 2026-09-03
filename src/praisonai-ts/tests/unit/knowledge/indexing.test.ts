/**
 * Tests for knowledge/indexing.ts — port of praisonaiagents/knowledge/indexing.py
 */

import { describe, it, expect, beforeEach, afterEach } from '@jest/globals';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import {
  CorpusStats,
  IndexResult,
  IgnoreMatcher,
  FileTracker,
  STRATEGY_THRESHOLDS,
  DEFAULT_STRATEGY,
  estimateTokensSimple,
  fnmatch,
} from '../../../src/knowledge/indexing';

let tmpDir: string;

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'praison-indexing-'));
});

afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

function write(rel: string, content: string): string {
  const full = path.join(tmpDir, rel);
  fs.mkdirSync(path.dirname(full), { recursive: true });
  fs.writeFileSync(full, content, 'utf-8');
  return full;
}

/** The strategy Python's `CorpusStats.strategy_recommendation` returns for a file count. */
function pythonStrategy(fileCount: number): string {
  for (const t of Object.keys(STRATEGY_THRESHOLDS).map(Number).sort((a, b) => a - b)) {
    if (fileCount < t) return STRATEGY_THRESHOLDS[t];
  }
  return DEFAULT_STRATEGY;
}

describe('estimateTokensSimple', () => {
  it('matches Python: 0 for empty, len//4 + 1 otherwise', () => {
    expect(estimateTokensSimple('')).toBe(0);
    expect(estimateTokensSimple('abcd')).toBe(2); // 4//4 + 1
    expect(estimateTokensSimple('abcdefg')).toBe(2); // 7//4 + 1
    expect(estimateTokensSimple('a'.repeat(100))).toBe(26);
  });
});

describe('CorpusStats', () => {
  it('has the Python dataclass defaults', () => {
    const s = new CorpusStats();
    expect(s.fileCount).toBe(0);
    expect(s.chunkCount).toBe(0);
    expect(s.totalTokens).toBe(0);
    expect(s.indexedAt).toBeNull();
    expect(s.path).toBeNull();
  });

  it('strategyRecommendation follows the Python thresholds exactly', () => {
    const cases: Array<[number, string]> = [
      [0, 'direct'],
      [9, 'direct'],
      [10, 'basic'],
      [99, 'basic'],
      [100, 'hybrid'],
      [999, 'hybrid'],
      [1000, 'reranked'],
      [9999, 'reranked'],
      [10000, 'compressed'],
      [99999, 'compressed'],
      [100000, 'hierarchical'],
      [5_000_000, 'hierarchical'],
    ];
    for (const [count, expected] of cases) {
      expect(new CorpusStats({ fileCount: count }).strategyRecommendation).toBe(expected);
      expect(pythonStrategy(count)).toBe(expected);
    }
  });

  it('fromDirectory counts matching files and estimates tokens from byte size', () => {
    write('a.txt', 'x'.repeat(400)); // 100 tokens
    write('sub/b.md', 'y'.repeat(43)); // 43 // 4 = 10 tokens
    write('sub/deep/c.py', 'z'.repeat(8)); // 2 tokens
    write('skip.bin', 'binary'); // not in the default extension list
    write('UPPER.MD', 'q'.repeat(4)); // extension lower-cased -> counts, 1 token

    const stats = CorpusStats.fromDirectory(tmpDir);
    expect(stats.fileCount).toBe(4);
    expect(stats.totalTokens).toBe(100 + 10 + 2 + 1);
    expect(stats.path).toBe(tmpDir);
    expect(stats.chunkCount).toBe(0);
    expect(typeof stats.indexedAt).toBe('string');
    expect(Number.isNaN(Date.parse(stats.indexedAt as string))).toBe(false);
  });

  it('fromDirectory honours an explicit extension list', () => {
    write('a.txt', 'aaaa');
    write('b.md', 'bbbb');
    write('c.log', 'cccc');
    const stats = CorpusStats.fromDirectory(tmpDir, ['.log']);
    expect(stats.fileCount).toBe(1);
    expect(stats.totalTokens).toBe(1);
  });

  it('fromDirectory on a missing directory yields empty stats (os.walk semantics)', () => {
    const stats = CorpusStats.fromDirectory(path.join(tmpDir, 'does-not-exist'));
    expect(stats.fileCount).toBe(0);
    expect(stats.totalTokens).toBe(0);
  });

  it('recommends the same strategy Python would for a small corpus (direct)', () => {
    for (let i = 0; i < 5; i++) write(`f${i}.txt`, 'hello');
    const stats = CorpusStats.fromDirectory(tmpDir);
    expect(stats.fileCount).toBe(5);
    expect(stats.strategyRecommendation).toBe('direct');
    expect(stats.strategyRecommendation).toBe(pythonStrategy(5));
  });

  it('recommends the same strategy Python would for a large corpus (hybrid at >=100 files)', () => {
    for (let i = 0; i < 120; i++) write(`dir${i % 7}/f${i}.md`, `doc ${i}`);
    const stats = CorpusStats.fromDirectory(tmpDir);
    expect(stats.fileCount).toBe(120);
    expect(stats.strategyRecommendation).toBe('hybrid');
    expect(stats.strategyRecommendation).toBe(pythonStrategy(120));
  });

  it('toDict/fromDict round-trip with the Python snake_case keys', () => {
    const s = new CorpusStats({ fileCount: 12, chunkCount: 3, totalTokens: 99, indexedAt: 't', path: '/p' });
    const d = s.toDict();
    expect(d).toEqual({
      file_count: 12,
      chunk_count: 3,
      total_tokens: 99,
      indexed_at: 't',
      path: '/p',
      strategy_recommendation: 'basic',
    });
    const back = CorpusStats.fromDict(d);
    expect(back.fileCount).toBe(12);
    expect(back.chunkCount).toBe(3);
    expect(back.totalTokens).toBe(99);
    expect(back.indexedAt).toBe('t');
    expect(back.path).toBe('/p');
    expect(CorpusStats.fromDict({}).fileCount).toBe(0);
  });
});

describe('IndexResult', () => {
  it('has the Python defaults, computes totalFiles and serialises', () => {
    const r = new IndexResult();
    expect(r.success).toBe(true);
    expect(r.filesIndexed).toBe(0);
    expect(r.filesSkipped).toBe(0);
    expect(r.chunksCreated).toBe(0);
    expect(r.errors).toEqual([]);
    expect(r.durationSeconds).toBe(0);
    expect(r.corpusStats).toBeNull();
    expect(r.toDict().corpus_stats).toBeNull();

    const r2 = new IndexResult({
      filesIndexed: 3,
      filesSkipped: 2,
      chunksCreated: 7,
      errors: ['boom'],
      durationSeconds: 1.5,
      corpusStats: new CorpusStats({ fileCount: 5 }),
    });
    expect(r2.totalFiles).toBe(5);
    const d = r2.toDict();
    expect(d.total_files).toBe(5);
    expect(d.files_indexed).toBe(3);
    expect(d.errors).toEqual(['boom']);
    expect(d.corpus_stats?.file_count).toBe(5);
    expect(d.corpus_stats?.strategy_recommendation).toBe('direct');
  });

  it('gives each instance its own errors array (dataclass default_factory)', () => {
    const a = new IndexResult();
    const b = new IndexResult();
    a.errors.push('x');
    expect(b.errors).toEqual([]);
  });
});

describe('fnmatch (Python fnmatch.fnmatch port)', () => {
  it('matches * ? and [] like Python', () => {
    expect(fnmatch('foo.py', '*.py')).toBe(true);
    expect(fnmatch('a/b/foo.py', '*.py')).toBe(true); // * crosses / in Python fnmatch
    expect(fnmatch('foo.pyc', '*.py')).toBe(false);
    expect(fnmatch('f1', 'f?')).toBe(true);
    expect(fnmatch('f12', 'f?')).toBe(false);
    expect(fnmatch('a.txt', '[ab].txt')).toBe(true);
    expect(fnmatch('c.txt', '[ab].txt')).toBe(false);
    expect(fnmatch('c.txt', '[!ab].txt')).toBe(true);
    expect(fnmatch('x', '[')).toBe(false); // unterminated bracket is literal
    expect(fnmatch('[', '[')).toBe(true);
    expect(fnmatch('a+b', 'a+b')).toBe(true); // regex metachars are literal
    expect(fnmatch('Foo.PY', '*.py')).toBe(false); // case-sensitive like POSIX
  });
});

describe('IgnoreMatcher', () => {
  it('honours gitignore-style patterns and leaves a control file alone', () => {
    const m = new IgnoreMatcher([
      '# a comment',
      '',
      '*.log',
      'node_modules/',
      'build/**',
      'secret_*.txt',
      '!secret_ok.txt',
    ]);
    // extension glob
    expect(m.shouldIgnore('app.log')).toBe(true);
    expect(m.shouldIgnore('logs/deep/app.log')).toBe(true);
    // directory pattern (trailing slash) matches the dir and anything under it
    expect(m.shouldIgnore('node_modules')).toBe(true);
    expect(m.shouldIgnore('node_modules/pkg/index.js')).toBe(true);
    expect(m.shouldIgnore('src/node_modules/pkg/index.js')).toBe(true);
    // ** recursive
    expect(m.shouldIgnore('build/out/main.js')).toBe(true);
    // negation re-includes
    expect(m.shouldIgnore('secret_key.txt')).toBe(true);
    expect(m.shouldIgnore('secret_ok.txt')).toBe(false);
    // controls that must NOT be ignored
    expect(m.shouldIgnore('src/index.ts')).toBe(false);
    expect(m.shouldIgnore('README.md')).toBe(false);
    expect(m.shouldIgnore('logs/notes.txt')).toBe(false);
  });

  it('normalises Windows separators and matches path segments', () => {
    const m = new IgnoreMatcher(['tmp']);
    expect(m.shouldIgnore('a\\tmp\\file.txt')).toBe(true);
    expect(m.shouldIgnore('a/tmpx/file.txt')).toBe(false);
  });

  it('with no patterns ignores nothing', () => {
    expect(new IgnoreMatcher().shouldIgnore('anything.log')).toBe(false);
    expect(new IgnoreMatcher(null).shouldIgnore('x')).toBe(false);
  });

  it('fromFile loads patterns and tolerates a missing file', () => {
    const f = write('.praisonignore', '*.tmp\n# c\n\n!keep.tmp\n');
    const m = IgnoreMatcher.fromFile(f);
    expect(m.shouldIgnore('a.tmp')).toBe(true);
    expect(m.shouldIgnore('keep.tmp')).toBe(false);
    expect(m.shouldIgnore('a.txt')).toBe(false);
    expect(IgnoreMatcher.fromFile(path.join(tmpDir, 'nope')).shouldIgnore('a.tmp')).toBe(false);
  });

  it('fromDirectory merges .praisonignore and .gitignore', () => {
    write('.praisonignore', '*.tmp\n');
    write('.gitignore', 'dist/\n');
    const m = IgnoreMatcher.fromDirectory(tmpDir);
    expect(m.shouldIgnore('a.tmp')).toBe(true);
    expect(m.shouldIgnore('dist/bundle.js')).toBe(true);
    expect(m.shouldIgnore('src/a.ts')).toBe(false);
  });
});

describe('FileTracker', () => {
  it('getFileInfo hashes small files with sha256 and reports mtime/size', () => {
    const f = write('a.txt', 'hello');
    const info = new FileTracker().getFileInfo(f);
    expect(info.path).toBe(f);
    // sha256("hello")
    expect(info.hash).toBe('2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824');
    expect(info.size).toBe(5);
    expect(typeof info.mtime).toBe('number');
    expect(info.mtime).toBeGreaterThan(0);
  });

  it('getFileInfo throws for a missing file like os.stat', () => {
    expect(() => new FileTracker().getFileInfo(path.join(tmpDir, 'missing'))).toThrow();
  });

  it('detects new, changed, unchanged and deleted files across two runs with persisted state', () => {
    const stateFile = path.join(tmpDir, '.praisonai', '.index_state.json');
    const unchanged = write('unchanged.txt', 'same');
    const changed = write('changed.txt', 'v1');
    const deleted = write('deleted.txt', 'bye');

    // Run 1: everything is new
    const run1 = new FileTracker(stateFile);
    run1.load(); // no state file yet: no-op
    for (const f of [unchanged, changed, deleted]) {
      expect(run1.hasChanged(f)).toBe(true);
      run1.markIndexed(f, run1.getFileInfo(f), [`mem-${path.basename(f)}`]);
    }
    run1.save();
    expect(fs.existsSync(stateFile)).toBe(true);
    const persisted = JSON.parse(fs.readFileSync(stateFile, 'utf-8'));
    expect(Object.keys(persisted).sort()).toEqual([changed, deleted, unchanged].sort());
    expect(persisted[changed].memory_ids).toEqual(['mem-changed.txt']);
    expect(persisted[changed].hash).toBeDefined();

    // Mutate the tree between runs
    fs.writeFileSync(changed, 'v2', 'utf-8');
    fs.unlinkSync(deleted);
    const added = write('new.txt', 'fresh');

    // Run 2: a fresh tracker loads persisted state
    const run2 = new FileTracker(stateFile);
    run2.load();
    expect(run2.hasChanged(unchanged)).toBe(false);
    expect(run2.hasChanged(changed)).toBe(true);
    expect(run2.hasChanged(added)).toBe(true); // never tracked
    expect(run2.hasChanged(deleted)).toBe(true); // tracked but gone -> stat fails -> changed
    expect(run2.getMemoryIds(changed)).toEqual(['mem-changed.txt']);
    expect(run2.getMemoryIds(added)).toEqual([]);
    // deleted files are still listed in state until the caller prunes them
    expect(run2.trackedPaths()).toContain(deleted);
  });

  it('hasChanged flags an mtime change even when content hash is identical', () => {
    const f = write('a.txt', 'same');
    const t = new FileTracker();
    t.markIndexed(f, t.getFileInfo(f));
    expect(t.hasChanged(f)).toBe(false);
    const future = new Date(Date.now() + 60_000);
    fs.utimesSync(f, future, future);
    expect(t.hasChanged(f)).toBe(true);
  });

  it('getMemoryIds returns a copy and markIndexed without ids leaves memory_ids unset', () => {
    const f = write('a.txt', 'x');
    const t = new FileTracker();
    t.markIndexed(f, t.getFileInfo(f));
    expect(t.getMemoryIds(f)).toEqual([]);
    t.markIndexed(f, t.getFileInfo(f), ['1', '2']);
    const ids = t.getMemoryIds(f);
    ids.push('3');
    expect(t.getMemoryIds(f)).toEqual(['1', '2']);
  });

  it('save/load are no-ops without a state file; load resets on corrupt JSON', () => {
    const t = new FileTracker();
    expect(() => {
      t.save();
      t.load();
    }).not.toThrow();

    const stateFile = write('state.json', '{not json');
    const t2 = new FileTracker(stateFile);
    t2.load();
    expect(t2.trackedPaths()).toEqual([]);
  });

  it('clear empties the tracker and removes the state file', () => {
    const stateFile = path.join(tmpDir, 'state.json');
    const f = write('a.txt', 'x');
    const t = new FileTracker(stateFile);
    t.markIndexed(f, t.getFileInfo(f));
    t.save();
    expect(fs.existsSync(stateFile)).toBe(true);
    t.clear();
    expect(t.trackedPaths()).toEqual([]);
    expect(fs.existsSync(stateFile)).toBe(false);
    expect(t.hasChanged(f)).toBe(true);
  });
});
