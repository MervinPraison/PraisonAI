/**
 * Child processes that run model-chosen code or commands get an allowlisted
 * environment, not the host's full `process.env`.
 *
 * Every secret below is a fake set inside this test; no real value is read.
 */
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { buildChildEnv } from '../../../src/utils/child-env';
import { createSandboxRunner, defaultSandboxConfig } from '../../../src/agent/features/sandbox';
import { createSubprocessExecutor } from '../../../src/agent/code';

const FAKE = {
  OPENAI_API_KEY: 'sk-fake-openai',
  GITHUB_TOKEN: 'ghp_fake',
  DATABASE_URL: 'postgres://user:fake@db/x',
  MY_ALLOWED_VAR: 'allowed-value',
  PRAISONAI_SHELL_ENV_ALLOWLIST: 'MY_ALLOWED_VAR',
};
const PRINT_ENV = 'console.log(JSON.stringify(process.env))';

describe('child process environment', () => {
  const saved: Record<string, string | undefined> = {};
  beforeEach(() => {
    for (const [k, v] of Object.entries(FAKE)) {
      saved[k] = process.env[k];
      process.env[k] = v;
    }
  });
  afterEach(() => {
    for (const k of Object.keys(FAKE)) {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
  });

  const expectFiltered = (env: Record<string, string>, explicit: Record<string, string>) => {
    expect(env.OPENAI_API_KEY).toBeUndefined();
    expect(env.GITHUB_TOKEN).toBeUndefined();
    expect(env.DATABASE_URL).toBeUndefined();
    expect(env.PATH).toBe(process.env.PATH);
    expect(env.MY_ALLOWED_VAR).toBe('allowed-value');
    for (const [k, v] of Object.entries(explicit)) expect(env[k]).toBe(v);
  };

  it('buildChildEnv keeps basics, the opt-in allowlist and explicit vars only', () => {
    const env = buildChildEnv(
      { OPENAI_API_KEY: 'explicit-wins', EXTRA: '1' },
      { Path: '/bin', LC_ALL: 'C', SECRET_KEY: 'x', MY_ALLOWED_VAR: 'y', PRAISONAI_SHELL_ENV_ALLOWLIST: ' my_allowed_var ,' },
    );
    expect(env).toEqual({ Path: '/bin', LC_ALL: 'C', MY_ALLOWED_VAR: 'y', OPENAI_API_KEY: 'explicit-wins', EXTRA: '1' });
  });

  it('Agent sandbox subprocess runner does not pass host secrets to the child', async () => {
    const config = { ...defaultSandboxConfig(), env: { SANDBOX_VAR: 'from-config' } };
    const result = await createSandboxRunner(config).execute(PRINT_ENV, { language: 'javascript', config });
    expect(result.exitCode).toBe(0);
    expectFiltered(JSON.parse(result.stdout), { SANDBOX_VAR: 'from-config' });
  });

  it('CodeAgent subprocess executor does not pass host secrets to the child', async () => {
    const workingDirectory = fs.mkdtempSync(path.join(os.tmpdir(), 'praison-child-env-'));
    try {
      const result = await createSubprocessExecutor()(PRINT_ENV, 'javascript', {
        sandbox: true,
        timeout: 30,
        workingDirectory,
        environment: { CODE_VAR: 'from-context' },
        maxOutputLength: 1_000_000,
      });
      expect(result.success).toBe(true);
      expectFiltered(JSON.parse(result.output), { CODE_VAR: 'from-context' });
    } finally {
      fs.rmSync(workingDirectory, { recursive: true, force: true });
    }
  });

  it('guard: every spawn of a model-chosen command builds its env with buildChildEnv', () => {
    const src = path.join(__dirname, '../../../src');
    // Operator-run launches (external agent CLIs, the `sandbox` CLI command,
    // LocalCompute which documents that it does not sandbox, git) are out of scope.
    const operatorRun = new Set([
      'cli/features/external-agents.ts',
      'cli/features/sandbox-executor.ts',
      'cli/features/git-integration.ts',
      'compute/local.ts',
    ]);
    const modelRun = ['agent/features/sandbox.ts', 'agent/code.ts', 'tools/utility-tools.ts'];
    const walk = (dir: string): string[] =>
      fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
        e.isDirectory() ? walk(path.join(dir, e.name)) : e.name.endsWith('.ts') ? [path.join(dir, e.name)] : []);
    const spawning = walk(src)
      .map((f) => path.relative(src, f).split(path.sep).join('/'))
      .filter((rel) => /child_process|'child', '_process'|'ode:child_process'/.test(fs.readFileSync(path.join(src, rel), 'utf8')))
      .filter((rel) => !operatorRun.has(rel) && rel !== 'tools/builtins/code-mode.ts');
    expect(spawning.sort()).toEqual([...modelRun].sort());
    for (const rel of modelRun) {
      const text = fs.readFileSync(path.join(src, rel), 'utf8');
      expect({ rel, spreadsHostEnv: /\.\.\.process\.env/.test(text) }).toEqual({ rel, spreadsHostEnv: false });
      const spawns = (text.match(/\bspawn(Sync)?\(/g) ?? []).length;
      const built = (text.match(/env: buildChildEnv\(/g) ?? []).length;
      expect({ rel, spawns, built }).toEqual({ rel, spawns, built: spawns });
    }
  });
});
