/**
 * Behaviour parity for the per-call options of `Agent.chat`.
 *
 * Every test here is paired: the option changes what the code does, and the
 * control shows the behaviour is absent when the option is not passed. That
 * pairing is the whole point — an option that is accepted and ignored passes
 * a "does the parameter exist?" test and fails the user.
 */
process.env.PRAISONAI_PARITY_SILENT = '1';

import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { Agent } from '../../../../src/agent/simple';
import { HooksManager } from '../../../../src/hooks/manager';
import { buildMultimodalPrompt } from '../../../../src/agent/features/chat-options';

const mockLlm = {
  calls: [] as Array<{ method: string; args: any[] }>,
  chatQueue: [] as any[],
  textQueue: [] as any[],
};

jest.mock('../../../../src/llm/openai', () => ({
  OpenAIService: jest.fn().mockImplementation(() => {
    const next = (queue: any[], fallback: any) => {
      const item = queue.length > 0 ? queue.shift() : fallback;
      if (item instanceof Error) throw item;
      return item;
    };
    return {
      generateText: jest.fn(async (...args: any[]) => {
        mockLlm.calls.push({ method: 'generateText', args });
        return next(mockLlm.textQueue, 'text-response');
      }),
      generateChat: jest.fn(async (...args: any[]) => {
        mockLlm.calls.push({ method: 'generateChat', args });
        return next(mockLlm.chatQueue, { content: 'chat-response', role: 'assistant' });
      }),
      streamChat: jest.fn(async (messages: any, temperature: number, onToken: (t: string) => void) => {
        mockLlm.calls.push({ method: 'streamChat', args: [messages, temperature] });
        onToken('streamed');
        return 'streamed';
      }),
      streamChatWithTools: jest.fn(async (...args: any[]) => {
        mockLlm.calls.push({ method: 'streamChatWithTools', args });
        return next(mockLlm.chatQueue, { content: 'stream-tools-response', role: 'assistant' });
      }),
    };
  }),
}));

const quiet = { verbose: false, stream: false } as const;
const lastCall = () => mockLlm.calls[mockLlm.calls.length - 1];
/** The user message of the last generateChat call. */
const lastUserMessage = () => {
  const messages = lastCall().args[0];
  return messages[messages.length - 1];
};

let tmpDir: string;

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'praison-chat-options-'));
});

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

beforeEach(() => {
  mockLlm.calls = [];
  mockLlm.chatQueue = [];
  mockLlm.textQueue = [];
});

describe('Agent.chat: attachments', () => {
  it('sends a local image as an inline data URI, and the plain text without it', async () => {
    // A 1x1 PNG is enough: the point is that the bytes are read and encoded.
    const png = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
      'base64',
    );
    const file = path.join(tmpDir, 'pixel.png');
    fs.writeFileSync(file, png);

    const agent = new Agent({ instructions: 'x', ...quiet });
    await agent.chat('what is this?', undefined, undefined, { attachments: [file] });

    const message = lastUserMessage();
    expect(Array.isArray(message.content)).toBe(true);
    expect(message.content[0]).toEqual({ type: 'text', text: 'what is this?' });
    expect(message.content[1].type).toBe('image_url');
    expect(message.content[1].image_url.url).toBe(`data:image/png;base64,${png.toString('base64')}`);

    // Ephemeral: the attachment never reaches history, only the text does.
    expect(agent.getHistory().map((m) => m.content)).toContain('what is this?');
  });

  it('control: without attachments the prompt stays a plain string', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    await agent.chat('what is this?');
    expect(lastCall().method).toBe('generateText');
    expect(lastCall().args[0]).toBe('what is this?');
  });

  it('passes an http(s) or data: attachment through as a URL', async () => {
    const content = await buildMultimodalPrompt('look', ['https://example.com/a.png', 'data:image/png;base64,AAAA']);
    expect(content).toEqual([
      { type: 'text', text: 'look' },
      { type: 'image_url', image_url: { url: 'https://example.com/a.png' } },
      { type: 'image_url', image_url: { url: 'data:image/png;base64,AAAA' } },
    ]);
  });

  it('warns and skips an unreadable or non-image attachment rather than failing the turn', async () => {
    const warnings: string[] = [];
    const content = await buildMultimodalPrompt('look', ['missing.png', 'notes.txt'], {
      onWarning: (m) => warnings.push(m),
    });
    expect(content).toEqual([{ type: 'text', text: 'look' }]);
    expect(warnings).toHaveLength(2);
    expect(warnings[0]).toContain('missing.png');
    expect(warnings[1]).toContain('notes.txt');
  });
});

describe('Agent.chat: reasoningSteps', () => {
  it('forces a single non-streaming completion even when streaming is on', async () => {
    const agent = new Agent({ instructions: 'x', verbose: false, stream: true });
    await agent.chat('hi', undefined, undefined, { reasoningSteps: true });
    expect(lastCall().method).toBe('generateText');
  });

  it('control: the same agent streams when reasoningSteps is not set', async () => {
    const agent = new Agent({ instructions: 'x', verbose: false, stream: true });
    await agent.chat('hi');
    expect(lastCall().method).toBe('streamChat');
  });

  it('beats an explicit per-call stream: true', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    await agent.chat('hi', undefined, undefined, { stream: true, reasoningSteps: true });
    expect(lastCall().method).toBe('generateText');
  });
});

describe('Agent.chat: taskName / taskDescription / taskId', () => {
  it('reaches the lifecycle hooks and is readable afterwards', async () => {
    const seen: any[] = [];
    const hooks = new HooksManager();
    hooks.register('agent_start', (ctx: any) => { seen.push(['start', ctx]); return ctx; });
    hooks.register('agent_complete', (ctx: any) => { seen.push(['complete', ctx]); return ctx; });

    const agent = new Agent({ instructions: 'x', ...quiet, hooks });
    await agent.chat('hi', undefined, undefined, {
      taskName: 'summarise', taskDescription: 'condense the notes', taskId: 'T-7',
    });

    expect(seen.map((s) => s[0])).toEqual(['start', 'complete']);
    for (const [, ctx] of seen) {
      expect(ctx.taskName).toBe('summarise');
      expect(ctx.taskDescription).toBe('condense the notes');
      expect(ctx.taskId).toBe('T-7');
    }
    expect(agent.getTaskContext()).toEqual({
      name: 'summarise', description: 'condense the notes', id: 'T-7',
    });
  });

  it('control: no task metadata is invented when the caller names none', async () => {
    const seen: any[] = [];
    const hooks = new HooksManager();
    hooks.register('agent_start', (ctx: any) => { seen.push(ctx); return ctx; });

    const agent = new Agent({ instructions: 'x', ...quiet, hooks });
    await agent.chat('hi');

    expect(seen[0].taskName).toBeUndefined();
    expect(seen[0].taskId).toBeUndefined();
    expect(agent.getTaskContext()).toBeUndefined();
  });

  it('carries only the fields that were given', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    await agent.chat('hi', undefined, undefined, { taskId: 'T-1' });
    expect(agent.getTaskContext()).toEqual({ id: 'T-1' });
  });
});

describe('Agent.chat: config', () => {
  it('is forwarded verbatim to the managed backend that runs the turn', async () => {
    const seen: any[] = [];
    const backend = {
      execute: jest.fn(async (prompt: string, options: any) => {
        seen.push({ prompt, options });
        return 'from-backend';
      }),
    };
    const agent = new Agent({ instructions: 'x', ...quiet, backend });

    await expect(agent.chat('hi', undefined, undefined, { config: { thinkingBudget: 4096 } }))
      .resolves.toBe('from-backend');
    expect(seen[0].options.config).toEqual({ thinkingBudget: 4096 });
    // The local transport was never used: the runtime owns the turn.
    expect(mockLlm.calls).toHaveLength(0);
  });

  it('control: the same backend sees no config when the caller passes none', async () => {
    const seen: any[] = [];
    const backend = { execute: jest.fn(async (prompt: string, options: any) => { seen.push(options); return 'ok'; }) };
    const agent = new Agent({ instructions: 'x', ...quiet, backend });
    await agent.chat('hi');
    expect(seen[0].config).toBeUndefined();
  });
});
