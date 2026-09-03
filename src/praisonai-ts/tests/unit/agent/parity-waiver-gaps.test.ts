/**
 * Behavioural parity for four signature-parity waivers that were validated by
 * running both SDKs rather than by reading the waiver text.
 *
 * Each block pairs the fixed behaviour with a control proving the explicit
 * form still wins, so a future "simplification" cannot quietly restore the gap.
 */
process.env.PRAISONAI_PARITY_SILENT = '1';

import { Agent } from '../../../src/agent/simple';
import { Handoff, defaultHandoffToolName, defaultHandoffToolDescription } from '../../../src/agent/handoff';
import { resolveDefaultModel } from '../../../src/llm/default-model';

// Recording double for the OpenAI-compatible service. `mock*` prefix: jest
// allows it inside the hoisted factory.
const mockLlm = {
  calls: [] as Array<{ method: string; args: any[] }>,
  instances: [] as Array<{ model: string; opts: any }>,
};

jest.mock('../../../src/llm/openai', () => ({
  OpenAIService: jest.fn().mockImplementation((model: string, opts: any) => {
    mockLlm.instances.push({ model, opts });
    return {
      model,
      generateText: jest.fn(async (...args: any[]) => {
        mockLlm.calls.push({ method: 'generateText', args });
        return 'text-response';
      }),
      generateChat: jest.fn(async (...args: any[]) => {
        mockLlm.calls.push({ method: 'generateChat', args });
        return { content: 'chat-response', role: 'assistant' };
      }),
      streamChat: jest.fn(async () => 'streamed'),
      streamChatWithTools: jest.fn(async (...args: any[]) => {
        mockLlm.calls.push({ method: 'streamChatWithTools', args });
        return { content: 'stream-tools-response', role: 'assistant' };
      }),
    };
  }),
}));

const quiet = { verbose: false, stream: false } as const;

/** The user prompt a recorded call carried. */
const promptOf = (call: { method: string; args: any[] }): string => {
  if (call.method === 'generateText') return call.args[0];
  const messages = call.args[0];
  return messages[messages.length - 1].content;
};

beforeEach(() => {
  mockLlm.calls = [];
  mockLlm.instances = [];
});

// ---------------------------------------------------------------------------
// Waiver: Agent.start.prompt
// ---------------------------------------------------------------------------

describe('Agent.start() without a prompt (Python: prompt=None -> instructions)', () => {
  it('sends the instructions as the task when no prompt is given', async () => {
    const agent = new Agent({ instructions: 'You are terse', ...quiet });

    await agent.start();

    expect(mockLlm.calls).toHaveLength(1);
    expect(promptOf(mockLlm.calls[0])).toBe('You are terse');
  });

  it('control: an explicit prompt still wins over the instructions', async () => {
    const agent = new Agent({ instructions: 'You are terse', ...quiet });

    await agent.start('What is 2+2?');

    expect(promptOf(mockLlm.calls[0])).toBe('What is 2+2?');
  });

  it('control: an explicit empty string is a choice, not an omission', async () => {
    const agent = new Agent({ instructions: 'You are terse', ...quiet });

    await agent.start('');

    expect(promptOf(mockLlm.calls[0])).toBe('');
  });

  it('falls back to "Hello" when the agent has no instructions either', async () => {
    // role-only agents get generated instructions, so drive the fallback by
    // emptying them the way Python's `self.instructions or "Hello"` does.
    const agent = new Agent({ instructions: 'x', ...quiet });
    (agent as any).instructions = '';

    await agent.start();

    expect(promptOf(mockLlm.calls[0])).toBe('Hello');
  });
});

// ---------------------------------------------------------------------------
// Waiver: Agent.__init__.model
// ---------------------------------------------------------------------------

describe('default model follows the available credential (Python: _resolve_default_model)', () => {
  const saved: Record<string, string | undefined> = {};
  const VARS = [
    'OPENAI_MODEL_NAME', 'PRAISONAI_MODEL', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY',
    'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'GROQ_API_KEY', 'COHERE_API_KEY', 'OLLAMA_HOST',
  ];

  beforeEach(() => {
    for (const v of VARS) { saved[v] = process.env[v]; delete process.env[v]; }
  });
  afterEach(() => {
    for (const v of VARS) {
      if (saved[v] === undefined) delete process.env[v];
      else process.env[v] = saved[v];
    }
  });

  it('an Anthropic-only environment gets an Anthropic model, not gpt-4o-mini', () => {
    process.env.ANTHROPIC_API_KEY = 'sk-ant-test';

    expect(resolveDefaultModel()).toBe('anthropic/claude-3-5-sonnet-latest');
    expect((new Agent({ instructions: 'x', ...quiet }) as any).llm).toBe('anthropic/claude-3-5-sonnet-latest');
  });

  it('control: an OpenAI-only environment is unchanged', () => {
    process.env.OPENAI_API_KEY = 'sk-test';

    expect(resolveDefaultModel()).toBe('gpt-4o-mini');
    expect((new Agent({ instructions: 'x', ...quiet }) as any).llm).toBe('gpt-4o-mini');
  });

  it('control: OpenAI wins when several credentials are present', () => {
    process.env.OPENAI_API_KEY = 'sk-test';
    process.env.ANTHROPIC_API_KEY = 'sk-ant-test';

    expect(resolveDefaultModel()).toBe('gpt-4o-mini');
  });

  it('control: an explicit model or llm still wins over the walk', () => {
    process.env.ANTHROPIC_API_KEY = 'sk-ant-test';

    expect((new Agent({ instructions: 'x', model: 'gpt-4o', ...quiet }) as any).llm).toBe('gpt-4o');
    expect((new Agent({ instructions: 'x', llm: 'groq/llama-3.1-8b', ...quiet }) as any).llm).toBe('groq/llama-3.1-8b');
  });

  it('control: OPENAI_MODEL_NAME still overrides every credential', () => {
    process.env.ANTHROPIC_API_KEY = 'sk-ant-test';
    process.env.OPENAI_MODEL_NAME = 'my-proxy-model';

    expect(resolveDefaultModel()).toBe('my-proxy-model');
  });

  it('no credential at all still falls back to gpt-4o-mini', () => {
    expect(resolveDefaultModel()).toBe('gpt-4o-mini');
  });
});

// ---------------------------------------------------------------------------
// Waiver: Agent.__init__.caching -- confirmed cosmetic, pinned so it stays so.
// ---------------------------------------------------------------------------

describe('caching default (Python: Agent.cache is set but never read)', () => {
  it('does not serve a second identical prompt from cache by default', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });

    await agent.chat('same question');
    await agent.chat('same question');

    // Python reaches the model both times; so must TypeScript.
    expect(mockLlm.calls).toHaveLength(2);
  });

  it('control: opting in to cache=true does serve the second call from cache', async () => {
    const agent = new Agent({ instructions: 'x', cache: true, ...quiet });

    await agent.chat('same question');
    await agent.chat('same question');

    expect(mockLlm.calls).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// Waiver: Handoff.__init__.tool_name_override -- was NOT cosmetic.
// ---------------------------------------------------------------------------

describe('default handoff tool name (Python: transfer_to_<snake_case agent>)', () => {
  it('lower-cases and underscores the agent name, as Python does', () => {
    expect(defaultHandoffToolName('Support Bot')).toBe('transfer_to_support_bot');
    expect(defaultHandoffToolName('Billing Agent')).toBe('transfer_to_billing_agent');
  });

  it('never emits a name the provider would reject', () => {
    // ^[a-zA-Z0-9_-]{1,64}$ is the OpenAI tool-name rule; the old
    // `handoff_to_${agent.name}` form let a space through.
    for (const raw of ['Support Bot', 'Ops/Tier 2', 'r&d team', '   ']) {
      expect(defaultHandoffToolName(raw)).toMatch(/^[a-zA-Z0-9_-]{1,64}$/);
    }
  });

  it('caps a very long name at the provider 64-char limit', () => {
    // Python does not truncate, so a name over 52 chars yields a
    // `transfer_to_...` string the API rejects; we cap it and stay legal.
    const longName = 'A'.repeat(80);
    const toolName = defaultHandoffToolName(longName);
    expect(toolName.length).toBeLessThanOrEqual(64);
    expect(toolName).toMatch(/^[a-zA-Z0-9_-]{1,64}$/);
    expect(toolName).not.toMatch(/_$/);
  });

  it('a Handoff object and a bare Agent produce the same tool name', () => {
    const target = new Agent({ name: 'Support Bot', instructions: 'help', ...quiet });

    const viaHandoff = new Handoff({ agent: target as any }).name;
    const viaBareAgent = new Agent({ instructions: 'main', handoffs: [target], ...quiet });

    expect(viaHandoff).toBe('transfer_to_support_bot');
    expect((viaBareAgent as any).handoffs[0].name).toBe('transfer_to_support_bot');
  });

  it('control: an explicit name override still wins', () => {
    const target = new Agent({ name: 'Support Bot', instructions: 'help', ...quiet });

    expect(new Handoff({ agent: target as any, name: 'my_tool' }).name).toBe('my_tool');
  });
});

// ---------------------------------------------------------------------------
// Waiver: Handoff.__init__.tool_description_override + Agent.__init__.role
// ---------------------------------------------------------------------------

describe('default handoff tool description (Python: Transfer task to <name> (<role>) - <goal>)', () => {
  it('carries the target role and goal, as Python does', () => {
    const target = new Agent({ name: 'Support Bot', role: 'Assistant', goal: 'Help users', ...quiet });

    expect(new Handoff({ agent: target as any }).description)
      .toBe('Transfer task to Support Bot (Assistant) - Help users');
  });

  it('omits the parenthesised parts an agent does not have', () => {
    expect(defaultHandoffToolDescription({ name: 'Bot' })).toBe('Transfer task to Bot');
    expect(defaultHandoffToolDescription({ name: 'Bot', role: 'Triager' }))
      .toBe('Transfer task to Bot (Triager)');
  });

  it('control: an explicit description override still wins', () => {
    const target = new Agent({ name: 'Support Bot', role: 'Assistant', ...quiet });

    expect(new Handoff({ agent: target as any, description: 'Escalate' }).description).toBe('Escalate');
  });
});

describe('Agent role/goal/backstory read back (Python: always materialised)', () => {
  it('an instruction-only agent reports Python\'s defaults', () => {
    const agent = new Agent({ instructions: 'Summarise AI news', ...quiet });

    expect(agent.role).toBe('Assistant');
    expect(agent.goal).toBe('Summarise AI news');
    expect(agent.backstory).toBe('Summarise AI news');
  });

  it('an agent with neither instructions nor goal reports Python\'s other defaults', () => {
    const agent = new Agent({ name: 'Bare', ...quiet });

    expect(agent.role).toBe('Assistant');
    expect(agent.goal).toBe('Help the user with their tasks');
    expect(agent.backstory).toBe('I am an AI assistant');
  });

  it('control: explicit values are kept verbatim and still shape the instructions', () => {
    const agent = new Agent({ role: 'Analyst', goal: 'Find trends', backstory: 'Ex-quant', ...quiet });

    expect(agent.role).toBe('Analyst');
    expect(agent.goal).toBe('Find trends');
    expect(agent.backstory).toBe('Ex-quant');
    expect(agent.getInstructions()).toContain('You are a Analyst.');
  });
});
