/**
 * Handoff safety parity tests - Python `Handoff._check_safety`: `detectCycles`
 * refuses a target already in the handoff chain and `maxDepth` refuses a chain
 * that is already at the limit, both before the target agent is touched.
 *
 * The chain itself is the async-scoped equivalent of Python's
 * `_handoff_chain_var`: `execute()` runs the target under the extended chain,
 * so a handoff performed from inside a target is seen as nested.
 *
 * Every case is paired with a control that turns the option off or raises the
 * limit, so a test that would pass with the option ignored fails here.
 */

import { describe, it, expect, jest } from '@jest/globals';
import {
  Handoff,
  HandoffCycleError,
  HandoffDepthError,
  currentHandoffChain,
  type HandoffContext,
} from '../../../src/agent/handoff';

process.env.PRAISONAI_PARITY_SILENT = '1';

function fakeAgent(name: string) {
  return { name, chat: jest.fn(async () => ({ text: `${name} ok` })) } as any;
}

/** A source agent: only its name reaches the chain. */
const sourceAgent = (name: string) => ({ name, chat: async () => ({ text: '' }) });

const ctx = (extra: Partial<HandoffContext> = {}): HandoffContext => ({
  messages: [],
  lastMessage: 'go',
  ...extra,
});

/** Await a handoff that must be refused, and hand back the refusal. */
async function refusal(promise: Promise<unknown>): Promise<any> {
  let caught: unknown;
  let resolved = false;
  await promise.then(() => { resolved = true; }, error => { caught = error; });
  if (resolved) throw new Error('expected the handoff to be refused');
  return caught as any;
}

describe('Handoff safety (Python parity)', () => {
  describe('maxDepth', () => {
    it('refuses a handoff at the depth limit and never calls the target', async () => {
      const target = fakeAgent('specialist');
      const h = new Handoff({ agent: target, maxDepth: 2 });

      await expect(
        h.execute(ctx({ handoffChain: ['a', 'b'], sourceAgent: sourceAgent('b') }))
      ).rejects.toThrow(HandoffDepthError);
      expect(target.chat).not.toHaveBeenCalled();
    });

    it('allows the same chain when the limit is higher (control)', async () => {
      const target = fakeAgent('specialist');
      const h = new Handoff({ agent: target, maxDepth: 5 });

      const result = await h.execute(ctx({ handoffChain: ['a', 'b'], sourceAgent: sourceAgent('b') }));
      expect(result.response).toBe('specialist ok');
      expect(target.chat).toHaveBeenCalledTimes(1);
    });

    it('reports the depth Python reports', async () => {
      const h = new Handoff({ agent: fakeAgent('specialist'), maxDepth: 2 });
      const error = await refusal(h.execute(ctx({ handoffChain: ['a', 'b'], sourceAgent: sourceAgent('b') })));

      expect(error.message).toBe('Max handoff depth exceeded: 3 > 2');
      expect(error.depth).toBe(3);
      expect(error.maxDepth).toBe(2);
      expect(error.context).toMatchObject({ source_agent: 'b', target_agent: 'specialist' });
    });

    it('counts a handoff made from inside a handoff, with no chain passed by hand', async () => {
      const inner = fakeAgent('inner');
      const outerTarget: any = {
        name: 'middle',
        innerError: null as unknown,
        chat: jest.fn(async () => {
          // Runs inside the outer handoff, so the chain already holds "main".
          outerTarget.innerError = await new Handoff({ agent: inner, maxDepth: 1 })
            .execute(ctx({ sourceAgent: sourceAgent('middle') }))
            .then(() => null)
            .catch(e => e);
          return { text: 'middle ok' };
        }),
      };

      await new Handoff({ agent: outerTarget, maxDepth: 1 }).execute(
        ctx({ sourceAgent: sourceAgent('main') })
      );

      expect(outerTarget.innerError).toBeInstanceOf(HandoffDepthError);
      expect(inner.chat).not.toHaveBeenCalled();
    });

    it('leaves the chain empty again once a handoff returns', async () => {
      await new Handoff({ agent: fakeAgent('specialist') }).execute(ctx({ sourceAgent: sourceAgent('main') }));
      expect(currentHandoffChain()).toEqual([]);
    });
  });

  describe('detectCycles', () => {
    it('refuses a target that is already in the chain and never calls it', async () => {
      const target = fakeAgent('alpha');
      const h = new Handoff({ agent: target });

      await expect(
        h.execute(ctx({ handoffChain: ['alpha', 'beta'], sourceAgent: sourceAgent('beta') }))
      ).rejects.toThrow(HandoffCycleError);
      expect(target.chat).not.toHaveBeenCalled();
    });

    it('allows the same handoff with detectCycles off (control)', async () => {
      const target = fakeAgent('alpha');
      const h = new Handoff({ agent: target, detectCycles: false });

      const result = await h.execute(ctx({ handoffChain: ['alpha', 'beta'], sourceAgent: sourceAgent('beta') }));
      expect(result.response).toBe('alpha ok');
      expect(target.chat).toHaveBeenCalledTimes(1);
    });

    it('reports the cycle path Python reports', async () => {
      const h = new Handoff({ agent: fakeAgent('alpha') });
      const error = await refusal(h.execute(ctx({ handoffChain: ['alpha', 'beta'], sourceAgent: sourceAgent('beta') })));

      expect(error.message).toBe('Handoff cycle detected: alpha -> beta -> alpha');
      expect(error.chain).toEqual(['alpha', 'beta', 'alpha']);
      expect(error.context.cycle_path).toEqual(['alpha', 'beta', 'alpha']);
    });

    it('catches a real A -> B -> A loop without any chain passed by hand', async () => {
      const alpha: any = { name: 'alpha', chat: jest.fn(async () => ({ text: 'alpha ok' })) };
      const beta: any = {
        name: 'beta',
        bounceError: null as unknown,
        chat: jest.fn(async () => {
          // beta hands back to alpha, which is where this chain started.
          beta.bounceError = await new Handoff({ agent: alpha })
            .execute(ctx({ sourceAgent: sourceAgent('beta') }))
            .then(() => null)
            .catch(e => e);
          return { text: 'beta ok' };
        }),
      };

      await new Handoff({ agent: beta }).execute(ctx({ sourceAgent: sourceAgent('alpha') }));

      expect(beta.bounceError).toBeInstanceOf(HandoffCycleError);
      expect((beta.bounceError as HandoffCycleError).chain).toEqual(['alpha', 'alpha']);
      expect(alpha.chat).not.toHaveBeenCalled();
    });

    it('lets the same loop through when detectCycles is off (control)', async () => {
      const alpha: any = { name: 'alpha', chat: jest.fn(async () => ({ text: 'alpha ok' })) };
      const beta: any = {
        name: 'beta',
        chat: jest.fn(async () => {
          await new Handoff({ agent: alpha, detectCycles: false }).execute(
            ctx({ sourceAgent: sourceAgent('beta') })
          );
          return { text: 'beta ok' };
        }),
      };

      await new Handoff({ agent: beta }).execute(ctx({ sourceAgent: sourceAgent('alpha') }));
      expect(alpha.chat).toHaveBeenCalledTimes(1);
    });
  });

  describe('concurrent handoffs', () => {
    it('keeps one handoff chain out of a sibling running at the same time', async () => {
      // While a handoff from "alpha" is in flight, an unrelated handoff *to*
      // alpha must not see alpha in its chain. One shared chain would report a
      // cycle that does not exist.
      const slow: any = {
        name: 'slow',
        chat: jest.fn(async () => {
          await new Promise(resolve => {
            const timer = setTimeout(resolve, 20);
            (timer as unknown as { unref?: () => void }).unref?.();
          });
          return { text: 'slow ok' };
        }),
      };
      const alpha = fakeAgent('alpha');

      const inFlight = new Handoff({ agent: slow }).execute(ctx({ sourceAgent: sourceAgent('alpha') }));
      await new Promise(resolve => {
        const timer = setTimeout(resolve, 5); // land inside the first handoff
        (timer as unknown as { unref?: () => void }).unref?.();
      });
      const sibling = await new Handoff({ agent: alpha }).execute(ctx({ sourceAgent: sourceAgent('beta') }));

      expect(sibling.response).toBe('alpha ok');
      expect(sibling.context.handoffChain).toEqual(['beta']);
      await inFlight;
    });
  });

  describe('the refusal reaches the caller', () => {
    it('invokes onError before rethrowing', async () => {
      const onError = jest.fn<(error: Error) => void>();
      const h = new Handoff({ agent: fakeAgent('alpha'), maxDepth: 1, onError });

      await expect(h.execute(ctx({ handoffChain: ['x'] }))).rejects.toThrow(HandoffDepthError);
      expect(onError).toHaveBeenCalledWith(expect.any(HandoffDepthError));
    });
  });
});
