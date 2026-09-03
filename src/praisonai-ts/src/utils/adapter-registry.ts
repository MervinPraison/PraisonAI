/**
 * Generic adapter registry.
 *
 * Port of `praisonaiagents/utils/adapter_registry.py` (`AdapterRegistry`).
 * Used by `memory/adapters.ts` (and, later, knowledge adapters) so the
 * factory-vs-class lookup logic lives in one place.
 *
 * Python semantics preserved:
 * - Two registration modes: a class instantiated on demand
 *   (`registerAdapter`) and a factory called on demand (`registerFactory`).
 *   A factory takes priority over a class registered under the same name.
 * - `getAdapter` returns `null` (Python `None`) when nothing is registered,
 *   or when construction fails because an optional backend is missing. In
 *   Python that is `ImportError`/`ModuleNotFoundError`; in TypeScript it is a
 *   {@link BackendNotAvailableError} or a Node `MODULE_NOT_FOUND` /
 *   `ERR_MODULE_NOT_FOUND` error (see {@link isBackendUnavailableError}).
 * - Any other construction failure is wrapped in
 *   {@link AdapterCreationError} (Python `RuntimeError`), with the original
 *   error on `cause`.
 *
 * Python's `threading.Lock` has no equivalent here: JavaScript registries
 * are single-threaded, so the lock is simply omitted.
 */

/** Keyword arguments forwarded to an adapter constructor / factory (Python `**kwargs`). */
export type AdapterKwargs = Record<string, unknown>;

/** An adapter class instantiated on demand (Python `Type[T]`). */
export type AdapterClass<T> = new (kwargs: AdapterKwargs) => T;

/** An adapter factory called on demand (Python `Callable[..., T]`). */
export type AdapterFactory<T> = (kwargs: AdapterKwargs) => T;

/**
 * Raised by adapter factories whose backend is not available in this runtime
 * (the optional dependency is missing, or the backend is not yet ported).
 *
 * Python analogue: the `ImportError` raised by the factories in
 * `memory/adapters/factories.py`. {@link AdapterRegistry.getAdapter} treats
 * it exactly like Python treats `ImportError`: the adapter resolves to `null`.
 */
export class BackendNotAvailableError extends Error {
  readonly backend: string;
  readonly installHint: string | null;

  constructor(backend: string, message: string, installHint: string | null = null) {
    super(message);
    this.name = 'BackendNotAvailableError';
    this.backend = backend;
    this.installHint = installHint;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Raised when an adapter constructor or factory throws for a reason other
 * than a missing backend (Python `RuntimeError` in `AdapterRegistry.get_adapter`).
 */
export class AdapterCreationError extends Error {
  readonly cause: unknown;

  constructor(message: string, cause: unknown) {
    super(message);
    this.name = 'AdapterCreationError';
    this.cause = cause;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * True when `err` means "the optional backend is not installed" — the
 * TypeScript equivalent of Python's `(ImportError, ModuleNotFoundError)`.
 */
export function isBackendUnavailableError(err: unknown): boolean {
  if (err instanceof BackendNotAvailableError) return true;
  const code = (err as { code?: unknown } | null)?.code;
  return code === 'MODULE_NOT_FOUND' || code === 'ERR_MODULE_NOT_FOUND';
}

/**
 * Generic registry for protocol-based adapters.
 *
 * Python parity: `praisonaiagents/utils/adapter_registry.py::AdapterRegistry`.
 */
export class AdapterRegistry<T> {
  private readonly _adapters = new Map<string, AdapterClass<T>>();
  private readonly _factories = new Map<string, AdapterFactory<T>>();
  private readonly _typeName: string;

  /**
   * @param adapterTypeName Human-readable adapter kind used in error messages
   *   (Python `adapter_type_name`, default `"adapter"`).
   */
  constructor(adapterTypeName: string = 'adapter') {
    this._typeName = adapterTypeName;
  }

  /** Register an adapter class instantiated on demand (Python `register_adapter`). */
  registerAdapter(name: string, adapterClass: AdapterClass<T>): void {
    this._adapters.set(name, adapterClass);
  }

  /** Register a factory function that creates adapter instances (Python `register_factory`). */
  registerFactory(name: string, factoryFunc: AdapterFactory<T>): void {
    this._factories.set(name, factoryFunc);
  }

  /**
   * Return an adapter instance for `name`, or `null` if unavailable
   * (Python `get_adapter`).
   *
   * Tries the factory first, then direct class instantiation. A missing
   * backend ({@link isBackendUnavailableError}) yields `null`; any other
   * failure is re-thrown as {@link AdapterCreationError}.
   */
  getAdapter(name: string, kwargs: AdapterKwargs = {}): T | null {
    const factory = this._factories.get(name);
    const adapterCls = this._adapters.get(name);

    if (factory !== undefined) {
      try {
        return factory(kwargs);
      } catch (exc) {
        if (isBackendUnavailableError(exc)) return null;
        throw new AdapterCreationError(
          `Failed to create ${this._typeName} adapter '${name}' via factory. ` +
            'Check adapter config and installed extras.',
          exc,
        );
      }
    }

    if (adapterCls !== undefined) {
      try {
        return new adapterCls(kwargs);
      } catch (exc) {
        if (isBackendUnavailableError(exc)) return null;
        throw new AdapterCreationError(
          `Failed to instantiate ${this._typeName} adapter '${name}'. ` +
            'Check adapter constructor args and installed extras.',
          exc,
        );
      }
    }

    return null;
  }

  /** Sorted list of every registered adapter name (Python `list_adapters`). */
  listAdapters(): string[] {
    return Array.from(new Set([...this._adapters.keys(), ...this._factories.keys()])).sort();
  }

  /** True if `name` has a registered adapter class or factory (Python `is_available`). */
  isAvailable(name: string): boolean {
    return this._adapters.has(name) || this._factories.has(name);
  }

  /**
   * First successfully instantiated adapter from `preferences`, as a
   * `[name, instance]` tuple, or `null` if none could be created
   * (Python `get_first_available`).
   */
  getFirstAvailable(preferences: string[], kwargs: AdapterKwargs = {}): [string, T] | null {
    for (const name of preferences) {
      const instance = this.getAdapter(name, kwargs);
      if (instance !== null && instance !== undefined) {
        return [name, instance];
      }
    }
    return null;
  }
}
