/**
 * Provider egress.
 *
 * Not incidental plumbing -- without this port the app does not work on iOS.
 * In a Tauri mobile webview the page origin is `tauri://localhost` (iOS) or
 * `http://tauri.localhost` (Android), so every provider request is cross-origin
 * and subject to that provider's CORS policy. It also puts the API key in the
 * JS heap, where any injected script can read it.
 *
 * The Tauri adapter sends the request from Rust instead: no CORS involvement,
 * and the key can stay behind the keychain command and never enter the webview
 * at all.
 *
 * Streaming is a byte stream rather than a string promise, because the SSE
 * reader in protocol/src/sse.ts must see partial frames as they arrive.
 */

export interface HttpRequest {
  readonly method: "GET" | "POST" | "DELETE";
  readonly url: string;
  readonly headers: Readonly<Record<string, string>>;
  readonly body?: string;
  readonly signal: AbortSignal;
}

export interface HttpResponse {
  readonly status: number;
  readonly headers: Readonly<Record<string, string>>;
  readonly body: ReadableStream<Uint8Array> | null;
}

export interface HttpPort {
  send(request: HttpRequest): Promise<HttpResponse>;

  /**
   * True when the adapter sends from native code.
   *
   * When false, the composition root refuses to hand a hardware-backed secret
   * to an engine -- so a misconfigured build cannot quietly leak a keychain
   * value into the webview's heap.
   */
  readonly sendsFromNative: boolean;
}
