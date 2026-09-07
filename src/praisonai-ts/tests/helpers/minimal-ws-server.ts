/**
 * A dependency-free RFC 6455 WebSocket server for tests.
 *
 * `ws` is not a dependency of this package, and these tests must not reach
 * OpenAI, so the server side is implemented here directly on `node:http`.
 * It speaks just enough of the protocol for the RealtimeAgent tests: the
 * handshake, unmasked server -> client text frames, masked client -> server
 * text frames, and close.
 */
import * as http from 'http';
import * as crypto from 'crypto';
import type { Socket } from 'net';

const WS_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11';

export interface MinimalWsConnection {
  /** Handshake headers exactly as the client sent them. */
  headers: http.IncomingHttpHeaders;
  /** Request path including query string. */
  url: string;
  /** JSON messages received from the client, in order. */
  received: any[];
  /** Send a JSON payload to the client. */
  send(payload: unknown): void;
  /** Close the connection from the server side. */
  close(code?: number): void;
  /** True once the socket has gone away. */
  closed: boolean;
}

export interface MinimalWsServerOptions {
  /**
   * Reject the upgrade with this HTTP status instead of completing the
   * handshake - how a bad API key looks on the wire (OpenAI answers 401).
   */
  rejectWithStatus?: number;
  /** Echo back one of the client's requested subprotocols, if offered. */
  acceptSubprotocol?: boolean;
  /** Called once a connection is established. */
  onConnection?: (connection: MinimalWsConnection) => void;
}

export interface MinimalWsServer {
  port: number;
  url: string;
  connections: MinimalWsConnection[];
  /** Resolves with the next connection to be established. */
  nextConnection(): Promise<MinimalWsConnection>;
  close(): Promise<void>;
}

function encodeTextFrame(text: string): Buffer {
  const payload = Buffer.from(text, 'utf8');
  let header: Buffer;
  if (payload.length < 126) {
    header = Buffer.from([0x81, payload.length]);
  } else if (payload.length < 65536) {
    header = Buffer.alloc(4);
    header[0] = 0x81;
    header[1] = 126;
    header.writeUInt16BE(payload.length, 2);
  } else {
    header = Buffer.alloc(10);
    header[0] = 0x81;
    header[1] = 127;
    header.writeBigUInt64BE(BigInt(payload.length), 2);
  }
  return Buffer.concat([header, payload]);
}

function encodeCloseFrame(code = 1000): Buffer {
  const payload = Buffer.alloc(2);
  payload.writeUInt16BE(code, 0);
  return Buffer.concat([Buffer.from([0x88, payload.length]), payload]);
}

/** Pull as many complete frames as are buffered. Returns leftover bytes. */
function drainFrames(
  buffer: Buffer,
  onFrame: (opcode: number, payload: Buffer) => void
): Buffer {
  let offset = 0;
  while (buffer.length - offset >= 2) {
    const first = buffer[offset];
    const second = buffer[offset + 1];
    const opcode = first & 0x0f;
    const masked = (second & 0x80) !== 0;
    let length = second & 0x7f;
    let cursor = offset + 2;

    if (length === 126) {
      if (buffer.length < cursor + 2) break;
      length = buffer.readUInt16BE(cursor);
      cursor += 2;
    } else if (length === 127) {
      if (buffer.length < cursor + 8) break;
      length = Number(buffer.readBigUInt64BE(cursor));
      cursor += 8;
    }

    let mask: Buffer | null = null;
    if (masked) {
      if (buffer.length < cursor + 4) break;
      mask = buffer.subarray(cursor, cursor + 4);
      cursor += 4;
    }

    if (buffer.length < cursor + length) break;
    const payload = Buffer.from(buffer.subarray(cursor, cursor + length));
    if (mask) {
      for (let i = 0; i < payload.length; i++) payload[i] ^= mask[i % 4];
    }
    cursor += length;
    offset = cursor;
    onFrame(opcode, payload);
  }
  return buffer.subarray(offset);
}

export async function startMinimalWsServer(
  options: MinimalWsServerOptions = {}
): Promise<MinimalWsServer> {
  const connections: MinimalWsConnection[] = [];
  const waiters: Array<(connection: MinimalWsConnection) => void> = [];
  const sockets = new Set<Socket>();

  const server = http.createServer((_req, res) => {
    res.writeHead(426);
    res.end('Upgrade required');
  });

  server.on('upgrade', (req, socket: Socket) => {
    sockets.add(socket);
    socket.on('close', () => sockets.delete(socket));

    if (options.rejectWithStatus) {
      socket.write(
        `HTTP/1.1 ${options.rejectWithStatus} Unauthorized\r\n` +
          'Connection: close\r\nContent-Length: 0\r\n\r\n'
      );
      socket.destroy();
      return;
    }

    const key = req.headers['sec-websocket-key'];
    const accept = crypto
      .createHash('sha1')
      .update(String(key) + WS_GUID)
      .digest('base64');

    const offered = String(req.headers['sec-websocket-protocol'] ?? '')
      .split(',')
      .map((p) => p.trim())
      .filter(Boolean);

    let responseHeaders =
      'HTTP/1.1 101 Switching Protocols\r\n' +
      'Upgrade: websocket\r\n' +
      'Connection: Upgrade\r\n' +
      `Sec-WebSocket-Accept: ${accept}\r\n`;
    if (options.acceptSubprotocol && offered.length > 0) {
      responseHeaders += `Sec-WebSocket-Protocol: ${offered[0]}\r\n`;
    }
    socket.write(responseHeaders + '\r\n');

    const connection: MinimalWsConnection = {
      headers: req.headers,
      url: req.url ?? '',
      received: [],
      closed: false,
      send(payload: unknown) {
        if (socket.destroyed) return;
        socket.write(encodeTextFrame(JSON.stringify(payload)));
      },
      close(code = 1000) {
        if (socket.destroyed) return;
        socket.write(encodeCloseFrame(code));
        socket.end();
      },
    };

    let buffered = Buffer.alloc(0);
    socket.on('data', (chunk: Buffer) => {
      buffered = drainFrames(Buffer.concat([buffered, chunk]), (opcode, payload) => {
        if (opcode === 0x8) {
          connection.closed = true;
          if (!socket.destroyed) {
            socket.write(encodeCloseFrame(1000));
            socket.end();
          }
          return;
        }
        if (opcode === 0x1) {
          try {
            connection.received.push(JSON.parse(payload.toString('utf8')));
          } catch {
            connection.received.push(payload.toString('utf8'));
          }
        }
      });
    });
    socket.on('close', () => {
      connection.closed = true;
    });
    socket.on('error', () => {
      connection.closed = true;
    });

    connections.push(connection);
    options.onConnection?.(connection);
    while (waiters.length > 0) waiters.shift()!(connection);
  });

  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  const port = typeof address === 'object' && address ? address.port : 0;

  return {
    port,
    url: `ws://127.0.0.1:${port}/v1/realtime`,
    connections,
    nextConnection() {
      if (connections.length > 0) return Promise.resolve(connections[connections.length - 1]);
      return new Promise<MinimalWsConnection>((resolve) => waiters.push(resolve));
    },
    close() {
      for (const socket of sockets) socket.destroy();
      sockets.clear();
      return new Promise<void>((resolve) => server.close(() => resolve()));
    },
  };
}

/** A port that is listening but immediately refuses/aborts every connection. */
export async function reservedClosedPort(): Promise<number> {
  const server = http.createServer();
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  const port = typeof address === 'object' && address ? address.port : 0;
  await new Promise<void>((resolve) => server.close(() => resolve()));
  return port;
}
