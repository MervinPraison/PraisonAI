import { EventEmitter } from 'events';
import { WebSocketTransport } from '../../src/mcp/transports';

class MockWebSocket extends EventEmitter {
    static last: MockWebSocket;
    send = jest.fn();

    constructor(_url: string) {
        super();
        MockWebSocket.last = this;
        queueMicrotask(() => this.emit('open'));
    }

    close(): void {
        this.emit('close');
    }
}

jest.mock('ws', () => ({ __esModule: true, default: MockWebSocket }), { virtual: true });

describe('WebSocketTransport response correlation', () => {
    let transport: WebSocketTransport;

    beforeEach(async () => {
        transport = new WebSocketTransport('ws://localhost');
        await transport.connect();
    });

    afterEach(async () => {
        await transport.disconnect();
    });

    it.each([0, 1, 'request-1'])('resolves the request with id %p', async (id) => {
        const response = { jsonrpc: '2.0' as const, id, result: { tools: [] } };
        const received = jest.fn();
        transport.onMessage(received);
        const pending = transport.send({ jsonrpc: '2.0', id, method: 'tools/list' });

        MockWebSocket.last.emit('message', Buffer.from(JSON.stringify(response)));

        await expect(pending).resolves.toEqual(response);
        expect(received).toHaveBeenCalledWith(response);
    });

    it('rejects an error response with id zero', async () => {
        const pending = transport.send({ jsonrpc: '2.0', id: 0, method: 'tools/list' });
        const rejected = expect(pending).rejects.toThrow('Tool listing failed');

        MockWebSocket.last.emit('message', JSON.stringify({
            jsonrpc: '2.0', id: 0, error: { code: -32603, message: 'Tool listing failed' },
        }));

        await rejected;
    });
});
