/**
 * Two races found in review of the realtime connect/disconnect fix.
 *
 * connect() assigns this.ws only AFTER the handshake resolves, and teardown()
 * nulls this.ws unconditionally without checking which socket it owns. So:
 *
 *  1. Two concurrent connect() calls both pass the isConnected() check and both
 *     open sockets. The last to finish overwrites this.ws, leaving the other
 *     socket open and unreachable -- a leaked connection the agent can never
 *     close.
 *  2. A disconnect() still waiting on an old socket can clear a NEW socket
 *     established by a reconnect, marking the agent disconnected while its
 *     socket stays open.
 */
import { RealtimeAgent } from '../../../src/agent/realtime';
import { startMinimalWsServer, MinimalWsServer } from '../../helpers/minimal-ws-server';

describe('RealtimeAgent connect/disconnect races', () => {
  let server: MinimalWsServer;

  beforeEach(async () => {
    server = await startMinimalWsServer();
  });

  afterEach(async () => {
    await server.close();
  });

  it('concurrent connect() calls must not leak a second socket', async () => {
    const agent = new RealtimeAgent({
      apiKey: 'sk-test',
      url: server.url,
      connectTimeoutMs: 4000,
      verbose: false,
    });

    await Promise.all([agent.connect(), agent.connect()]);

    // One agent, one live connection. A second accepted socket is one the
    // agent no longer references and can never close.
    expect(server.connections.length).toBe(1);
    expect(agent.isConnected()).toBe(true);

    await agent.disconnect();
  });

  it('control: a single connect() opens exactly one socket', async () => {
    const agent = new RealtimeAgent({
      apiKey: 'sk-test',
      url: server.url,
      connectTimeoutMs: 4000,
      verbose: false,
    });

    await agent.connect();
    expect(server.connections.length).toBe(1);
    expect(agent.isConnected()).toBe(true);

    await agent.disconnect();
  });

  it('a reconnect during disconnect must survive the old teardown', async () => {
    const agent = new RealtimeAgent({
      apiKey: 'sk-test',
      url: server.url,
      connectTimeoutMs: 4000,
      verbose: false,
    });

    await agent.connect();
    const closing = agent.disconnect();
    await closing;

    await agent.connect();
    // The reconnect must be usable, not cleared by the earlier teardown.
    expect(agent.isConnected()).toBe(true);

    await agent.disconnect();
  });
});
