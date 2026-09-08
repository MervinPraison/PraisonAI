/**
 * RealtimeAgent - Real-time voice/audio interaction agent
 *
 * Python parity with praisonaiagents/agent/realtime_agent.py
 * Enables real-time voice conversations over a real WebSocket connection.
 *
 * ## Why the WebSocket is loaded the way it is
 *
 * This module is exported from the package root, so it has to stay loadable in
 * a browser/webview bundle (see `scripts/webview-gate.mjs`). A static
 * `import WebSocket from 'ws'` would put an unresolvable bare specifier on that
 * bundle. So the implementation is resolved at call time:
 *
 *   1. an explicitly injected constructor (`{ webSocket }`), for tests and for
 *      runtimes that ship their own,
 *   2. `globalThis.WebSocket` -- browsers, React Native, and Node >= 22,
 *   3. the optional `ws` package, imported through a computed specifier so no
 *      bundler tries to resolve it statically. `ws` is NOT a dependency of this
 *      package; this branch only fires if a consumer installed it themselves,
 *   4. otherwise a clear error naming all three ways to fix it. It never
 *      pretends to have connected.
 */

// ============================================================================
// WebSocket transport abstraction
// ============================================================================

/**
 * The subset of the WebSocket API this agent uses.
 *
 * Both the WHATWG `WebSocket` (browsers, Node >= 22) and the `ws` package
 * satisfy this, which is why a single code path can drive either.
 */
export interface WebSocketLike {
  readyState?: number;
  send(data: string | ArrayBufferLike | ArrayBufferView): void;
  close(code?: number, reason?: string): void;
  addEventListener(type: string, listener: (event: any) => void): void;
  removeEventListener?(type: string, listener: (event: any) => void): void;
}

/** Constructor shape for a {@link WebSocketLike}. */
export type WebSocketConstructorLike = new (
  url: string,
  protocolsOrOptions?: any,
  options?: any
) => WebSocketLike;

interface ResolvedWebSocket {
  ctor: WebSocketConstructorLike;
  /** Can this implementation send custom HTTP headers on the handshake? */
  supportsHeaders: boolean;
  /** Human-readable origin, used in error messages only. */
  source: string;
}

/** WebSocket readyState constants (avoids depending on the ctor's statics). */
const WS_OPEN = 1;

let cachedWebSocket: ResolvedWebSocket | null = null;

/** Reset the cached WebSocket resolution. Exported for tests. */
export function _resetWebSocketResolution(): void {
  cachedWebSocket = null;
}

/**
 * Resolve a WebSocket implementation, preferring a global one.
 *
 * @throws if no implementation can be found - never silently degrades.
 */
export async function resolveWebSocketImplementation(
  injected?: WebSocketConstructorLike
): Promise<ResolvedWebSocket> {
  if (injected) {
    // An injected constructor is assumed to accept the same options object the
    // Node/`ws` implementations do; tests assert on the headers it receives.
    return { ctor: injected, supportsHeaders: true, source: 'injected WebSocket' };
  }

  if (cachedWebSocket) return cachedWebSocket;

  const globalObj = globalThis as any;

  if (typeof globalObj.WebSocket === 'function') {
    // Node's global WebSocket is undici's, which accepts a non-standard
    // `{ headers }` option. A browser's does not - passing an object there is
    // coerced to a protocol list and throws - so browsers use OpenAI's
    // documented subprotocol credentials instead.
    const isNode =
      typeof globalObj.process !== 'undefined' &&
      !!globalObj.process?.versions?.node;
    cachedWebSocket = {
      ctor: globalObj.WebSocket as WebSocketConstructorLike,
      supportsHeaders: isNode,
      source: isNode ? 'global WebSocket (Node)' : 'global WebSocket',
    };
    return cachedWebSocket;
  }

  // Computed specifier: keeps `ws` off every bundler's static import graph.
  const specifier = ['w', 's'].join('');
  let loadError: any = null;
  try {
    const mod: any = await import(/* webpackIgnore: true */ specifier);
    const ctor = mod?.WebSocket ?? mod?.default?.WebSocket ?? mod?.default ?? mod;
    if (typeof ctor === 'function') {
      cachedWebSocket = {
        ctor: ctor as WebSocketConstructorLike,
        supportsHeaders: true,
        source: "'ws' package",
      };
      return cachedWebSocket;
    }
    loadError = new Error("'ws' resolved but exported no WebSocket constructor");
  } catch (error: any) {
    // Only a module-not-found means "not installed". Anything else is a real
    // failure inside an installed `ws` and must not be reported as absence.
    const code = error?.code;
    if (code !== 'MODULE_NOT_FOUND' && code !== 'ERR_MODULE_NOT_FOUND') {
      loadError = error;
    }
  }

  throw new Error(
    'RealtimeAgent requires a WebSocket implementation and none is available. ' +
      'This runtime has no global WebSocket (Node >= 22, browsers and React Native ' +
      "provide one) and the optional 'ws' package " +
      (loadError ? `failed to load: ${loadError?.message ?? loadError}. ` : 'is not installed. ') +
      'Fix by one of: upgrade to Node 22+, run `npm install ws`, or pass ' +
      '`new RealtimeAgent({ webSocket: YourWebSocketConstructor })`.'
  );
}

// ============================================================================
// Configuration Types
// ============================================================================

/**
 * Configuration for Realtime settings.
 */
export interface RealtimeConfig {
  /** Voice to use for responses */
  voice?: 'alloy' | 'echo' | 'fable' | 'onyx' | 'nova' | 'shimmer';
  /** Audio input format */
  inputFormat?: 'pcm16' | 'g711_ulaw' | 'g711_alaw';
  /** Audio output format */
  outputFormat?: 'pcm16' | 'g711_ulaw' | 'g711_alaw';
  /** Sample rate in Hz (local playback hint; not sent to the API) */
  sampleRate?: number;
  /** Enable voice activity detection */
  vadEnabled?: boolean;
  /** VAD threshold */
  vadThreshold?: number;
  /** Timeout in seconds */
  timeout?: number;
}

/**
 * Event types the agent knows by name. The server may send others; they are
 * emitted verbatim rather than dropped, which is why {@link RealtimeEventType}
 * also admits arbitrary strings.
 */
export type KnownRealtimeEventType =
  | 'session.created'
  | 'session.updated'
  | 'input_audio_buffer.append'
  | 'input_audio_buffer.commit'
  | 'input_audio_buffer.clear'
  | 'response.create'
  | 'response.done'
  | 'response.audio.delta'
  | 'response.audio.done'
  | 'response.text.delta'
  | 'response.text.done'
  | 'error';

/**
 * Event type for realtime sessions.
 *
 * `'*'` is a local wildcard: a handler registered for it receives every event.
 * Any other string is a server event type, passed through untouched.
 */
export type RealtimeEventType = KnownRealtimeEventType | '*' | (string & {});

/**
 * Realtime event.
 */
export interface RealtimeEvent {
  type: RealtimeEventType;
  /** The full decoded server payload for this event. */
  data?: any;
  timestamp?: number;
}

/**
 * Configuration for creating a RealtimeAgent.
 */
export interface RealtimeAgentConfig {
  /** Agent name */
  name?: string;
  /** Model to use */
  llm?: string;
  /** Realtime configuration */
  realtime?: boolean | RealtimeConfig;
  /** System instructions */
  instructions?: string;
  /** Enable verbose output */
  verbose?: boolean;
  /** API key */
  apiKey?: string;
  /**
   * Full WebSocket endpoint override (e.g. a local test server or a proxy).
   * When set, the `model` query parameter is not appended and a missing API
   * key is not an error.
   */
  url?: string;
  /** Extra handshake headers (ignored by implementations that cannot send them) */
  headers?: Record<string, string>;
  /** Inject a WebSocket constructor instead of resolving one */
  webSocket?: WebSocketConstructorLike;
  /** How long to wait for the handshake before failing. Default 30000ms. */
  connectTimeoutMs?: number;
}

// ============================================================================
// Default Configuration
// ============================================================================

const DEFAULT_REALTIME_CONFIG: Required<RealtimeConfig> = {
  voice: 'alloy',
  inputFormat: 'pcm16',
  outputFormat: 'pcm16',
  sampleRate: 24000,
  vadEnabled: true,
  vadThreshold: 0.5,
  timeout: 300,
};

const DEFAULT_ENDPOINT = 'wss://api.openai.com/v1/realtime';
const DEFAULT_CONNECT_TIMEOUT_MS = 30000;

// ============================================================================
// Helpers
// ============================================================================

/** Encode bytes as base64 without depending on any Node builtin import. */
function toBase64(bytes: Uint8Array): string {
  const globalObj = globalThis as any;
  if (typeof globalObj.btoa === 'function') {
    let binary = '';
    const chunkSize = 0x8000;
    for (let i = 0; i < bytes.length; i += chunkSize) {
      binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
    }
    return globalObj.btoa(binary);
  }
  if (typeof globalObj.Buffer !== 'undefined') {
    return globalObj.Buffer.from(bytes).toString('base64');
  }
  throw new Error('No base64 encoder available in this runtime (no btoa, no Buffer)');
}

/** Decode base64 to bytes without depending on any Node builtin import. */
function fromBase64(value: string): Uint8Array {
  const globalObj = globalThis as any;
  if (typeof globalObj.atob === 'function') {
    const binary = globalObj.atob(value);
    const out = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
    return out;
  }
  if (typeof globalObj.Buffer !== 'undefined') {
    return new Uint8Array(globalObj.Buffer.from(value, 'base64'));
  }
  throw new Error('No base64 decoder available in this runtime (no atob, no Buffer)');
}

function toUint8Array(data: ArrayBuffer | Uint8Array | ArrayBufferView): Uint8Array {
  if (data instanceof Uint8Array) return data;
  if (data instanceof ArrayBuffer) return new Uint8Array(data);
  const view = data as ArrayBufferView;
  return new Uint8Array(view.buffer, view.byteOffset, view.byteLength);
}

/** Turn whatever a WebSocket handed us into a string, or null if we cannot. */
function messageToString(data: any): string | null {
  if (typeof data === 'string') return data;
  if (data == null) return null;
  if (typeof ArrayBuffer !== 'undefined' && data instanceof ArrayBuffer) {
    return new TextDecoder().decode(new Uint8Array(data));
  }
  if (ArrayBuffer.isView(data)) {
    return new TextDecoder().decode(toUint8Array(data));
  }
  if (Array.isArray(data)) {
    // `ws` can deliver a fragmented message as an array of Buffers.
    return data.map((part) => messageToString(part) ?? '').join('');
  }
  if (typeof data.toString === 'function') return String(data);
  return null;
}

/** Best-effort description of a WebSocket error/close event, for messages. */
function describeFailure(event: any): string {
  if (!event) return 'unknown error';
  const parts: string[] = [];
  const message = event.message ?? event.error?.message ?? event.reason;
  if (message) parts.push(String(message));
  if (typeof event.code === 'number') parts.push(`close code ${event.code}`);
  if (parts.length === 0 && event.type) parts.push(`${event.type} event`);
  return parts.length > 0 ? parts.join(', ') : 'unknown error';
}

// ============================================================================
// RealtimeAgent Class
// ============================================================================

/**
 * Agent for real-time voice conversations.
 *
 * Uses a real WebSocket connection for low-latency audio streaming.
 * `connect()` resolves only once the handshake has actually completed; a bad
 * key, a bad URL or a refused connection rejects, and `isConnected()` stays
 * false.
 *
 * @example
 * ```typescript
 * import { RealtimeAgent } from 'praisonai';
 *
 * const agent = new RealtimeAgent({
 *   instructions: 'You are a helpful voice assistant',
 *   realtime: { voice: 'nova' }
 * });
 *
 * // Listen for what the server actually sends
 * agent.on('response.audio.delta', (event) => {
 *   playAudio(event.data);
 * });
 *
 * await agent.connect();   // rejects if the handshake fails
 * agent.sendAudio(audioBuffer);
 * await agent.disconnect();
 * ```
 */
export class RealtimeAgent {
  static readonly DEFAULT_MODEL = 'gpt-4o-realtime-preview';

  readonly name: string;
  readonly llm: string;
  private readonly instructions?: string;
  private readonly verbose: boolean;
  private readonly realtimeConfig: Required<RealtimeConfig>;
  private readonly apiKey?: string;
  private readonly urlOverride?: string;
  private readonly extraHeaders: Record<string, string>;
  private readonly webSocketImpl?: WebSocketConstructorLike;
  private readonly connectTimeoutMs: number;

  private connected: boolean = false;
  private ws: WebSocketLike | null = null;
  /**
   * The connect() attempt currently in flight, if any. connect() assigns
   * `this.ws` only after the handshake resolves, so without this two
   * concurrent callers both pass the isConnected() check, both open a socket,
   * and the slower one is overwritten -- left open and unreachable, because
   * nothing references it any more. Concurrent callers share one attempt.
   */
  private connecting: Promise<void> | null = null;
  /**
   * Incremented by every teardown. A teardown captures the generation it was
   * issued for, so a disconnect still unwinding an old socket cannot clear a
   * newer one established by a reconnect in the meantime.
   */
  private generation: number = 0;
  private eventHandlers: Map<RealtimeEventType, Array<(event: RealtimeEvent) => void>> = new Map();
  private messageCallbacks: Array<(text: string) => void> = [];
  private audioCallbacks: Array<(audio: Uint8Array) => void> = [];
  private errorCallbacks: Array<(error: Error) => void> = [];

  constructor(config: RealtimeAgentConfig) {
    this.name = config.name || 'RealtimeAgent';
    this.llm = config.llm || process.env.OPENAI_REALTIME_MODEL || RealtimeAgent.DEFAULT_MODEL;
    this.instructions = config.instructions;
    this.verbose = config.verbose ?? true;
    this.apiKey = config.apiKey || process.env.OPENAI_API_KEY;
    this.urlOverride = config.url;
    this.extraHeaders = { ...(config.headers ?? {}) };
    this.webSocketImpl = config.webSocket;
    this.connectTimeoutMs = config.connectTimeoutMs ?? DEFAULT_CONNECT_TIMEOUT_MS;

    // Resolve realtime configuration
    if (config.realtime === undefined || config.realtime === true || config.realtime === false) {
      this.realtimeConfig = { ...DEFAULT_REALTIME_CONFIG };
    } else {
      this.realtimeConfig = { ...DEFAULT_REALTIME_CONFIG, ...config.realtime };
    }
  }

  private log(message: string): void {
    if (this.verbose) {
      console.log(message);
    }
  }

  /** The endpoint this agent will dial. Never contains the API key. */
  getUrl(): string {
    if (this.urlOverride) return this.urlOverride;
    return `${DEFAULT_ENDPOINT}?model=${encodeURIComponent(this.llm)}`;
  }

  /** The `session.update` payload derived from the local config. */
  private sessionPayload(): Record<string, any> {
    const payload: Record<string, any> = {
      voice: this.realtimeConfig.voice,
      input_audio_format: this.realtimeConfig.inputFormat,
      output_audio_format: this.realtimeConfig.outputFormat,
      turn_detection: this.realtimeConfig.vadEnabled
        ? { type: 'server_vad', threshold: this.realtimeConfig.vadThreshold }
        : null,
    };
    if (this.instructions) payload.instructions = this.instructions;
    return payload;
  }

  // =========================================================================
  // Connection
  // =========================================================================

  /**
   * Connect to the realtime session.
   *
   * Resolves only after the WebSocket handshake has completed. Rejects on a
   * refused connection, a non-101 response (which is what a bad API key looks
   * like), a close during the handshake, or a timeout.
   */
  async connect(): Promise<void> {
    if (this.isConnected()) {
      this.log('Already connected to realtime session');
      return;
    }

    // Share one attempt between concurrent callers rather than opening a
    // socket per call and leaking all but the last.
    if (this.connecting) {
      return this.connecting;
    }

    const attempt = this.doConnect();
    this.connecting = attempt;
    try {
      await attempt;
    } finally {
      if (this.connecting === attempt) this.connecting = null;
    }
  }

  private async doConnect(): Promise<void> {
    // A half-dead socket from a previous attempt must not linger.
    this.teardown();

    const url = this.getUrl();
    const usingDefaultEndpoint = !this.urlOverride;

    if (!this.apiKey && usingDefaultEndpoint) {
      throw new Error(
        'OPENAI_API_KEY is required to connect to the OpenAI Realtime API. ' +
          'Set the environment variable, pass `{ apiKey }`, or point `{ url }` at ' +
          'your own endpoint.'
      );
    }

    const impl = await resolveWebSocketImplementation(this.webSocketImpl);

    this.log(`Connecting to realtime session at ${url} ...`);

    let socket: WebSocketLike;
    try {
      if (impl.supportsHeaders) {
        const headers: Record<string, string> = { ...this.extraHeaders };
        if (this.apiKey) {
          headers['Authorization'] = `Bearer ${this.apiKey}`;
          headers['OpenAI-Beta'] = 'realtime=v1';
        }
        socket = new impl.ctor(url, { headers });
      } else {
        // Browsers cannot set handshake headers. OpenAI's documented browser
        // path carries the credentials as subprotocols instead. Note this puts
        // the API key in the page; use an ephemeral key.
        const protocols = ['realtime'];
        if (this.apiKey) protocols.push(`openai-insecure-api-key.${this.apiKey}`);
        protocols.push('openai-beta.realtime-v1');
        Object.keys(this.extraHeaders).length > 0 &&
          this.log(
            `Note: ${impl.source} cannot send custom headers; ` +
              `${Object.keys(this.extraHeaders).join(', ')} were not sent.`
          );
        socket = new impl.ctor(url, protocols);
      }
    } catch (error: any) {
      throw new Error(
        `Failed to create a WebSocket for ${url} using ${impl.source}: ${error?.message ?? error}`
      );
    }

    await new Promise<void>((resolve, reject) => {
      let settled = false;
      const timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        try {
          socket.close();
        } catch {
          /* already gone */
        }
        reject(new Error(`Timed out after ${this.connectTimeoutMs}ms connecting to ${url}`));
      }, this.connectTimeoutMs);
      if (typeof (timer as any).unref === 'function') (timer as any).unref();

      const settle = (error?: Error) => {
        if (settled) return false;
        settled = true;
        clearTimeout(timer);
        if (error) reject(error);
        else resolve();
        return true;
      };

      socket.addEventListener('open', () => {
        settle();
      });

      socket.addEventListener('error', (event: any) => {
        const error = new Error(
          `WebSocket connection to ${url} failed: ${describeFailure(event)}`
        );
        if (!settle(error)) {
          // Post-handshake error: report it, do not claim a connection.
          this.connected = false;
          this.reportError(error);
        }
      });

      socket.addEventListener('close', (event: any) => {
        if (
          !settle(
            new Error(
              `WebSocket to ${url} closed during handshake: ${describeFailure(event)}`
            )
          )
        ) {
          this.handleClose(event);
        }
      });

      socket.addEventListener('message', (event: any) => {
        this.handleMessage(event);
      });
    });

    this.ws = socket;
    this.connected = true;

    // Mirror the Python agent: push the session configuration immediately.
    await this.sendEvent({ type: 'session.update', session: this.sessionPayload() });

    this.log(`Connected to realtime session with model ${this.llm}`);
  }

  /**
   * Disconnect from the realtime session.
   */
  async disconnect(): Promise<void> {
    const socket = this.ws;
    if (!socket) {
      this.connected = false;
      return;
    }

    // Capture the generation this disconnect belongs to. Closing a socket is
    // asynchronous, and a connect() can complete while we wait; clearing state
    // unconditionally afterwards would null out that newer socket and mark the
    // agent disconnected while its connection stayed open and unreachable.
    const generation = this.generation;

    this.log('Disconnecting from realtime session...');
    await new Promise<void>((resolve) => {
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        resolve();
      };
      const timer = setTimeout(finish, 5000);
      if (typeof (timer as any).unref === 'function') (timer as any).unref();
      try {
        socket.addEventListener('close', finish);
        socket.close(1000, 'client disconnect');
      } catch {
        finish();
      }
    });

    this.teardownIfCurrent(generation);
  }

  /** Drop the socket reference and mark the agent disconnected. */
  private teardown(): void {
    this.generation += 1;
    this.ws = null;
    this.connected = false;
  }

  /**
   * Tear down only if nothing newer has been established since `generation`
   * was captured. Used by disconnect(), so a slow close cannot clear a socket
   * a later connect() has already installed.
   */
  private teardownIfCurrent(generation: number): void {
    if (this.generation !== generation) return;
    this.teardown();
  }

  /**
   * Check if connected. Reflects the live socket state, not an intention.
   */
  isConnected(): boolean {
    if (!this.connected || !this.ws) return false;
    const readyState = this.ws.readyState;
    return typeof readyState === 'number' ? readyState === WS_OPEN : true;
  }

  // =========================================================================
  // Sending
  // =========================================================================

  /**
   * Send a raw event over the socket.
   *
   * @throws if not connected - it never silently drops the event.
   */
  async sendEvent(event: Record<string, any>): Promise<void> {
    if (!this.isConnected() || !this.ws) {
      throw new Error(
        `Not connected to realtime session; cannot send "${event.type}". Call connect() first.`
      );
    }
    this.ws.send(JSON.stringify(event));
  }

  /**
   * Send audio data to the session (base64-encoded, per the Realtime API).
   */
  sendAudio(audioData: ArrayBuffer | Uint8Array): void {
    if (!this.isConnected() || !this.ws) {
      throw new Error('Not connected to realtime session');
    }
    this.ws.send(
      JSON.stringify({
        type: 'input_audio_buffer.append',
        audio: toBase64(toUint8Array(audioData)),
      })
    );
  }

  /**
   * Commit the audio buffer for processing.
   */
  commitAudio(): void {
    if (!this.isConnected() || !this.ws) {
      throw new Error('Not connected to realtime session');
    }
    this.ws.send(JSON.stringify({ type: 'input_audio_buffer.commit' }));
  }

  /**
   * Clear the audio buffer.
   */
  clearAudio(): void {
    if (!this.isConnected() || !this.ws) {
      throw new Error('Not connected to realtime session');
    }
    this.ws.send(JSON.stringify({ type: 'input_audio_buffer.clear' }));
  }

  /**
   * Send a text message and request a response (Python `asend_text` parity).
   */
  async sendText(text: string): Promise<void> {
    if (!this.isConnected() || !this.ws) {
      throw new Error('Not connected to realtime session');
    }
    this.log(`Sending text: ${text}`);
    await this.sendEvent({
      type: 'conversation.item.create',
      item: {
        type: 'message',
        role: 'user',
        content: [{ type: 'input_text', text }],
      },
    });
    await this.sendEvent({ type: 'response.create' });
  }

  // =========================================================================
  // Receiving
  // =========================================================================

  private handleMessage(event: any): void {
    const raw = messageToString(event?.data ?? event);
    if (raw === null) return;

    let parsed: any;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return; // Python's receive_loop ignores non-JSON frames too.
    }
    if (!parsed || typeof parsed.type !== 'string') return;

    const type: string = parsed.type;

    // Python-parity convenience callbacks.
    if (type === 'response.text.delta') {
      const delta = typeof parsed.delta === 'string' ? parsed.delta : '';
      for (const callback of [...this.messageCallbacks]) callback(delta);
    } else if (type === 'response.audio.delta') {
      const delta = typeof parsed.delta === 'string' ? parsed.delta : '';
      if (delta) {
        let bytes: Uint8Array | null = null;
        try {
          bytes = fromBase64(delta);
        } catch {
          bytes = null;
        }
        if (bytes) for (const callback of [...this.audioCallbacks]) callback(bytes);
      }
    } else if (type === 'error') {
      const error = new Error(
        parsed.error?.message ?? `Realtime API error: ${JSON.stringify(parsed.error ?? parsed)}`
      );
      this.reportError(error);
    }

    this.emit({ type, data: parsed, timestamp: Date.now() });
  }

  private handleClose(event: any): void {
    const wasConnected = this.connected;
    this.teardown();
    if (wasConnected) {
      this.log(`Realtime session closed: ${describeFailure(event)}`);
    }
  }

  private reportError(error: Error): void {
    for (const callback of [...this.errorCallbacks]) {
      try {
        callback(error);
      } catch {
        /* a bad handler must not break the socket */
      }
    }
  }

  // =========================================================================
  // Handlers
  // =========================================================================

  /**
   * Register an event handler. Use `'*'` to receive every server event.
   */
  on(eventType: RealtimeEventType, handler: (event: RealtimeEvent) => void): void {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, []);
    }
    this.eventHandlers.get(eventType)!.push(handler);
  }

  /**
   * Remove an event handler.
   */
  off(eventType: RealtimeEventType, handler: (event: RealtimeEvent) => void): void {
    const handlers = this.eventHandlers.get(eventType);
    if (handlers) {
      const index = handlers.indexOf(handler);
      if (index !== -1) {
        handlers.splice(index, 1);
      }
    }
  }

  /** Register a callback for text deltas (Python `on_message` parity). */
  onMessage(callback: (text: string) => void): void {
    this.messageCallbacks.push(callback);
  }

  /** Register a callback for decoded audio deltas (Python `on_audio` parity). */
  onAudio(callback: (audio: Uint8Array) => void): void {
    this.audioCallbacks.push(callback);
  }

  /** Register a callback for errors (Python `on_error` parity). */
  onError(callback: (error: Error) => void): void {
    this.errorCallbacks.push(callback);
  }

  /**
   * Emit an event to handlers.
   */
  private emit(event: RealtimeEvent): void {
    const targets = [
      ...(this.eventHandlers.get(event.type) ?? []),
      ...(this.eventHandlers.get('*') ?? []),
    ];
    for (const handler of targets) {
      try {
        handler(event);
      } catch {
        /* a bad handler must not break the socket */
      }
    }
  }

  /**
   * Get the current configuration.
   */
  getConfig(): Required<RealtimeConfig> {
    return { ...this.realtimeConfig };
  }

  /**
   * Update the session configuration. Pushes `session.update` when connected.
   */
  async updateConfig(config: Partial<RealtimeConfig>): Promise<void> {
    Object.assign(this.realtimeConfig, config);

    if (this.isConnected()) {
      await this.sendEvent({ type: 'session.update', session: this.sessionPayload() });
    }
  }
}

// ============================================================================
// Factory Function
// ============================================================================

/**
 * Create a RealtimeAgent instance.
 */
export function createRealtimeAgent(config: RealtimeAgentConfig): RealtimeAgent {
  return new RealtimeAgent(config);
}
