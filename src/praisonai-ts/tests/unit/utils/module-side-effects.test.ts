/**
 * Regression tests for issue #4390: importing the package must not run
 * `process.env` reads or `dotenv.config()` at module-initialisation time,
 * so it does not throw in runtimes where `process` is undefined.
 *
 * These call the code (not just assert exports) to prove behaviour.
 */

describe('module-scope side effects (issue #4390)', () => {
    describe('Logger.level is lazy and process-guarded', () => {
        let savedProcess: any;

        afterEach(() => {
            if (savedProcess !== undefined) {
                (globalThis as any).process = savedProcess;
                savedProcess = undefined;
            }
            jest.resetModules();
        });

        it('does not throw when process is undefined', () => {
            jest.resetModules();
            savedProcess = (globalThis as any).process;
            // Simulate a webview / non-Node runtime with no `process`.
            delete (globalThis as any).process;

            const { Logger } = require('../../../src/utils/logger');

            // Reading the level would previously have thrown at import time via
            // `process.env.LOGLEVEL`. Now it must be safe to call.
            expect(() => Logger.info('hello')).not.toThrow();
        });

        it('defaults to INFO level when LOGLEVEL is unset', () => {
            jest.resetModules();
            const prev = process.env.LOGLEVEL;
            delete process.env.LOGLEVEL;

            const { Logger, LogLevel } = require('../../../src/utils/logger');
            const level = (Logger as any).level as number;
            expect(level).toBe(LogLevel.INFO);

            if (prev !== undefined) {
                process.env.LOGLEVEL = prev;
            }
        });
    });

    describe('llm/openai has no module-scope dotenv.config()', () => {
        it('imports without any OPENAI_API_KEY and without throwing', () => {
            jest.resetModules();
            const prevKey = process.env.OPENAI_API_KEY;
            delete process.env.OPENAI_API_KEY;

            // dotenv was removed as a dependency; requiring the OpenAI module
            // must not attempt to load it or read a .env, and must not throw
            // for consumers of non-OpenAI providers.
            let mod: any;
            expect(() => {
                mod = require('../../../src/llm/openai');
            }).not.toThrow();
            expect(mod.OpenAIService).toBeDefined();

            if (prevKey !== undefined) {
                process.env.OPENAI_API_KEY = prevKey;
            }
        });

        it('does not statically import the dotenv package', () => {
            const fs = require('fs');
            const path = require('path');
            const src = fs.readFileSync(
                path.join(__dirname, '../../../src/llm/openai.ts'),
                'utf8'
            );
            expect(src).not.toContain("from 'dotenv'");
            expect(src).not.toContain('dotenv.config(');
        });
    });
});
