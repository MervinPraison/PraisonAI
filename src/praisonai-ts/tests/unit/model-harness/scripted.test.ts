/**
 * The TypeScript half of praisonaiagents.model_harness: a scriptable model
 * double and a guard that blocks real provider calls.
 */
import { ScriptedModel, ScriptExhausted } from '../../../src/model-harness/scripted';
import {
  allowModelRequests,
  noModelRequests,
  modelRequestsAllowed,
  checkModelRequest,
  ModelRequestBlocked,
} from '../../../src/model-harness/guard';

describe('ScriptedModel', () => {
  it('returns scripted replies in order with no network', async () => {
    const model = new ScriptedModel(['first', 'second']);
    expect((await model.generate('a')).text).toBe('first');
    expect((await model.generate('b')).text).toBe('second');
  });

  it('records what the agent actually sent', async () => {
    const model = new ScriptedModel(['ok']);
    await model.generate('refund order A1', { systemPrompt: 'Support bot.' });
    expect(model.requestCount).toBe(1);
    expect(model.requests[0].prompt).toBe('refund order A1');
    expect(model.requests[0].systemPrompt).toBe('Support bot.');
  });

  it('a callable entry can answer based on the request', async () => {
    const model = new ScriptedModel([(req) => `echo:${req.prompt}`]);
    expect((await model.generate('hi')).text).toBe('echo:hi');
  });

  it('running out of script fails loudly rather than inventing a reply', async () => {
    const model = new ScriptedModel(['only one']);
    await model.generate('a');
    await expect(model.generate('b')).rejects.toThrow(ScriptExhausted);
  });

  it('control: a sufficient script does not throw', async () => {
    const model = new ScriptedModel(['a', 'b']);
    await model.generate('1');
    await expect(model.generate('2')).resolves.toBeDefined();
  });

  it('streams the scripted reply', async () => {
    const model = new ScriptedModel(['streamed']);
    const chunks: string[] = [];
    for await (const c of model.generateStream('go')) chunks.push(c);
    expect(chunks.join('')).toBe('streamed');
  });

  it('reset rewinds the script and the recording', async () => {
    const model = new ScriptedModel(['a']);
    await model.generate('x');
    model.reset();
    expect(model.requestCount).toBe(0);
    expect((await model.generate('x')).text).toBe('a');
  });
});

describe('model request guard', () => {
  afterEach(() => allowModelRequests(true));

  it('blocks a real call and names the call site', () => {
    allowModelRequests(false);
    let err: any;
    try {
      checkModelRequest('gpt-4o');
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(ModelRequestBlocked);
    expect(err.model).toBe('gpt-4o');
    expect(err.callSite).toBeTruthy();
  });

  it('control: allowed by default', () => {
    expect(modelRequestsAllowed()).toBe(true);
    expect(() => checkModelRequest('gpt-4o')).not.toThrow();
  });

  it('overlapping scopes stay blocked until every one exits', async () => {
    // The Python guard originally saved and restored a shared boolean, so an
    // inner scope exiting first re-enabled requests while an outer scope was
    // still open. A counter is why that cannot happen here.
    let innerSawBlocked = false;
    let afterInnerStillBlocked = false;
    await noModelRequests(async () => {
      await noModelRequests(async () => {
        innerSawBlocked = !modelRequestsAllowed();
      });
      afterInnerStillBlocked = !modelRequestsAllowed();
    });
    expect(innerSawBlocked).toBe(true);
    expect(afterInnerStillBlocked).toBe(true);
    expect(modelRequestsAllowed()).toBe(true);
  });
});
