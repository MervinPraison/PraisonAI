/**
 * Handoff context parity tests - Python `Handoff._prepare_context` and
 * `_seed_target_history`: `contextPolicy` selects the messages the target
 * sees, `maxContextMessages` sizes the `last_n` slice, `preserveSystem`
 * exempts system messages from it, `maxContextTokens` caps the selection, and
 * the selection is seeded onto the target for the duration of the call.
 *
 * Every case is paired with a control that omits the option, so a test that
 * would pass with the option ignored fails here.
 */

import { describe, it, expect, jest } from '@jest/globals';
import { Handoff, ContextPolicy, type HandoffContext } from '../../../src/agent/handoff';

process.env.PRAISONAI_PARITY_SILENT = '1';

/** A target that records the conversation it was given while it was running. */
function recordingAgent(name = 'specialist') {
  const agent: any = {
    name,
    chatHistory: [] as any[],
    seenHistory: null as any[] | null,
    chat: jest.fn(async () => {
      agent.seenHistory = [...agent.chatHistory];
      return { text: `${name} ok` };
    }),
  };
  return agent;
}

const SYSTEM = { role: 'system', content: 'be nice' };
const HISTORY = [
  SYSTEM,
  { role: 'user', content: 'm1' },
  { role: 'assistant', content: 'm2' },
  { role: 'user', content: 'm3' },
  { role: 'assistant', content: 'm4' },
  { role: 'user', content: 'm5' },
];

const contents = (messages: any[]) => messages.map(m => m.content);

const ctx = (extra: Partial<HandoffContext> = {}): HandoffContext => ({
  messages: HISTORY,
  lastMessage: 'please help',
  ...extra,
});

/** A message whose estimated cost is ~104 tokens (4 overhead + 400/4 chars). */
const bulky = (tag: string) => ({ role: 'user', content: `${tag}${'x'.repeat(400 - tag.length)}` });

describe('Handoff context policy (Python parity)', () => {
  describe('contextPolicy', () => {
    it('defaults to summary: system messages plus the last 3 others', async () => {
      const agent = recordingAgent();
      const result = await new Handoff({ agent }).execute(ctx());
      expect(contents(result.context.messages)).toEqual(['be nice', 'm3', 'm4', 'm5']);
    });

    it('contextPolicy full keeps the whole conversation (control: default keeps 4)', async () => {
      const full = await new Handoff({ agent: recordingAgent(), contextPolicy: ContextPolicy.FULL }).execute(ctx());
      expect(contents(full.context.messages)).toEqual(['be nice', 'm1', 'm2', 'm3', 'm4', 'm5']);

      const control = await new Handoff({ agent: recordingAgent() }).execute(ctx());
      expect(control.context.messages).toHaveLength(4);
    });

    it('contextPolicy none passes nothing (control: default passes 4)', async () => {
      const none = await new Handoff({ agent: recordingAgent(), contextPolicy: ContextPolicy.NONE }).execute(ctx());
      expect(none.context.messages).toEqual([]);

      const control = await new Handoff({ agent: recordingAgent() }).execute(ctx());
      expect(control.context.messages).toHaveLength(4);
    });

    it('contextPolicy last_n slices to maxContextMessages', async () => {
      const result = await new Handoff({
        agent: recordingAgent(),
        contextPolicy: ContextPolicy.LAST_N,
        maxContextMessages: 2,
      }).execute(ctx());
      expect(contents(result.context.messages)).toEqual(['be nice', 'm4', 'm5']);
    });

    it('applies transformContext to what the policy selected, not to the raw history', async () => {
      const seen: any[][] = [];
      const result = await new Handoff({
        agent: recordingAgent(),
        contextPolicy: ContextPolicy.LAST_N,
        maxContextMessages: 1,
        transformContext: messages => {
          seen.push(messages);
          return messages.filter(m => m.role !== 'system');
        },
      }).execute(ctx());
      // The filter is handed the policy's output (system + last 1), never all 6.
      expect(contents(seen[0])).toEqual(['be nice', 'm5']);
      expect(contents(result.context.messages)).toEqual(['m5']);
    });
  });

  describe('maxContextMessages', () => {
    it('changes how many messages survive last_n (control: the default 10 keeps all)', async () => {
      const limited = await new Handoff({
        agent: recordingAgent(),
        contextPolicy: ContextPolicy.LAST_N,
        maxContextMessages: 2,
      }).execute(ctx());
      expect(contents(limited.context.messages)).toEqual(['be nice', 'm4', 'm5']);

      const control = await new Handoff({
        agent: recordingAgent(),
        contextPolicy: ContextPolicy.LAST_N,
      }).execute(ctx());
      expect(contents(control.context.messages)).toEqual(['be nice', 'm1', 'm2', 'm3', 'm4', 'm5']);
    });

    it('is ignored by every policy but last_n, as in Python', async () => {
      const summary = await new Handoff({
        agent: recordingAgent(),
        maxContextMessages: 1,
      }).execute(ctx());
      // summary is hard-coded to the last 3 in Python; max_context_messages is
      // the last_n knob only.
      expect(contents(summary.context.messages)).toEqual(['be nice', 'm3', 'm4', 'm5']);
    });
  });

  describe('preserveSystem', () => {
    it('keeps system messages outside the last_n slice (control: false slices raw)', async () => {
      const preserved = await new Handoff({
        agent: recordingAgent(),
        contextPolicy: ContextPolicy.LAST_N,
        maxContextMessages: 2,
      }).execute(ctx());
      expect(contents(preserved.context.messages)).toEqual(['be nice', 'm4', 'm5']);

      const dropped = await new Handoff({
        agent: recordingAgent(),
        contextPolicy: ContextPolicy.LAST_N,
        maxContextMessages: 2,
        preserveSystem: false,
      }).execute(ctx());
      expect(contents(dropped.context.messages)).toEqual(['m4', 'm5']);
    });

    it('keeps a system message the summary policy would otherwise drop', async () => {
      const trailing = [
        { role: 'user', content: 'm1' },
        SYSTEM,
        { role: 'user', content: 'm2' },
        { role: 'user', content: 'm3' },
        { role: 'user', content: 'm4' },
      ];
      const preserved = await new Handoff({ agent: recordingAgent() }).execute(ctx({ messages: trailing }));
      expect(contents(preserved.context.messages)).toEqual(['be nice', 'm2', 'm3', 'm4']);

      const control = await new Handoff({ agent: recordingAgent(), preserveSystem: false }).execute(
        ctx({ messages: trailing })
      );
      expect(contents(control.context.messages)).toEqual(['m2', 'm3', 'm4']);
    });
  });

  describe('maxContextTokens', () => {
    // Python declares max_context_tokens and never reads it; TypeScript honours
    // the documented meaning instead of copying the omission.
    it('drops the oldest messages until the estimate fits (control: the 4000 default keeps all)', async () => {
      const messages = [bulky('a'), bulky('b'), bulky('c')];

      const capped = await new Handoff({
        agent: recordingAgent(),
        contextPolicy: ContextPolicy.FULL,
        maxContextTokens: 250,
      }).execute(ctx({ messages }));
      expect(capped.context.messages.map((m: any) => m.content[0])).toEqual(['b', 'c']);

      const control = await new Handoff({
        agent: recordingAgent(),
        contextPolicy: ContextPolicy.FULL,
      }).execute(ctx({ messages }));
      expect(control.context.messages).toHaveLength(3);
    });

    it('never drops a system message while preserveSystem is on (control: false drops it too)', async () => {
      const messages = [{ role: 'system', content: 'S'.repeat(400) }, bulky('a'), bulky('b')];

      const preserved = await new Handoff({
        agent: recordingAgent(),
        contextPolicy: ContextPolicy.FULL,
        maxContextTokens: 150,
      }).execute(ctx({ messages }));
      expect(preserved.context.messages.map((m: any) => m.role)).toEqual(['system']);

      const dropped = await new Handoff({
        agent: recordingAgent(),
        contextPolicy: ContextPolicy.FULL,
        maxContextTokens: 150,
        preserveSystem: false,
      }).execute(ctx({ messages }));
      expect(dropped.context.messages.map((m: any) => m.content[0])).toEqual(['b']);
    });

    it('is disabled by a non-positive budget', async () => {
      const messages = [bulky('a'), bulky('b'), bulky('c')];
      const result = await new Handoff({
        agent: recordingAgent(),
        contextPolicy: ContextPolicy.FULL,
        maxContextTokens: 0,
      }).execute(ctx({ messages }));
      expect(result.context.messages).toHaveLength(3);
    });
  });

  describe('seeding the target', () => {
    it('prepends the selected context for the call and restores it afterwards', async () => {
      const agent = recordingAgent();
      agent.chatHistory = [{ role: 'assistant', content: 'the target own memory' }];

      await new Handoff({ agent, contextPolicy: ContextPolicy.LAST_N, maxContextMessages: 1 }).execute(ctx());

      expect(contents(agent.seenHistory)).toEqual(['be nice', 'm5', 'the target own memory']);
      // Invocation-scoped: the target is left exactly as it was found.
      expect(contents(agent.chatHistory)).toEqual(['the target own memory']);
    });

    it('seeds nothing when the policy selected nothing', async () => {
      const agent = recordingAgent();
      agent.chatHistory = [{ role: 'assistant', content: 'the target own memory' }];

      await new Handoff({ agent, contextPolicy: ContextPolicy.NONE }).execute(ctx());

      expect(contents(agent.seenHistory)).toEqual(['the target own memory']);
    });

    it('restores the target history when the handoff fails', async () => {
      const agent = recordingAgent();
      agent.chatHistory = [{ role: 'assistant', content: 'kept' }];
      agent.chat.mockRejectedValue(new Error('target down'));

      await expect(new Handoff({ agent }).execute(ctx())).rejects.toThrow('target down');
      expect(contents(agent.chatHistory)).toEqual(['kept']);
    });

    it('runs unseeded rather than failing when the target refuses the history', async () => {
      // getHistory/setHistory is the simple Agent's shape; setHistory rejects a
      // history it cannot represent (here: a second system message).
      const agent: any = {
        name: 'strict',
        history: [{ role: 'user', content: 'own' }],
        getHistory: () => agent.history,
        setHistory: (messages: any[]) => {
          if (messages.filter(m => m.role === 'system').length > 1) throw new Error('unrepresentable');
          agent.history = messages;
        },
        chat: jest.fn(async () => {
          agent.seenHistory = [...agent.history];
          return { text: 'ok' };
        }),
      };

      const twoSystems = [SYSTEM, { role: 'system', content: 'also me' }, { role: 'user', content: 'm1' }];
      const result = await new Handoff({ agent, contextPolicy: ContextPolicy.FULL }).execute(
        ctx({ messages: twoSystems })
      );

      expect(result.response).toBe('ok');
      expect(contents(agent.seenHistory)).toEqual(['own']);
      expect(contents(agent.history)).toEqual(['own']);
    });

    it('seeds a simple-Agent-shaped target through setHistory and restores it', async () => {
      const agent: any = {
        name: 'simple',
        history: [{ role: 'user', content: 'own' }],
        getHistory: () => [...agent.history],
        setHistory: (messages: any[]) => { agent.history = [...messages]; },
        chat: jest.fn(async () => {
          agent.seenHistory = [...agent.history];
          return 'ok';
        }),
      };

      await new Handoff({ agent, contextPolicy: ContextPolicy.LAST_N, maxContextMessages: 1 }).execute(ctx());

      expect(contents(agent.seenHistory)).toEqual(['be nice', 'm5', 'own']);
      expect(contents(agent.history)).toEqual(['own']);
    });
  });
});
