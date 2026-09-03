/**
 * Shared base helpers for framework adapters (no third-party imports).
 *
 * Python parity: praisonaiagents/frameworks/base.py
 *
 * Python offloads a sync `run` to a bounded per-adapter thread pool so one
 * slow framework cannot starve the process-wide executor. JavaScript has no
 * threads to offload to, so the same bound is applied as a per-adapter
 * concurrency limit: at most `THREAD_OFFLOAD_MAX_WORKERS` runs are in flight
 * at once and the rest queue in order. Python's `__del__` best-effort cleanup
 * has no TypeScript equivalent; call {@link BaseFrameworkAdapter.cleanup}.
 */

import { Logger } from '../utils/logger';
import type {
  FrameworkAdapterProtocol,
  FrameworkLLMConfig,
  FrameworkResolveOptions,
  FrameworkRunOptions,
  FrameworkSetupOptions,
} from './protocols';

/**
 * Bounded FIFO concurrency limiter standing in for Python's
 * `ThreadPoolExecutor(max_workers=...)`.
 */
export class OffloadPool {
  private active = 0;
  private readonly waiters: Array<() => void> = [];

  constructor(readonly maxWorkers: number) {}

  /** Run `fn` once a worker slot is free. */
  async run<T>(fn: () => T | Promise<T>): Promise<T> {
    if (this.active >= this.maxWorkers) {
      await new Promise<void>((resolve) => this.waiters.push(resolve));
    }
    this.active += 1;
    try {
      return await fn();
    } finally {
      this.active -= 1;
      const next = this.waiters.shift();
      if (next) next();
    }
  }

  /** Number of runs currently executing. */
  get activeCount(): number {
    return this.active;
  }

  /** Number of runs waiting for a slot. */
  get pendingCount(): number {
    return this.waiters.length;
  }
}

const TEMPLATE_RE = /\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g;

/**
 * Base class for framework adapters providing common functionality.
 *
 * Python parity: `BaseFrameworkAdapter`. Subclasses provide `isAvailable()`
 * and `run(...)`; `arun` offloads a sync `run` through the bounded pool.
 */
export abstract class BaseFrameworkAdapter implements FrameworkAdapterProtocol {
  name: string = '';
  installHint: string = '';
  requiresToolsExtra: boolean = false;
  isRouter: boolean = false;

  /** Adapters with a native async `run` path set this true and override `arun`. */
  SUPPORTS_ASYNC: boolean = false;

  /** Adapter can execute native workflow YAML. */
  SUPPORTS_WORKFLOW: boolean = false;

  /** Adapter supports cli_backend / runtime / models.*.runtime / providers.*.runtime_default. */
  SUPPORTS_RUNTIME_FEATURES: boolean = false;

  /** Bound of the per-adapter offload pool (Python `_THREAD_OFFLOAD_MAX_WORKERS`). */
  THREAD_OFFLOAD_MAX_WORKERS: number = 4;

  DEFAULT_MODEL: string = 'openai/gpt-4o-mini';

  private threadPool: OffloadPool | null = null;

  /** True when this framework's optional dependencies are installed. */
  abstract isAvailable(): boolean;

  /** Execute the framework with shared agents.yaml configuration. */
  abstract run(
    config: Record<string, unknown>,
    llmConfig: FrameworkLLMConfig,
    topic: string,
    options?: FrameworkRunOptions,
  ): string | Promise<string>;

  /**
   * Resolve a model name from per-agent spec and shared llmConfig.
   * Python parity: `_resolve_llm(spec, llm_config)`.
   */
  protected resolveLlm(spec: unknown, llmConfig: FrameworkLLMConfig | null | undefined): string {
    // base_url / api_key are read for wrapper subclasses that upgrade the
    // model string to a provider object; the base returns the model string.
    if (typeof spec === 'string' && spec.trim()) {
      return spec.trim();
    }
    if (spec && typeof spec === 'object' && typeof (spec as Record<string, unknown>).model === 'string') {
      const model = (spec as Record<string, unknown>).model as string;
      if (model) return model;
    }
    void llmConfig;
    return process.env.MODEL_NAME || this.DEFAULT_MODEL;
  }

  /**
   * Safely format a template string, preserving JSON-like braces whose name
   * is not in `kwargs`. Python parity: `_format_template(template, **kwargs)`.
   */
  protected formatTemplate(template: string, kwargs: Record<string, unknown> = {}): string {
    if (typeof template !== 'string') return template;
    return template.replace(TEMPLATE_RE, (match: string, name: string) =>
      name in kwargs ? String(kwargs[name]) : match,
    );
  }

  /** Pick a concrete adapter variant; the base returns itself. */
  resolve(options: FrameworkResolveOptions = {}): FrameworkAdapterProtocol {
    const { config = null } = options;
    void config;
    return this;
  }

  /** Framework-specific pre-run hooks; the base does nothing. */
  setup(options: FrameworkSetupOptions): void {
    void options;
  }

  /** Lazily create the bounded, per-adapter offload pool. Python parity: `_get_thread_pool`. */
  protected getThreadPool(): OffloadPool {
    if (this.threadPool === null) {
      this.threadPool = new OffloadPool(this.THREAD_OFFLOAD_MAX_WORKERS);
    }
    return this.threadPool;
  }

  /**
   * Run `run` through this adapter's bounded pool.
   * Python parity: `_thread_offload_run(*args, **kwargs)`.
   */
  protected async threadOffloadRun(
    config: Record<string, unknown>,
    llmConfig: FrameworkLLMConfig,
    topic: string,
    options: FrameworkRunOptions = {},
  ): Promise<string> {
    const pool = this.getThreadPool();
    return pool.run(() => this.run(config, llmConfig, topic, options));
  }

  /** Async execution; offloads the sync `run` when there is no native async path. */
  async arun(
    config: Record<string, unknown>,
    llmConfig: FrameworkLLMConfig,
    topic: string,
    options: FrameworkRunOptions = {},
  ): Promise<string> {
    const { toolsDict = null, agentCallback = null, taskCallback = null, cliConfig = null } = options;
    if (!this.SUPPORTS_ASYNC) {
      void Logger.warn(
        `Adapter ${JSON.stringify(this.name || this.constructor.name)} has no native async path; ` +
          `delegating to a bounded pool (maxWorkers=${this.THREAD_OFFLOAD_MAX_WORKERS}). ` +
          'Concurrent async callers will contend for this pool.',
      );
    }
    return this.threadOffloadRun(config, llmConfig, topic, { toolsDict, agentCallback, taskCallback, cliConfig });
  }

  /** Release the offload pool. Queued runs already accepted still complete. */
  cleanup(): void {
    this.threadPool = null;
  }

  /** Return the concrete adapter name to dispatch to. */
  resolveAlias(): string {
    return this.name;
  }
}
