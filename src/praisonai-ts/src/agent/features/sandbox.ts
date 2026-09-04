/**
 * Sandboxed code execution (Python parity: `Agent(sandbox=...)`,
 * `agent/sandbox_mixin.py` `SandboxMixin`, `sandbox/config.py`,
 * `sandbox/security.py`).
 *
 * `sandbox: true` gives the agent a subprocess sandbox; a config object names
 * a different one. Two things then become true of `agent.executeCode()`:
 *
 * 1. The code is analysed BEFORE it runs, and the warnings travel with the
 *    result. Python's note applies here too -- the analysis is best-effort
 *    static pattern matching for the operator's awareness; the sandbox is
 *    what actually isolates.
 * 2. Without a sandbox configured (and no per-call `runIn`), the call fails
 *    with an error that names both ways to fix it, rather than quietly
 *    running the code in this process.
 *
 * The runner is an injectable interface. Only `subprocess` ships here;
 * `docker`, `e2b` and friends are provider integrations a host registers with
 * {@link registerSandboxRunner}, and naming one that is not registered fails
 * loudly instead of silently downgrading to local execution.
 */

/** Python `SandboxConfig` (the subset the Agent needs). */
export interface SandboxConfig {
  sandboxType: string;
  image: string;
  workingDir: string;
  env: Record<string, string>;
  autoCleanup: boolean;
  persistFiles: boolean;
  /** Seconds a single execution may take. */
  timeout: number;
  metadata: Record<string, unknown>;
}

/** Python's `SandboxConfig` defaults (`sandbox/config.py`). */
export function defaultSandboxConfig(sandboxType: string = 'subprocess'): SandboxConfig {
  return {
    sandboxType,
    image: 'python:3.12-slim',
    workingDir: '/workspace',
    env: {},
    autoCleanup: true,
    persistFiles: false,
    timeout: 30,
    metadata: {},
  };
}

/** Python `SecurityWarning`. */
export interface SecurityWarning {
  pattern: string;
  message: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  lineNumber?: number;
  context?: string;
}

/** Python `SandboxResult` (the fields the Agent surfaces). */
export interface SandboxResult {
  success: boolean;
  stdout: string;
  stderr: string;
  exitCode: number;
  metadata?: Record<string, unknown>;
}

/** Anything that can run code somewhere isolated. */
export interface SandboxRunner {
  readonly sandboxType: string;
  execute(code: string, options: { language: string; config: SandboxConfig }): Promise<SandboxResult>;
}

type PatternRule = [RegExp, string, SecurityWarning['severity']];

/** Python `DANGEROUS_PATTERNS`. */
const PYTHON_PATTERNS: PatternRule[] = [
  [/import\s+os\s*;?\s*os\.system/, 'Direct system command execution via os.system', 'high'],
  [/subprocess\.call.*shell\s*=\s*True/, 'Shell injection risk with subprocess', 'high'],
  [/subprocess\.run.*shell\s*=\s*True/, 'Shell injection risk with subprocess', 'high'],
  [/subprocess\.Popen.*shell\s*=\s*True/, 'Shell injection risk with subprocess', 'high'],
  [/__import__\(['"]os['"]\)/, 'Dynamic import of os module', 'medium'],
  [/eval\s*\(/, 'Dynamic code execution with eval()', 'critical'],
  [/exec\s*\(/, 'Dynamic code execution with exec()', 'critical'],
  [/compile\s*\(.*exec/, 'Code compilation for execution', 'high'],
  [/open\s*\(.*['"]\/etc/, 'Access to system configuration files', 'medium'],
  [/open\s*\(.*['"]\/root/, 'Access to root directory', 'high'],
  [/open\s*\(.*['"]\/home/, 'Access to user directories', 'medium'],
  [/shutil\.rmtree/, 'Recursive directory deletion', 'high'],
  [/os\.remove\s*\(/, 'File deletion', 'medium'],
  [/os\.unlink\s*\(/, 'File deletion', 'medium'],
  [/socket\.socket/, 'Direct socket creation', 'medium'],
  [/urllib\.request/, 'HTTP requests via urllib', 'low'],
  [/requests\./, 'HTTP requests via requests library', 'low'],
  [/os\.fork\s*\(/, 'Process forking', 'high'],
  [/multiprocessing\./, 'Multiprocessing usage', 'medium'],
  [/sys\.modules/, 'Module manipulation', 'high'],
  [/__builtins__/, 'Access to builtin functions', 'high'],
  [/while\s+True:/, 'Infinite loop (potential DoS)', 'medium'],
];

/** Python `_check_bash_patterns`. */
const BASH_PATTERNS: PatternRule[] = [
  [/rm\s+-rf\s+\//i, 'Recursive deletion of root directory', 'critical'],
  [/rm\s+-rf\s+\*/i, 'Recursive deletion with wildcard', 'high'],
  [/>\s*\/dev\/sd[a-z]/i, 'Direct disk device access', 'critical'],
  [/dd\s+if=.*of=/i, 'Low-level disk operations', 'high'],
  [/mkfs\./i, 'Filesystem creation', 'critical'],
  [/fdisk/i, 'Disk partitioning', 'critical'],
  [/shutdown/i, 'System shutdown', 'high'],
  [/reboot/i, 'System reboot', 'high'],
  [/chmod\s+777/i, 'Overly permissive file permissions', 'medium'],
  [/curl.*\|\s*bash/i, 'Piped execution from network', 'high'],
  [/wget.*\|\s*bash/i, 'Piped execution from network', 'high'],
];

/** Python `_check_generic_patterns`. */
const GENERIC_PATTERNS: PatternRule[] = [
  [/eval\s*\(/i, 'Dynamic code execution', 'critical'],
  [/exec\s*\(/i, 'Dynamic code execution', 'high'],
  [/system\s*\(/i, 'System command execution', 'high'],
  [/shell\s*\(/i, 'Shell command execution', 'high'],
];

function scan(code: string, rules: readonly PatternRule[]): SecurityWarning[] {
  const warnings: SecurityWarning[] = [];
  const lines = code.split('\n');
  for (let i = 0; i < lines.length; i++) {
    for (const [pattern, message, severity] of rules) {
      if (pattern.test(lines[i])) {
        warnings.push({
          pattern: pattern.source,
          message,
          severity,
          lineNumber: i + 1,
          context: lines[i].trim(),
        });
      }
    }
  }
  return warnings;
}

/**
 * Static analysis of code about to be sandboxed (Python `check_code_safety`).
 * Warnings only: the sandbox provides the real isolation.
 */
export function checkCodeSafety(code: string, language: string = 'python'): SecurityWarning[] {
  if (language === 'python') return scan(code, PYTHON_PATTERNS);
  if (language === 'bash' || language === 'sh' || language === 'shell') return scan(code, BASH_PATTERNS);
  return scan(code, GENERIC_PATTERNS);
}

/** Python `format_warnings`. */
export function formatWarnings(warnings: readonly SecurityWarning[]): string {
  if (warnings.length === 0) return 'No security issues detected.';
  const bySeverity: Record<string, SecurityWarning[]> = { critical: [], high: [], medium: [], low: [] };
  for (const warning of warnings) bySeverity[warning.severity].push(warning);

  const lines: string[] = [`Security analysis found ${warnings.length} potential issue(s):`, ''];
  for (const severity of ['critical', 'high', 'medium', 'low'] as const) {
    if (bySeverity[severity].length === 0) continue;
    lines.push(`${severity.toUpperCase()} RISK:`);
    for (const warning of bySeverity[severity]) {
      const where = warning.lineNumber ? ` (line ${warning.lineNumber})` : '';
      const context = warning.context ? `\n  Context: ${warning.context}` : '';
      lines.push(`  - ${warning.message}${where}${context}`);
    }
    lines.push('');
  }
  lines.push('Note: These are warnings only. The sandbox provides real isolation.');
  return lines.join('\n');
}

const KNOWN_KEYS = new Set([
  'sandboxType', 'sandbox_type', 'image', 'workingDir', 'working_dir', 'env',
  'autoCleanup', 'auto_cleanup', 'persistFiles', 'persist_files', 'timeout', 'metadata',
]);

/**
 * Resolve the constructor option. `true` selects the subprocess sandbox
 * (Python `SandboxConfig.subprocess()`), a string names the sandbox type, an
 * object supplies fields (snake_case accepted).
 */
export function resolveSandbox(
  input: boolean | string | Record<string, unknown> | undefined | null
): SandboxConfig | undefined {
  if (input === undefined || input === null || input === false) return undefined;
  if (input === true) return defaultSandboxConfig('subprocess');
  if (typeof input === 'string') return defaultSandboxConfig(input);
  if (typeof input !== 'object') throw new Error('sandbox must be a boolean, a sandbox type, or a config object');

  const unknown = Object.keys(input).filter((k) => !KNOWN_KEYS.has(k));
  if (unknown.length > 0) {
    throw new Error(
      `Unknown sandbox field(s): ${unknown.join(', ')}. Valid fields: sandboxType, image, workingDir, env, autoCleanup, persistFiles, timeout, metadata`
    );
  }
  const base = defaultSandboxConfig(
    (input.sandboxType ?? input.sandbox_type ?? 'subprocess') as string
  );
  return {
    ...base,
    image: (input.image as string) ?? base.image,
    workingDir: (input.workingDir ?? input.working_dir ?? base.workingDir) as string,
    env: (input.env as Record<string, string>) ?? base.env,
    autoCleanup: (input.autoCleanup ?? input.auto_cleanup ?? base.autoCleanup) as boolean,
    persistFiles: (input.persistFiles ?? input.persist_files ?? base.persistFiles) as boolean,
    timeout: (input.timeout as number) ?? base.timeout,
    metadata: (input.metadata as Record<string, unknown>) ?? base.metadata,
  };
}

const runners = new Map<string, (config: SandboxConfig) => SandboxRunner>();

/**
 * Register a sandbox implementation for a `sandboxType`. `docker`, `e2b` and
 * the rest are provider integrations, so a host supplies them; naming an
 * unregistered type errors rather than downgrading to local execution.
 */
export function registerSandboxRunner(
  sandboxType: string,
  factory: (config: SandboxConfig) => SandboxRunner
): void {
  runners.set(sandboxType.toLowerCase(), factory);
}

/** Forget a sandbox runner registration. `subprocess` cannot be removed. */
export function unregisterSandboxRunner(sandboxType: string): boolean {
  if (sandboxType.toLowerCase() === 'subprocess') return false;
  return runners.delete(sandboxType.toLowerCase());
}

/** Every registered sandbox type. */
export function sandboxRunnerNames(): string[] {
  return ['subprocess', ...runners.keys()].filter((v, i, a) => a.indexOf(v) === i).sort();
}

/**
 * Interpreter table. `command` is a factory rather than a value so the Node
 * executable (`process.execPath`) is read only when a call actually spawns a
 * subprocess -- never at module load. A literal `process.execPath` here would
 * evaluate `process` while the Agent graph initialises, which throws a
 * ReferenceError in a browser/mobile WebView (issue #4437). `process` is
 * reached through globalThis for the same reason.
 */
const INTERPRETERS: Readonly<Record<string, { command: () => string; args: (file: string) => string[]; extension: string }>> =
  Object.freeze({
    python: { command: () => 'python3', args: (f) => [f], extension: '.py' },
    bash: { command: () => 'bash', args: (f) => [f], extension: '.sh' },
    sh: { command: () => 'sh', args: (f) => [f], extension: '.sh' },
    javascript: { command: () => nodeExecPath(), args: (f) => [f], extension: '.js' },
    node: { command: () => nodeExecPath(), args: (f) => [f], extension: '.js' },
  });

/** The Node executable, resolved lazily so it never runs on a browser graph. */
function nodeExecPath(): string {
  const proc = (globalThis as { process?: { execPath?: string } }).process;
  return proc?.execPath ?? 'node';
}

/**
 * The built-in `subprocess` runner: the code goes to a temp file and runs in a
 * child process with the config's cwd, environment and timeout. Isolation is
 * process-level only -- that is exactly what Python's subprocess sandbox is,
 * and why the config carries `docker` as an option.
 */
export function createSubprocessRunner(config: SandboxConfig): SandboxRunner {
  return {
    sandboxType: 'subprocess',
    async execute(code, options): Promise<SandboxResult> {
      const interpreter = INTERPRETERS[options.language];
      if (!interpreter) {
        return {
          success: false,
          stdout: '',
          stderr: `The subprocess sandbox cannot run "${options.language}" (known: ${Object.keys(INTERPRETERS).join(', ')}).`,
          exitCode: 1,
        };
      }
      // Loaded through computed specifiers so these never reach a browser
      // bundle. `require()` is not enough: scripts/webview-gate.mjs counts a
      // require-call as a static import, and only a true dynamic import keeps
      // the builtin off the graph. Without this the Agent entry fails the gate
      // with "Node builtins imported STATICALLY" -- a blank screen at import
      // time in a webview, which is issue #4437 all over again.
      const [fs, os, path, childProcess] = await Promise.all([
        import(/* @vite-ignore */ ['n', 'ode:fs'].join('')) as Promise<typeof import('fs')>,
        import(/* @vite-ignore */ ['n', 'ode:os'].join('')) as Promise<typeof import('os')>,
        import(/* @vite-ignore */ ['n', 'ode:path'].join('')) as Promise<typeof import('path')>,
        import(/* @vite-ignore */ ['n', 'ode:child_process'].join('')) as Promise<typeof import('child_process')>,
      ]);
      const { spawnSync } = childProcess;

      // Where the code runs and where relative paths resolve. `persistFiles`
      // reuses a stable workspace so artifacts one call writes are there for
      // the next; otherwise each call gets a throwaway temp directory. `cwd`
      // is passed to the child so relative paths resolve against the workspace
      // rather than the host process directory.
      //
      // The default `workingDir` (`/workspace`) is a *container* path from
      // Python's SandboxConfig; the subprocess runner is host-local, so an
      // explicit non-default path is honoured verbatim while the container
      // default maps to a stable per-workspace temp dir instead of the host
      // filesystem root.
      const containerDefault = defaultSandboxConfig().workingDir;
      const explicitDir = config.workingDir && config.workingDir !== containerDefault;
      let dir: string;
      let ephemeral: boolean;
      if (explicitDir) {
        dir = path.resolve(config.workingDir);
        fs.mkdirSync(dir, { recursive: true });
        ephemeral = false;
      } else if (config.persistFiles) {
        dir = path.join(os.tmpdir(), 'praison-sandbox-workspace');
        fs.mkdirSync(dir, { recursive: true });
        ephemeral = false;
      } else {
        dir = fs.mkdtempSync(path.join(os.tmpdir(), 'praison-sandbox-'));
        ephemeral = true;
      }
      const file = path.join(dir, `code${interpreter.extension}`);
      try {
        fs.writeFileSync(file, code, 'utf8');
        const result = spawnSync(interpreter.command(), interpreter.args(file), {
          cwd: dir,
          encoding: 'utf8',
          timeout: options.config.timeout * 1000,
          env: { ...process.env, ...options.config.env },
        });
        const exitCode = result.status ?? 1;
        return {
          success: exitCode === 0 && !result.error,
          stdout: result.stdout ?? '',
          stderr: result.error ? String(result.error.message) : (result.stderr ?? ''),
          exitCode,
        };
      } finally {
        // Only ever remove a temp directory this call created. `autoCleanup`
        // must never delete a persisted or user-named workspace -- that would
        // defeat `persistFiles` and could remove host files.
        if (config.autoCleanup && ephemeral) {
          try {
            fs.rmSync(dir, { recursive: true, force: true });
          } catch {
            // A leftover temp directory is not worth failing the execution for.
          }
        } else if (config.autoCleanup && !ephemeral && !config.persistFiles) {
          // A user-named workingDir without persistFiles: clean up only the
          // code file we wrote, leaving the workspace itself intact.
          try {
            fs.rmSync(file, { force: true });
          } catch {
            // Non-fatal.
          }
        }
      }
    },
  };
}

/** Build the runner for a config, or throw naming what is registered. */
export function createSandboxRunner(config: SandboxConfig): SandboxRunner {
  const type = config.sandboxType.toLowerCase();
  const factory = runners.get(type);
  if (factory) return factory(config);
  if (type === 'subprocess' || type === 'local') return createSubprocessRunner(config);
  throw new Error(
    `No sandbox runner is registered for "${config.sandboxType}" (available: ${sandboxRunnerNames().join(', ')}).\n` +
    `  A remote sandbox is a provider integration: register one with registerSandboxRunner('${config.sandboxType}', ...).`
  );
}

/** Per-call options of `Agent.executeCode` (Python `execute_code`). */
export interface ExecuteCodeOptions {
  /** `python` (default), `bash`, `javascript`, ... */
  language?: string;
  /** Run the static pre-check (default true). */
  checkSecurity?: boolean;
  /**
   * Where to run THIS call: a sandbox type, a config object, or `true` for
   * the default subprocess sandbox. Overrides the agent's `sandbox`.
   */
  runIn?: boolean | string | Record<string, unknown>;
}

/**
 * Run `code` in a sandbox, exactly as Python's `Agent.execute_code` does:
 * resolve where it runs, analyse it first, execute, and attach the warnings
 * to the result rather than only logging them.
 *
 * Runners are cached per sandbox type in `runners`: building a fresh one per
 * call would start and tear down a container each time, which for Docker is
 * seconds of latency and for any backend loses the previous call's files.
 */
export async function executeCodeInSandbox(params: {
  code: string;
  options?: ExecuteCodeOptions;
  /** The agent's own `sandbox` config, used when the call names no `runIn`. */
  defaultConfig?: SandboxConfig;
  runners: Map<string, SandboxRunner>;
  /** Used only to make the "no sandbox configured" error read naturally. */
  agentName: string;
  onWarning?: (message: string) => void;
}): Promise<SandboxResult> {
  const { code, runners, agentName, defaultConfig } = params;
  const options = params.options ?? {};
  const language = options.language ?? 'python';
  const config = options.runIn !== undefined ? resolveSandbox(options.runIn) : defaultConfig;
  if (!config) {
    throw new Error(
      `Agent ${agentName}: no sandbox configured. Either name a place on the call --\n` +
      "    agent.executeCode(code, { runIn: 'subprocess' })\n" +
      '  or set a default for every call with new Agent({ sandbox: true }).'
    );
  }

  let warnings: SecurityWarning[] = [];
  if (options.checkSecurity !== false) {
    warnings = checkCodeSafety(code, language);
    if (warnings.length > 0) params.onWarning?.(formatWarnings(warnings));
  }

  let runner = runners.get(config.sandboxType);
  if (!runner) {
    runner = createSandboxRunner(config);
    runners.set(config.sandboxType, runner);
  }
  const result = await runner.execute(code, { language, config });
  if (warnings.length > 0) {
    result.metadata = { ...(result.metadata ?? {}), securityWarnings: warnings };
  }
  return result;
}
