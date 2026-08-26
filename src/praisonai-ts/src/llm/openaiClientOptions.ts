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
 * Detect whether we are running in a browser-like runtime: a real browser,
 * an embedded webview / Electron renderer, or React Native.
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
  }
  return result as T & {
    dangerouslyAllowBrowser?: boolean;
    fetch?: typeof fetch;
  };
}
