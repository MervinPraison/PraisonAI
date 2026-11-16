import { EventEmitter } from 'events';
import { WebSocketTransport } from '../../src/mcp/transports';

class MockWebSocket extends EventEmitter {
    static last: MockWebSocket;
    send = jest.fn();
    // Real close handshakes finish asynchronously; tests emit close explicitly.
    close = jest.fn();

    constructor(_url: string) {
        super();
        MockWebSocket.last = this;
        queueMicrotask(() => this.emit('open'));
    }
}

jest.mock('ws', () => ({ __esModule: true, default: MockWebSocket }), { virtual: true });

async function boundedOutcome(pending: Promise<unknown>): Promise<unknown> {
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
        return await Promise.race([
            pending.then(() => 'resolved', error => error),
            new Promise(resolve => { timer = setTimeout(() => resolve('pending'), 100); }),
        ]);
    } finally {
        if (timer) clearTimeout(timer);
    }
}

const response = (source: string) => JSON.stringify({ jsonrpc: '2.0', id: 1, result: { source } });

describe('WebSocketTransport connection lifecycle', () => {
    let transport: WebSocketTransport;

    beforeEach(async () => {
        transport = new WebSocketTransport('ws://localhost');
        await transport.connect();
    });

    afterEach(async () => {
        await transport.disconnect();
    });

    it.each(['remote', 'local'])('rejects every pending request on %s close', async (mode) => {
        const outcomes = [1, 2].map(id => boundedOutcome(
            transport.send({ jsonrpc: '2.0', id, method: 'tools/list' })
        ));
        if (mode === 'remote') MockWebSocket.last.emit('close');
        else await transport.disconnect();

        expect(transport.isConnected()).toBe(false);
        for (const outcome of await Promise.all(outcomes)) {
            expect(outcome).toBeInstanceOf(Error);
            expect(outcome).toEqual(expect.objectContaining({
                message: expect.stringMatching(/closed|disconnect/i),
            }));
        }
    });

    it('keeps a replacement connection active when the old close event arrives', async () => {
        const old = MockWebSocket.last;
        await transport.disconnect();
        await transport.connect();
        old.emit('close');
        expect(transport.isConnected()).toBe(true);

        const pending = transport.send({ jsonrpc: '2.0', id: 1, method: 'tools/list' });
        MockWebSocket.last.emit('message', response('new'));
        await expect(pending).resolves.toMatchObject({ result: { source: 'new' } });
    });

    it('ignores a closing connection response when a new request reuses its ID', async () => {
        const old = MockWebSocket.last;
        await transport.disconnect();
        await transport.connect();
        const received = jest.fn();
        transport.onMessage(received);
        const pending = transport.send({ jsonrpc: '2.0', id: 1, method: 'tools/list' });
        old.emit('message', response('old'));
        MockWebSocket.last.emit('message', response('new'));

        await expect(pending).resolves.toMatchObject({ result: { source: 'new' } });
        expect(received).toHaveBeenCalledTimes(1);
    });

    it('keeps a completed response available after its connection closes', async () => {
        const pending = transport.send({ jsonrpc: '2.0', id: 1, method: 'tools/list' });
        MockWebSocket.last.emit('message', response('complete'));
        MockWebSocket.last.emit('close');
        await expect(pending).resolves.toMatchObject({ result: { source: 'complete' } });
    });
});
