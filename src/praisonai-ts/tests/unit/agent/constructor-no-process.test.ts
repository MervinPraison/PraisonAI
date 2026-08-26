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
});
