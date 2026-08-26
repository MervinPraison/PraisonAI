/**
 * Shared helper for constructing OpenAI client options that work across
 * Node and browser-like runtimes (webview, Electron renderer, React Native).
 *
 * The `openai` SDK refuses to construct in any browser-like environment unless
 * `dangerouslyAllowBrowser: true` is passed. Detecting the runtime here keeps
 * Node behaviour unchanged while unblocking browser-like hosts with zero config.
 *
 * Supplying a custom `fetch` lets a host route provider egress through native
 * code (e.g. a Tauri command), keeping the API key out of the JS heap and
 * avoiding CORS for embedded webviews; it also implies `dangerouslyAllowBrowser`.
 */

export interface OpenAIRuntimeOptions {
  /** Force-enable (or disable) the SDK's browser guard. */
  dangerouslyAllowBrowser?: boolean;
  /** Custom fetch implementation; implies `dangerouslyAllowBrowser`. */
  fetch?: typeof fetch;
}

/**
 * Read an environment variable without assuming a Node `process` global, so the
 * OpenAI paths stay usable in webviews / React Native where `process` is
 * undefined (dereferencing it there throws `ReferenceError`).
 *
 * @param name - Environment variable name to read.
 * @returns The variable's value, or `undefined` when `process`/the var is absent.
 * @example
 * const key = getEnv('OPENAI_API_KEY');
 */
export function getEnv(name: string): string | undefined {
  return typeof process !== 'undefined' && process.env
    ? process.env[name]
    : undefined;
}

/**
 * Detect whether we are running in a browser-like runtime: a real browser,
 * an embedded webview / Electron renderer, or React Native.
 *
 * @returns `true` for browser / webview / React-Native runtimes, else `false`.
 * @example
 * if (isBrowserLikeRuntime()) {
 *   // dangerouslyAllowBrowser is required for the OpenAI SDK here
 * }
 */
export function isBrowserLikeRuntime(): boolean {
  const g = globalThis as any;
  const hasWindow =
    typeof g.window !== 'undefined' && typeof g.window.document !== 'undefined';
  const isReactNative =
    typeof g.navigator !== 'undefined' && g.navigator.product === 'ReactNative';
  return hasWindow || isReactNative;
}

/**
 * Merge caller-provided OpenAI client options with runtime-aware defaults so
 * that the SDK constructs successfully in browser-like environments.
 *
 * A custom `fetch` is injected and implies `dangerouslyAllowBrowser`. When
 * `runtime.dangerouslyAllowBrowser` is set it wins (an explicit `false` forces
 * the flag off even if `options` already carried `true`); otherwise the flag is
 * auto-enabled only in browser-like runtimes or when a custom `fetch` is given.
 *
 * @param options - Base OpenAI client options (e.g. `apiKey`, `baseURL`).
 * @param runtime - Runtime overrides: `dangerouslyAllowBrowser` and/or `fetch`.
 * @returns The merged options, browser-safe for the detected runtime.
 * @example
 * const client = new OpenAI(
 *   buildOpenAIClientOptions({ apiKey }, { fetch: nativeFetch })
 * );
 */
export function buildOpenAIClientOptions<T extends Record<string, any>>(
  options: T = {} as T,
  runtime: OpenAIRuntimeOptions = {}
): T & { dangerouslyAllowBrowser?: boolean; fetch?: typeof fetch } {
  const result: Record<string, any> = { ...options };
  if (runtime.fetch) {
    result.fetch = runtime.fetch;
  }
  const allowBrowser =
    runtime.dangerouslyAllowBrowser ??
    (isBrowserLikeRuntime() || !!runtime.fetch);
  if (allowBrowser) {
    result.dangerouslyAllowBrowser = true;
  } else {
    // An explicit disable (or a non-browser runtime) must win even if the
    // caller's base options already carried the flag.
    delete result.dangerouslyAllowBrowser;
  }
  return result as T & {
    dangerouslyAllowBrowser?: boolean;
    fetch?: typeof fetch;
  };
}
