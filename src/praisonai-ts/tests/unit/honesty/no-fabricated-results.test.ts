/**
 * Regression tests for code paths that used to return fabricated results and
 * report success.
 *
 * Every test here fails against the pre-fix implementation. In particular the
 * embedding test asserts *value* identity for identical input, not just that an
 * array of the right length came back -- a shape assertion passed happily
 * against `Math.random()` vectors.
 */

import { describe, it, expect, jest, beforeEach, afterEach } from '@jest/globals';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

// ---------------------------------------------------------------------------
// 1. EmbeddingAgent must return real embeddings, never random vectors
// ---------------------------------------------------------------------------

jest.mock('../../../src/llm/embeddings', () => {
  // A deterministic stand-in for a provider: the same text always maps to the
  // same vector, which is the property every real embedding model has and the
  // one the old `Math.random()` implementation could not satisfy.
  const fake = (text: string) => {
    const vec = new Array(8).fill(0);
    for (let i = 0; i < text.length; i++) {
      vec[i % 8] += text.charCodeAt(i) / 255;
    }
    return vec;
  };
  return {
    __esModule: true,
    embed: jest.fn(async (text: string) => ({ embedding: fake(text), usage: { tokens: 3 } })),
    embedMany: jest.fn(async (texts: string[]) => ({
      embeddings: texts.map(fake),
      usage: { tokens: 3 * texts.length },
    })),
  };
});

import { EmbeddingAgent } from '../../../src/agent/embedding';
import * as llmEmbeddings from '../../../src/llm/embeddings';

describe('EmbeddingAgent (no random vectors)', () => {
  it('returns identical vectors for identical text', async () => {
    const agent = new EmbeddingAgent({ verbose: false });
    const a = await agent.embed('the quick brown fox');
    const b = await agent.embed('the quick brown fox');

    expect(a.embedding).toEqual(b.embedding);
    // cosine of a vector with itself is 1; the random implementation scored ~0.
    expect(agent.cosineSimilarity(a.embedding, b.embedding)).toBeCloseTo(1, 10);
  });

  it('returns different vectors for different text', async () => {
    const agent = new EmbeddingAgent({ verbose: false });
    const a = await agent.embed('cats');
    const b = await agent.embed('quantum chromodynamics');
    expect(a.embedding).not.toEqual(b.embedding);
  });

  it('delegates to the real provider rather than generating vectors locally', async () => {
    const agent = new EmbeddingAgent({ verbose: false, model: 'text-embedding-3-large' });
    await agent.embed('hello');
    expect(llmEmbeddings.embed).toHaveBeenCalledWith('hello', { model: 'text-embedding-3-large' });
  });

  it('propagates provider failures instead of falling back to noise', async () => {
    (llmEmbeddings.embed as jest.Mock).mockImplementationOnce(async () => {
      throw new Error('OPENAI_API_KEY is not set');
    });
    const agent = new EmbeddingAgent({ verbose: false });
    await expect(agent.embed('hello')).rejects.toThrow('OPENAI_API_KEY is not set');
  });

  it('embedMany is consistent with embed for the same text', async () => {
    const agent = new EmbeddingAgent({ verbose: false });
    const single = await agent.embed('shared text');
    const batch = await agent.embedMany(['shared text', 'other']);
    expect(batch.embeddings[0]).toEqual(single.embedding);
    expect(batch.embeddings[0]).not.toEqual(batch.embeddings[1]);
  });
});

// ---------------------------------------------------------------------------
// 2. createMCP must not return an empty client when the server is unreachable
// ---------------------------------------------------------------------------

describe('createMCP (no silent empty client)', () => {
  it('rejects when the stdio server binary does not exist', async () => {
    const { createMCP } = await import('../../../src/ai/mcp');
    await expect(
      createMCP({
        transport: {
          type: 'stdio',
          command: '/nonexistent/praisonai-mcp-server-does-not-exist',
          args: [],
        },
      })
    ).rejects.toBeDefined();
  }, 30000);

  it('rejects on an unknown transport type instead of returning a client', async () => {
    const { createMCP } = await import('../../../src/ai/mcp');
    await expect(
      createMCP({ transport: { type: 'carrier-pigeon' } as any })
    ).rejects.toThrow(/Unknown transport type/);
  });
});

// ---------------------------------------------------------------------------
// 3. CodeAgent must not reach in-process eval by flipping `sandbox`
// ---------------------------------------------------------------------------

describe('CodeAgent.execute (no eval by flag flip)', () => {
  const PROBE = '__praisonai_eval_probe__';

  afterEach(() => {
    delete (globalThis as any)[PROBE];
  });

  it('does not eval JavaScript in-process when sandbox is false', async () => {
    const { CodeAgent } = await import('../../../src/agent/code');
    const agent = new CodeAgent({
      verbose: false,
      code: { sandbox: false, allowedLanguages: ['javascript'] },
    });

    const result = await agent.execute(`globalThis['${PROBE}'] = true; 'pwned'`, 'javascript');

    expect((globalThis as any)[PROBE]).toBeUndefined();
    expect(result.success).toBe(false);
    expect(result.output).toBe('');
    expect(result.error).toMatch(/No code executor is configured/);
  });

  it('does not eval when sandbox is true either', async () => {
    const { CodeAgent } = await import('../../../src/agent/code');
    const agent = new CodeAgent({
      verbose: false,
      code: { sandbox: true, allowedLanguages: ['javascript'] },
    });
    const result = await agent.execute(`globalThis['${PROBE}'] = true; 1`, 'javascript');
    expect((globalThis as any)[PROBE]).toBeUndefined();
    expect(result.success).toBe(false);
  });

  it('runs code only through an explicitly supplied executor', async () => {
    const { CodeAgent } = await import('../../../src/agent/code');
    const executor = jest.fn(async () => ({
      success: true,
      output: '42',
      exitCode: 0,
      executionTime: 0.01,
    }));

    const agent = new CodeAgent({
      verbose: false,
      // `as any`: keeps this file compiling when the fix is reverted for
      // mutation testing, so the gate fails behaviourally rather than at tsc.
      code: { executor, allowedLanguages: ['python'] } as any,
    });

    const result = await agent.execute('print(42)', 'python');
    expect(result.success).toBe(true);
    expect(result.output).toBe('42');
    expect(executor).toHaveBeenCalledTimes(1);
  });

  it('createSubprocessExecutor runs code out of process, not in this one', async () => {
    const mod: any = await import('../../../src/agent/code');
    const { CodeAgent, createSubprocessExecutor } = mod;
    if (typeof createSubprocessExecutor !== 'function') {
      throw new Error('createSubprocessExecutor is not exported');
    }
    const agent = new CodeAgent({
      verbose: false,
      code: {
        executor: createSubprocessExecutor(),
        allowedLanguages: ['javascript'],
        timeout: 20,
      } as any,
    });

    const result = await agent.execute(
      `globalThis['${PROBE}'] = true; console.log('from child');`,
      'javascript'
    );

    expect(result.success).toBe(true);
    expect(result.output).toContain('from child');
    // The child mutated its own global, never this process's.
    expect((globalThis as any)[PROBE]).toBeUndefined();
  }, 30000);
});

// ---------------------------------------------------------------------------
// 4. OCRAgent must not fabricate an extraction
// ---------------------------------------------------------------------------

describe('OCRAgent.extract (no fabricated text)', () => {
  it('throws instead of returning placeholder text', async () => {
    const { OCRAgent } = await import('../../../src/agent/ocr');
    const agent = new OCRAgent({ verbose: false });
    await expect(agent.extract('https://example.com/doc.pdf')).rejects.toThrow(
      /no extractor configured/i
    );
  });

  it('never returns text containing an "requires API integration" placeholder', async () => {
    const { OCRAgent } = await import('../../../src/agent/ocr');
    const agent = new OCRAgent({ verbose: false });
    const result = await agent.extract('x.png').catch((e: Error) => e);
    expect(result).toBeInstanceOf(Error);
    expect(String(result)).not.toMatch(/\[OCR extraction from/);
  });

  it('uses an explicitly supplied extractor', async () => {
    const { OCRAgent } = await import('../../../src/agent/ocr');
    const agent = new OCRAgent({
      verbose: false,
      extractor: async ({ source }: { source: string }) => ({
        text: `real text for ${source}`,
        pages: [{ index: 0, markdown: `real text for ${source}` }],
      }),
    } as any);
    const result = await agent.extract('doc.pdf');
    expect(result.text).toBe('real text for doc.pdf');
    expect(await agent.read('doc.pdf')).toBe('real text for doc.pdf');
  });
});

// ---------------------------------------------------------------------------
// 5. Plugin discovery must actually discover
// ---------------------------------------------------------------------------

describe('PluginManager discovery (not a no-op)', () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'praisonai-plugin-honesty-'));
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
    delete process.env.PRAISONAI_ALLOW_PLUGIN_DISCOVERY;
  });

  const writePlugin = (dir: string, file: string, name: string) => {
    const pluginModule = path.resolve(__dirname, '../../../src/plugins/index.ts');
    fs.writeFileSync(
      path.join(dir, file),
      `const { Plugin } = require(${JSON.stringify(pluginModule)});\n` +
        `module.exports.createPlugin = () => new Plugin({ name: ${JSON.stringify(name)} });\n`
    );
  };

  it('loadFromDirectory returns the number of plugins loaded and registers them', async () => {
    const { PluginManager } = await import('../../../src/plugins/index');
    writePlugin(tmpDir, 'alpha.js', 'alpha');
    writePlugin(tmpDir, 'beta.js', 'beta');
    writePlugin(tmpDir, '_private.js', 'private');

    const manager = new PluginManager();
    const count = manager.loadFromDirectory(tmpDir);

    expect(count).toBe(2);
    expect(manager.listPlugins().map((p) => p.name).sort()).toEqual(['alpha', 'beta']);
    expect(manager.get('private')).toBeUndefined();
  });

  it('loadFromDirectory returns 0 for a directory that does not exist', async () => {
    const { PluginManager } = await import('../../../src/plugins/index');
    expect(new PluginManager().loadFromDirectory(path.join(tmpDir, 'nope'))).toBe(0);
  });

  it('autoDiscoverPlugins returns a count and stays opt-in', async () => {
    const { PluginManager } = await import('../../../src/plugins/index');
    const manager = new PluginManager();

    delete process.env.PRAISONAI_ALLOW_PLUGIN_DISCOVERY;
    expect(manager.autoDiscoverPlugins()).toBe(0);

    const projectDir = path.join(process.cwd(), '.praisonai', 'plugins');
    const preexisting = fs.existsSync(projectDir);
    try {
      fs.mkdirSync(projectDir, { recursive: true });
      writePlugin(projectDir, 'discovered-by-test.js', 'discovered-by-test');

      process.env.PRAISONAI_ALLOW_PLUGIN_DISCOVERY = 'true';
      const count = manager.autoDiscoverPlugins();

      expect(typeof count).toBe('number');
      expect(count).toBeGreaterThanOrEqual(1);
      expect(manager.get('discovered-by-test')).toBeDefined();
    } finally {
      fs.rmSync(path.join(projectDir, 'discovered-by-test.js'), { force: true });
      if (!preexisting) {
        fs.rmSync(path.join(process.cwd(), '.praisonai'), { recursive: true, force: true });
      }
    }
  });
});
