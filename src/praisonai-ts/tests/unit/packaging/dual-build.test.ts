/**
 * Dual ESM+CJS build — behavioural packaging tests.
 *
 * These tests exercise the *emitted* build output, not just declarations, to
 * guard the concrete regression in the issue: a CJS-only build downlevels every
 * `await import()` into a `require()`, which browser/React-Native bundlers cannot
 * resolve. The dual ESM build must instead preserve dynamic `import()` so it
 * survives as a lazy chunk.
 *
 * The tests build the ESM output on demand (idempotent) and then:
 *   1. Assert emitted ESM modules keep `import(` (not `require(`) for the lazy
 *      boundaries their source used — this FAILS on the old CJS-only build.
 *   2. Actually load the ESM entry point via native dynamic import() and
 *      construct an Agent — proving the entry works, not merely that it exists.
 */

import { execFileSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { pathToFileURL } from 'url';

const PKG_ROOT = path.resolve(__dirname, '..', '..', '..');
const ESM_DIR = path.join(PKG_ROOT, 'dist', 'esm');
const ESM_ENTRY = path.join(ESM_DIR, 'index.js');

function buildDist(): void {
  // Always rebuild both CJS and ESM so the suite validates the CURRENT sources
  // and shim — never stale artifacts from an earlier revision. The ESM shim also
  // repoints internal relative require() calls at the mirrored CJS dist/, so the
  // CJS build must exist first (npm run build runs build:cjs then build:esm).
  execFileSync('npm', ['run', 'build'], {
    cwd: PKG_ROOT,
    stdio: 'inherit',
  });
}

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full));
    else if (entry.isFile() && full.endsWith('.js')) out.push(full);
  }
  return out;
}

describe('praisonai dual ESM+CJS packaging', () => {
  beforeAll(() => {
    buildDist();
  }, 300000);

  it('emits an ESM entry point and marks dist/esm as a module', () => {
    expect(fs.existsSync(ESM_ENTRY)).toBe(true);
    const esmPkg = JSON.parse(
      fs.readFileSync(path.join(ESM_DIR, 'package.json'), 'utf8')
    );
    expect(esmPkg.type).toBe('module');
  });

  it('preserves dynamic import() in emitted ESM instead of downleveling to require()', () => {
    // Pick a representative module whose source uses `await import(`.
    // simple.ts (the Agent) uses lazy dynamic imports; its ESM output must keep them.
    const simpleEsm = path.join(ESM_DIR, 'agent', 'simple.js');
    expect(fs.existsSync(simpleEsm)).toBe(true);

    const code = fs.readFileSync(simpleEsm, 'utf8');

    // The behavioural guarantee: dynamic import() survives (lazy chunk for bundlers).
    expect(code).toMatch(/\bimport\s*\(/);

    // And it was NOT downleveled into a synchronous require() at those sites,
    // which is exactly what the CJS-only build produced and what browser/RN
    // bundlers choke on. Any require() present must come only from the shim
    // banner (createRequire), never as `Promise.resolve().then(() => require(`.
    expect(code).not.toMatch(/Promise\.resolve\(\)\.then\([^)]*require\(/);
    expect(code).not.toMatch(/=\s*require\(/);
  });

  it('rewrites relative specifiers to explicit .js paths for native ESM resolution', () => {
    const files = walk(ESM_DIR).filter((f) => !f.endsWith('package.json'));
    // Scan a bounded sample for speed; assert no bare extensionless relative
    // import survives (Node's ESM resolver requires explicit extensions).
    const offenders: string[] = [];
    for (const file of files) {
      const code = fs.readFileSync(file, 'utf8');
      const badFrom = /(?:import|export)[\s\S]*?from\s*['"](\.[^'"]*?)(?<!\.js)(?<!\.json)(?<!\/index)['"]/.test(
        code
      );
      // Only flag if it's a relative path with no extension at all.
      const m = code.match(/from\s*['"](\.[^'"]+)['"]/g) || [];
      for (const spec of m) {
        const inner = spec.replace(/from\s*['"]/, '').replace(/['"]$/, '');
        if (
          (inner.startsWith('./') || inner.startsWith('../')) &&
          !/\.[a-zA-Z0-9]+$/.test(inner)
        ) {
          offenders.push(`${path.relative(ESM_DIR, file)}: ${inner}`);
        }
      }
      void badFrom;
    }
    expect(offenders).toEqual([]);
  });

  it('loads the ESM entry in native Node ESM and constructs an Agent', () => {
    // Run in a real child Node process so ts-jest cannot rewrite the dynamic
    // import() into a require(). This proves the *published ESM* actually works
    // under native ESM resolution, not merely that a symbol is declared.
    const entryUrl = pathToFileURL(ESM_ENTRY).href;
    const script = [
      `const { Agent } = await import(${JSON.stringify(entryUrl)});`,
      `if (typeof Agent !== 'function') { console.error('NO_AGENT'); process.exit(2); }`,
      `const a = new Agent({ instructions: 'hi', sessionId: 'packaging-esm-test' });`,
      `if (a.getSessionId() !== 'packaging-esm-test') { console.error('BAD_SESSION'); process.exit(3); }`,
      `console.log('ESM_OK');`,
    ].join('\n');

    const scriptFile = path.join(
      fs.mkdtempSync(path.join(os.tmpdir(), 'praison-esm-')),
      'load.mjs'
    );
    fs.writeFileSync(scriptFile, script);

    const out = execFileSync(process.execPath, [scriptFile], {
      cwd: PKG_ROOT,
      encoding: 'utf8',
    });
    expect(out).toContain('ESM_OK');
  }, 120000);

  it('repoints internal relative require() at the CommonJS dist copy (not ESM)', () => {
    // tsc leaves explicit require('./x') in ESM output. Under native ESM those
    // would resolve to type:module siblings and throw ERR_REQUIRE_ESM on Node <22.
    // The shim must repoint every internal relative require at the mirrored CJS
    // file under dist/, i.e. the resolved target must live OUTSIDE dist/esm.
    const files = walk(ESM_DIR);
    const offenders: string[] = [];
    for (const file of files) {
      const code = fs.readFileSync(file, 'utf8');
      const requires = code.match(/require\(\s*['"](\.[^'"]+)['"]\s*\)/g) || [];
      for (const req of requires) {
        const spec = req.replace(/^require\(\s*['"]/, '').replace(/['"]\s*\)$/, '');
        const target = path.resolve(path.dirname(file), spec);
        const rel = path.relative(ESM_DIR, target);
        if (!rel.startsWith('..') && !path.isAbsolute(rel)) {
          offenders.push(`${path.relative(ESM_DIR, file)}: ${spec}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it('resolves documented deep-import subpaths under native ESM', () => {
    // The exports map must not hide public subpaths documented in JSDoc
    // (praisonai/ai, praisonai/tools, praisonai/integrations/*). Resolve them via
    // the built ESM files directly (the published paths those subpaths map to).
    const subpaths = [
      path.join(ESM_DIR, 'ai', 'index.js'),
      path.join(ESM_DIR, 'tools', 'index.js'),
      path.join(ESM_DIR, 'integrations', 'slack.js'),
    ];
    const script = subpaths
      .map((p) => `await import(${JSON.stringify(pathToFileURL(p).href)});`)
      .concat([`console.log('SUBPATHS_OK');`])
      .join('\n');

    const scriptFile = path.join(
      fs.mkdtempSync(path.join(os.tmpdir(), 'praison-subpath-')),
      'load.mjs'
    );
    fs.writeFileSync(scriptFile, script);

    const out = execFileSync(process.execPath, [scriptFile], {
      cwd: PKG_ROOT,
      encoding: 'utf8',
    });
    expect(out).toContain('SUBPATHS_OK');
  }, 120000);
});

/**
 * The published `praisonai/mobile` entry must be buildable for the WebView floor
 * the mobile app declares (Android minSdkVersion 26 => Chrome 58).
 *
 * The shim's createRequire banner is a top-level await, which esbuild cannot
 * lower for chrome58 and refuses outright. Three files on the mobile graph used
 * to earn that banner through a bare require() inside otherwise lazy provider
 * loaders; the sources now import statically, so the built files need no
 * banner and the entry bundles at the floor. Both halves are asserted here
 * against the freshly built dist, because `npm test` runs in Node where a
 * top-level await is perfectly fine and nothing else would notice.
 */
describe('praisonai/mobile entry has no top-level await on its graph', () => {
  // The three built files that carried the banner (git log -S__praisonMod).
  const MOBILE_GRAPH_FILES = [
    'llm/backend-resolver.js',
    'llm/providers/ai-sdk/index.js',
    'llm/providers/registry.js',
  ];

  // Mechanical criterion, identical to:
  //   grep -l "__praisonMod" dist/esm/llm/backend-resolver.js \
  //     dist/esm/llm/providers/ai-sdk/index.js dist/esm/llm/providers/registry.js
  // printing nothing. '__praisonMod' is the first binding of the banner; the
  // second assertion is the banner-independent marker esm-shim-banner.test.ts
  // uses, so a renamed banner still fails here.
  it('emits the three former banner files with no createRequire banner', () => {
    const bannered = MOBILE_GRAPH_FILES.filter((rel) => {
      const code = fs.readFileSync(path.join(ESM_DIR, rel), 'utf8');
      return code.includes('__praisonMod') || code.includes('const require =');
    });
    expect(bannered).toEqual([]);
  });

  it('has no bare require()/__dirname left in the sources the shim would banner', () => {
    // The emit-time decision is needsCjsBanner() over the emitted JS; tsc's ESM
    // emit neither adds nor removes require() calls, so the same detector over
    // the TypeScript source is the build-independent form of the check above.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { needsCjsBanner } = require('../../../scripts/esm-shim.js');
    const SRC = path.join(PKG_ROOT, 'src');
    const offenders = MOBILE_GRAPH_FILES.map((rel) => rel.replace(/\.js$/, '.ts')).filter((rel) =>
      needsCjsBanner(fs.readFileSync(path.join(SRC, rel), 'utf8'))
    );
    expect(offenders).toEqual([]);
  });

  it('bundles dist/esm/mobile.js for chrome58 (scripts/webview-gate.mjs floor check)', () => {
    // The gate owns the esbuild configuration (browser platform, bare specifiers
    // external) and the floor target; run it rather than restate it. It exits
    // non-zero on any failure, which execFileSync turns into a thrown error
    // carrying esbuild's own diagnosis (file:line of the top-level await).
    const out = execFileSync(process.execPath, ['scripts/webview-gate.mjs'], {
      cwd: PKG_ROOT,
      encoding: 'utf8',
    });
    expect(out).toContain('OK   dist/esm/mobile.js: bundles for chrome58');
    expect(out).toContain('OK   dist/esm/mobile.js: loadable in a webview');
  }, 120000);
});
