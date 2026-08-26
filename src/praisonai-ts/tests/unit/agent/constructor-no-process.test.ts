/**
 * Regression tests for issue #4425: constructing an `Agent` (or `AgentTeam`)
 * must not dereference a Node `process` global, so it does not throw in
 * runtimes where `process` is undefined (webview, React Native, browser).
 *
 * Module init was already fixed by #4390; the constructor was missed. These
 * call the code (not just assert exports) to prove behaviour.
 */

describe('Agent constructor process guard (issue #4425)', () => {
    let savedProcess: any;

    afterEach(() => {
        if (savedProcess !== undefined) {
            (globalThis as any).process = savedProcess;
            savedProcess = undefined;
        }
        jest.resetModules();
    });

    it('constructs Agent when process is undefined', () => {
        jest.resetModules();
        savedProcess = (globalThis as any).process;
        // Simulate a webview / non-Node runtime with no `process`.
        delete (globalThis as any).process;

        const { Agent } = require('../../../src/agent/simple');

        let agent: any;
        expect(() => {
            agent = new Agent({ instructions: 'You are helpful' });
        }).not.toThrow();
        // Falls back to the default model without a `process.env` deref.
        expect(agent.llm).toBe('gpt-4o-mini');
    });

    it('constructs AgentTeam when process is undefined', () => {
        jest.resetModules();
        savedProcess = (globalThis as any).process;
        delete (globalThis as any).process;

        const { Agent, AgentTeam } = require('../../../src/agent/simple');

        expect(() => {
            const agent = new Agent({ instructions: 'You are helpful' });
            new AgentTeam({ agents: [agent] });
        }).not.toThrow();
    });

    it('default token sink does not deref process.stdout when process is undefined', async () => {
        jest.resetModules();

        const { Agent } = require('../../../src/agent/simple');
        const agent = new Agent({ instructions: 'You are helpful', llm: 'gpt-4o-mini' });

        // Emit a token through the default sink (no onToken supplied). The mock
        // exercises the OpenAI streaming path where emitToken() runs.
        agent.llmService.streamChat = jest.fn(
            async (_messages: any, _temp: any, onToken: (t: string) => void) => {
                onToken('hello');
                return 'hello';
            }
        );

        // Simulate a webview: process (and process.stdout) is gone at call time.
        savedProcess = (globalThis as any).process;
        delete (globalThis as any).process;

        await expect(agent.start('hi')).resolves.toBe('hello');
        expect(agent.llmService.streamChat).toHaveBeenCalled();
    });
});
