/**
 * Cancellation / AbortSignal tests (behavioural).
 *
 * These call the code (not merely assert a symbol exists) and would FAIL
 * before AbortSignal was threaded through the option types, providers and the
 * tools registry.
 */

import { describe, it, expect } from '@jest/globals';
import { OpenAIProvider } from '../../../src/llm/providers/openai';
import { ToolsRegistry } from '../../../src/tools/registry/registry';
import type { ToolMetadata } from '../../../src/tools/registry/types';
import { Agent } from '../../../src/agent/simple';

describe('AbortSignal cancellation', () => {
  describe('OpenAIProvider forwards signal to the client', () => {
    it('passes options.signal to chat.completions.create in generateText', async () => {
      const provider = new OpenAIProvider('gpt-4o-mini', { apiKey: 'test-key' });

      let seenRequestOptions: any = undefined;
      // Inject a fake OpenAI client so no network call happens.
      (provider as any).client = {
        chat: {
          completions: {
            create: async (_body: any, requestOptions?: any) => {
              seenRequestOptions = requestOptions;
              return {
                choices: [{ message: { content: 'ok' }, finish_reason: 'stop' }],
                usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
              };
            },
          },
        },
      };

      const controller = new AbortController();
      await provider.generateText({
        messages: [{ role: 'user', content: 'hi' }],
        signal: controller.signal,
      });

      // Before the fix, create() was called with a single argument and the
      // signal never reached the request — seenRequestOptions.signal was
      // undefined.
      expect(seenRequestOptions).toBeDefined();
      expect(seenRequestOptions.signal).toBe(controller.signal);
    });

    it('passes options.signal to a streaming request', async () => {
      const provider = new OpenAIProvider('gpt-4o-mini', { apiKey: 'test-key' });

      let seenRequestOptions: any = undefined;
      (provider as any).client = {
        chat: {
          completions: {
            create: async (_body: any, requestOptions?: any) => {
              seenRequestOptions = requestOptions;
              // Minimal empty async iterable.
              return {
                async *[Symbol.asyncIterator]() {
                  /* no chunks */
                },
              };
            },
          },
        },
      };

      const controller = new AbortController();
      const stream = await provider.streamText({
        messages: [{ role: 'user', content: 'hi' }],
        signal: controller.signal,
      });
      // Consume the iterator so the create() call actually runs.
      for await (const _ of stream) {
        /* drain */
      }

      expect(seenRequestOptions).toBeDefined();
      expect(seenRequestOptions.signal).toBe(controller.signal);
    });
  });

  describe('ToolsRegistry honours ctx.signal', () => {
    const metadata: ToolMetadata = {
      id: 'echo',
      displayName: 'Echo',
      description: 'Echoes input',
      tags: [],
      requiredEnv: [],
      optionalEnv: [],
      install: { npm: '', pnpm: '', yarn: '', bun: '' },
      docsSlug: 'echo',
      capabilities: {},
      packageName: 'none',
    };

    it('does not run the tool when the signal is already aborted', async () => {
      const registry = new ToolsRegistry();
      let executed = false;
      registry.register(metadata, () => ({
        name: 'echo',
        description: 'Echoes input',
        parameters: { type: 'object', properties: {} },
        execute: async (input: any) => {
          executed = true;
          return input;
        },
      }));

      const tool = registry.create('echo');
      const controller = new AbortController();
      controller.abort();

      await expect(
        tool.execute({ value: 1 }, { signal: controller.signal })
      ).rejects.toBeDefined();
      // Before the fix ctx.signal was ignored and the tool ran anyway.
      expect(executed).toBe(false);
    });

    it('runs the tool normally when the signal is not aborted', async () => {
      const registry = new ToolsRegistry();
      let executed = false;
      registry.register(metadata, () => ({
        name: 'echo',
        description: 'Echoes input',
        parameters: { type: 'object', properties: {} },
        execute: async (input: any) => {
          executed = true;
          return input;
        },
      }));

      const tool = registry.create('echo');
      const controller = new AbortController();

      const result = await tool.execute({ value: 42 }, { signal: controller.signal });
      expect(executed).toBe(true);
      expect(result).toEqual({ value: 42 });
    });
  });

  describe('Agent tool loop honours cancellation', () => {
    it('does not invoke a tool when the resolved signal is already aborted', async () => {
      let toolRan = false;
      const agent = new Agent({
        instructions: 'test',
        toolFunctions: {
          sideEffect: () => {
            toolRan = true;
            return 'done';
          },
        },
      });

      const controller = new AbortController();
      controller.abort();

      // Drive processToolCalls directly with an already-aborted signal: the
      // model returned a tool call but Stop was pressed before execution.
      const toolCalls = [
        { id: '1', function: { name: 'sideEffect', arguments: '{}' } },
      ];

      await expect(
        (agent as any).processToolCalls(toolCalls, controller.signal)
      ).rejects.toBeDefined();
      // Before the fix the signal was dropped and the side-effecting tool ran.
      expect(toolRan).toBe(false);
    });

    it('runs the tool when the signal is not aborted', async () => {
      let toolRan = false;
      const agent = new Agent({
        instructions: 'test',
        toolFunctions: {
          sideEffect: () => {
            toolRan = true;
            return 'done';
          },
        },
      });

      const controller = new AbortController();
      const toolCalls = [
        { id: '1', function: { name: 'sideEffect', arguments: '{}' } },
      ];

      const results = await (agent as any).processToolCalls(toolCalls, controller.signal);
      expect(toolRan).toBe(true);
      expect(results[0].content).toBe('done');
    });
  });
});
