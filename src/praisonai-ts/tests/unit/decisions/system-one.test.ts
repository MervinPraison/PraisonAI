import { describe, expect, it, jest } from '@jest/globals';
import {
  choiceQuestion,
  getChoice,
  isDecisionModel,
  systemOne,
} from '../../../src/decisions';

describe('systemOne', () => {
  it('detects decision model ids', () => {
    expect(isDecisionModel('nimble')).toBe(true);
    expect(isDecisionModel('ollama/nimble')).toBe(true);
    expect(isDecisionModel('llama3.2')).toBe(false);
  });

  it('calls /v1/systemone and parses choice', async () => {
    const fetchImpl = jest.fn(async () => ({
      ok: true,
      status: 200,
      text: async () =>
        JSON.stringify({
          model: 'nimble',
          answers: {
            team: { type: 'choice', choice: 'billing', confidence: 0.9 },
          },
        }),
    })) as unknown as typeof fetch;

    const result = await systemOne(
      { ticket: 'refund' },
      { team: choiceQuestion('Team?', { billing: 'pay' }) },
      { apiBase: 'http://127.0.0.1:11434', fetchImpl },
    );

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, init] = (fetchImpl as jest.Mock).mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://127.0.0.1:11434/v1/systemone');
    expect(JSON.parse(String(init.body)).model).toBe('nimble');
    expect(getChoice(result, 'team')).toBe('billing');
  });
});
