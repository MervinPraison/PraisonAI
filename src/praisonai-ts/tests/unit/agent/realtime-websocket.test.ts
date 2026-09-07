/**
 * RealtimeAgent WebSocket behaviour.
 *
 * The bug these tests exist for: `connect()` used to set `connected = true`
 * and emit a fabricated `session.created` without opening any socket, so an
 * agent built with a deliberately invalid endpoint or key still reported
 * itself connected. Every failure assertion below is paired with a control
 * that proves the assertion is not vacuously true.
 *
 * No test here talks to OpenAI: the server side is a local, dependency-free
 * RFC 6455 implementation in tests/helpers/minimal-ws-server.ts.
 */
import { RealtimeAgent, resolveWebSocketImplementation, _resetWebSocketResolution } from '../../../src/agent/realtime';
import {
  startMinimalWsServer,
  reservedClosedPort,
  MinimalWsServer,
} from '../../helpers/minimal-ws-server';

const QUIET = { verbose: false, connectTimeoutMs: 2000 } as const;

/** Wait until `predicate` holds, or fail loudly after `timeoutMs`. */
async function waitFor(predicate: () => boolean, timeoutMs = 3000, label = 'condition'): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  throw new Error(`Timed out waiting for ${label}`);
}

describe('RealtimeAgent - real WebSocket connection', () => {
  let server: MinimalWsServer | null = null;

  afterEach(async () => {
    if (server) {
      await server.close();
      server = null;
    }
  });

  // ==========================================================================
  // Regression: the original defect
  // ==========================================================================

  describe('regression: an invalid endpoint must not report connected', () => {
    it('rejects and stays disconnected when nothing is listening', async () => {
      const port = await reservedClosedPort();
      const agent = new RealtimeAgent({
        ...QUIET,
        apiKey: 'sk-invalid',
        url: `ws://127.0.0.1:${port}/v1/realtime`,
      });

      await expect(agent.connect()).rejects.toThrow(/failed|closed|refus/i);
      expect(agent.isConnected()).toBe(false);
    });

    it('rejects and stays disconnected when the host does not resolve', async () => {
      const agent = new RealtimeAgent({
        ...QUIET,
        apiKey: 'sk-invalid',
        url: 'ws://this-host-does-not-exist.invalid/v1/realtime',
      });

      await expect(agent.connect()).rejects.toThrow();
      expect(agent.isConnected()).toBe(false);
    });

    it('rejects when the server refuses the handshake, as a bad API key does', async () => {
      server = await startMinimalWsServer({ rejectWithStatus: 401 });
      const agent = new RealtimeAgent({ ...QUIET, apiKey: 'sk-wrong', url: server.url });

      await expect(agent.connect()).rejects.toThrow();
      expect(agent.isConnected()).toBe(false);
    });

    // CONTROL for all three: the same agent shape against a server that does
    // complete the handshake connects and reports connected.
    it('CONTROL: connects and reports connected against a live server', async () => {
      server = await startMinimalWsServer();
      const agent = new RealtimeAgent({ ...QUIET, apiKey: 'sk-test', url: server.url });

      await expect(agent.connect()).resolves.toBeUndefined();
      expect(agent.isConnected()).toBe(true);
      await agent.disconnect();
    });

    it('does not fabricate session.created - only the server can emit it', async () => {
      // This server accepts the handshake and then says nothing at all.
      server = await startMinimalWsServer();
      const agent = new RealtimeAgent({ ...QUIET, apiKey: 'sk-test', url: server.url });

      const seen: string[] = [];
      agent.on('session.created', (event) => seen.push(String(event.type)));

      await agent.connect();
      await new Promise((resolve) => setTimeout(resolve, 100));
      expect(seen).toEqual([]);

      // CONTROL: when the server does send it, the handler fires.
      const connection = await server.nextConnection();
      connection.send({ type: 'session.created', session: { id: 'sess_123' } });
      await waitFor(() => seen.length === 1, 3000, 'server-sent session.created');
      expect(seen).toEqual(['session.created']);

      await agent.disconnect();
    });
  });

  // ==========================================================================
  // A successful connect really opens a socket
  // ==========================================================================

  describe('successful connect', () => {
    it('actually opens a socket the server observes, with auth headers', async () => {
      server = await startMinimalWsServer();
      const agent = new RealtimeAgent({
        ...QUIET,
        apiKey: 'sk-header-check',
        url: server.url,
        headers: { 'X-Trace': 'abc' },
      });

      expect(server.connections).toHaveLength(0); // control: nothing yet
      await agent.connect();

      const connection = await server.nextConnection();
      expect(server.connections).toHaveLength(1);
      expect(connection.headers['authorization']).toBe('Bearer sk-header-check');
      expect(connection.headers['openai-beta']).toBe('realtime=v1');
      expect(connection.headers['x-trace']).toBe('abc');

      await agent.disconnect();
    });

    it('sends session.update with the resolved config right after connecting', async () => {
      server = await startMinimalWsServer();
      const agent = new RealtimeAgent({
        ...QUIET,
        apiKey: 'sk-test',
        url: server.url,
        instructions: 'Be brief',
        realtime: { voice: 'nova', vadThreshold: 0.9 },
      });

      await agent.connect();
      const connection = await server.nextConnection();
      await waitFor(() => connection.received.length >= 1, 3000, 'session.update');

      expect(connection.received[0]).toMatchObject({
        type: 'session.update',
        session: {
          voice: 'nova',
          input_audio_format: 'pcm16',
          instructions: 'Be brief',
          turn_detection: { type: 'server_vad', threshold: 0.9 },
        },
      });

      await agent.disconnect();
    });

    it('emits server events verbatim, including types it does not know', async () => {
      server = await startMinimalWsServer();
      const agent = new RealtimeAgent({ ...QUIET, apiKey: 'sk-test', url: server.url });

      const all: any[] = [];
      agent.on('*', (event) => all.push(event));
      const texts: string[] = [];
      agent.onMessage((text) => texts.push(text));

      await agent.connect();
      const connection = await server.nextConnection();

      connection.send({ type: 'response.text.delta', delta: 'Hel' });
      connection.send({ type: 'response.text.delta', delta: 'lo' });
      connection.send({ type: 'rate_limits.updated', rate_limits: [{ name: 'requests' }] });

      await waitFor(() => all.length === 3, 3000, 'three server events');
      expect(all.map((e) => e.type)).toEqual([
        'response.text.delta',
        'response.text.delta',
        'rate_limits.updated',
      ]);
      expect(all[0].data).toEqual({ type: 'response.text.delta', delta: 'Hel' });
      expect(texts.join('')).toBe('Hello');

      await agent.disconnect();
    });

    it('decodes base64 audio deltas for onAudio callbacks', async () => {
      server = await startMinimalWsServer();
      const agent = new RealtimeAgent({ ...QUIET, apiKey: 'sk-test', url: server.url });

      const chunks: Uint8Array[] = [];
      agent.onAudio((audio) => chunks.push(audio));

      await agent.connect();
      const connection = await server.nextConnection();
      connection.send({
        type: 'response.audio.delta',
        delta: Buffer.from([0x01, 0x02, 0xfe]).toString('base64'),
      });

      await waitFor(() => chunks.length === 1, 3000, 'audio delta');
      expect(Array.from(chunks[0])).toEqual([0x01, 0x02, 0xfe]);

      await agent.disconnect();
    });

    it('surfaces server error events to onError handlers', async () => {
      server = await startMinimalWsServer();
      const agent = new RealtimeAgent({ ...QUIET, apiKey: 'sk-test', url: server.url });

      const errors: Error[] = [];
      agent.onError((error) => errors.push(error));

      await agent.connect();
      const connection = await server.nextConnection();

      expect(errors).toHaveLength(0); // control
      connection.send({ type: 'error', error: { message: 'invalid_request_error' } });

      await waitFor(() => errors.length === 1, 3000, 'error event');
      expect(errors[0].message).toContain('invalid_request_error');

      await agent.disconnect();
    });
  });

  // ==========================================================================
  // Sending
  // ==========================================================================

  describe('sending', () => {
    it('fails clearly when sending before connecting', async () => {
      const agent = new RealtimeAgent({ ...QUIET, apiKey: 'sk-test', url: 'ws://127.0.0.1:9/x' });

      expect(() => agent.sendAudio(new Uint8Array([1, 2, 3]))).toThrow(/Not connected/i);
      expect(() => agent.commitAudio()).toThrow(/Not connected/i);
      expect(() => agent.clearAudio()).toThrow(/Not connected/i);
      await expect(agent.sendText('hi')).rejects.toThrow(/Not connected/i);
      await expect(agent.sendEvent({ type: 'response.create' })).rejects.toThrow(/Not connected/i);
    });

    it('CONTROL: the same calls reach the wire once connected', async () => {
      server = await startMinimalWsServer();
      const agent = new RealtimeAgent({ ...QUIET, apiKey: 'sk-test', url: server.url });

      await agent.connect();
      const connection = await server.nextConnection();

      agent.sendAudio(new Uint8Array([0xaa, 0xbb]));
      agent.commitAudio();
      agent.clearAudio();
      await agent.sendText('hello there');

      await waitFor(() => connection.received.length >= 6, 3000, 'six client frames');
      const types = connection.received.map((event: any) => event.type);
      expect(types).toEqual([
        'session.update',
        'input_audio_buffer.append',
        'input_audio_buffer.commit',
        'input_audio_buffer.clear',
        'conversation.item.create',
        'response.create',
      ]);
      expect(connection.received[1].audio).toBe(Buffer.from([0xaa, 0xbb]).toString('base64'));
      expect(connection.received[4].item).toEqual({
        type: 'message',
        role: 'user',
        content: [{ type: 'input_text', text: 'hello there' }],
      });

      await agent.disconnect();
    });

    it('sending fails again after disconnect', async () => {
      server = await startMinimalWsServer();
      const agent = new RealtimeAgent({ ...QUIET, apiKey: 'sk-test', url: server.url });

      await agent.connect();
      expect(() => agent.commitAudio()).not.toThrow(); // control
      await agent.disconnect();
      expect(() => agent.commitAudio()).toThrow(/Not connected/i);
    });
  });

  // ==========================================================================
  // Teardown
  // ==========================================================================

  describe('close', () => {
    it('disconnect() closes the socket the server sees', async () => {
      server = await startMinimalWsServer();
      const agent = new RealtimeAgent({ ...QUIET, apiKey: 'sk-test', url: server.url });

      await agent.connect();
      const connection = await server.nextConnection();
      expect(connection.closed).toBe(false); // control

      await agent.disconnect();
      expect(agent.isConnected()).toBe(false);
      await waitFor(() => connection.closed, 3000, 'server-side close');
    });

    it('a server-initiated close flips isConnected() to false', async () => {
      server = await startMinimalWsServer();
      const agent = new RealtimeAgent({ ...QUIET, apiKey: 'sk-test', url: server.url });

      await agent.connect();
      expect(agent.isConnected()).toBe(true); // control
      const connection = await server.nextConnection();
      connection.close(1001);

      await waitFor(() => !agent.isConnected(), 3000, 'client to notice the close');
    });

    it('disconnect() on a never-connected agent is a no-op', async () => {
      const agent = new RealtimeAgent({ ...QUIET, apiKey: 'sk-test', url: 'ws://127.0.0.1:9/x' });
      await expect(agent.disconnect()).resolves.toBeUndefined();
      expect(agent.isConnected()).toBe(false);
    });

    it('reconnects after a disconnect', async () => {
      server = await startMinimalWsServer();
      const agent = new RealtimeAgent({ ...QUIET, apiKey: 'sk-test', url: server.url });

      await agent.connect();
      await agent.disconnect();
      await agent.connect();

      expect(agent.isConnected()).toBe(true);
      expect(server.connections).toHaveLength(2);
      await agent.disconnect();
    });
  });

  // ==========================================================================
  // Endpoint and credentials
  // ==========================================================================

  describe('endpoint and credentials', () => {
    it('defaults to the OpenAI realtime endpoint with the model in the query', () => {
      const agent = new RealtimeAgent({ ...QUIET, apiKey: 'sk-test', llm: 'gpt-4o-realtime-preview' });
      expect(agent.getUrl()).toBe(
        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview'
      );
    });

    it('refuses to dial the OpenAI endpoint without an API key', async () => {
      const previous = process.env.OPENAI_API_KEY;
      delete process.env.OPENAI_API_KEY;
      try {
        const agent = new RealtimeAgent({ ...QUIET });
        await expect(agent.connect()).rejects.toThrow(/OPENAI_API_KEY/);
        expect(agent.isConnected()).toBe(false);
      } finally {
        if (previous !== undefined) process.env.OPENAI_API_KEY = previous;
      }
    });

    it('CONTROL: a custom url does not require an API key', async () => {
      const previous = process.env.OPENAI_API_KEY;
      delete process.env.OPENAI_API_KEY;
      try {
        server = await startMinimalWsServer();
        const agent = new RealtimeAgent({ ...QUIET, url: server.url });
        await agent.connect();
        expect(agent.isConnected()).toBe(true);

        const connection = await server.nextConnection();
        expect(connection.headers['authorization']).toBeUndefined();
        await agent.disconnect();
      } finally {
        if (previous !== undefined) process.env.OPENAI_API_KEY = previous;
      }
    });
  });

  // ==========================================================================
  // WebSocket resolution
  // ==========================================================================

  describe('WebSocket implementation resolution', () => {
    afterEach(() => _resetWebSocketResolution());

    it('prefers the global WebSocket when one exists', async () => {
      _resetWebSocketResolution();
      const resolved = await resolveWebSocketImplementation();
      expect(resolved.ctor).toBe((globalThis as any).WebSocket);
      expect(resolved.supportsHeaders).toBe(true); // Node's undici accepts { headers }
    });

    it('fails with an actionable error when no implementation exists', async () => {
      const previous = (globalThis as any).WebSocket;
      delete (globalThis as any).WebSocket;
      _resetWebSocketResolution();
      try {
        // `ws` is not a dependency of this package, so this resolves nothing.
        await expect(resolveWebSocketImplementation()).rejects.toThrow(
          /requires a WebSocket implementation/
        );
      } finally {
        (globalThis as any).WebSocket = previous;
        _resetWebSocketResolution();
      }
    });

    it('an injected constructor is used and connect() still rejects if it fails', async () => {
      const previous = (globalThis as any).WebSocket;
      delete (globalThis as any).WebSocket;
      _resetWebSocketResolution();
      try {
        const listeners: Record<string, Array<(event: any) => void>> = {};
        class ExplodingSocket {
          readyState = 0;
          constructor(public url: string, public options: any) {
            setTimeout(() => {
              (listeners['error'] ?? []).forEach((fn) => fn({ message: 'handshake refused' }));
            }, 0);
          }
          addEventListener(type: string, fn: (event: any) => void) {
            (listeners[type] ??= []).push(fn);
          }
          send() {
            throw new Error('should never be called');
          }
          close() {}
        }

        const agent = new RealtimeAgent({
          ...QUIET,
          apiKey: 'sk-test',
          url: 'ws://injected/endpoint',
          webSocket: ExplodingSocket as any,
        });

        await expect(agent.connect()).rejects.toThrow(/handshake refused/);
        expect(agent.isConnected()).toBe(false);
      } finally {
        (globalThis as any).WebSocket = previous;
        _resetWebSocketResolution();
      }
    });
  });

  // ==========================================================================
  // Browser path: no handshake headers available
  // ==========================================================================

  describe('browser path (no header support)', () => {
    it('sends OpenAI subprotocol credentials when headers cannot be set', async () => {
      // A browser WebSocket cannot set handshake headers, so the agent falls
      // back to OpenAI's documented subprotocol credentials. Verified here at
      // the wire level only; not verified against api.openai.com.
      server = await startMinimalWsServer({ acceptSubprotocol: true });

      const RealWebSocket = (globalThis as any).WebSocket;
      class BrowserLikeWebSocket extends RealWebSocket {}
      const agent = new RealtimeAgent({
        ...QUIET,
        apiKey: 'sk-browser',
        url: server.url,
        webSocket: undefined,
      });
      // Force the no-header branch by pretending we are not in Node.
      const previousProcess = (globalThis as any).process;
      (globalThis as any).process = { ...previousProcess, versions: {} };
      (globalThis as any).WebSocket = BrowserLikeWebSocket;
      _resetWebSocketResolution();

      try {
        await agent.connect();
        const connection = await server.nextConnection();
        expect(connection.headers['authorization']).toBeUndefined();
        expect(String(connection.headers['sec-websocket-protocol'])).toContain(
          'openai-insecure-api-key.sk-browser'
        );
        expect(String(connection.headers['sec-websocket-protocol'])).toContain(
          'openai-beta.realtime-v1'
        );
        await agent.disconnect();
      } finally {
        (globalThis as any).process = previousProcess;
        (globalThis as any).WebSocket = RealWebSocket;
        _resetWebSocketResolution();
      }
    });
  });
});
