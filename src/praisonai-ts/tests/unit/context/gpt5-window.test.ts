import { BALANCED_POLICY, getModelLimit } from '../../../src/context/policy';

test.each(['gpt-5', 'gpt-5-mini', 'gpt-5-nano', 'gpt-5-2025-08-07'])('uses the documented GPT-5 full window for %s', model => {
  expect(getModelLimit(model)).toBe(400000);
  const budget = BALANCED_POLICY.computeContextBudget([{ role: 'user', content: 'hello' }], model);
  expect(budget.details.modelLimit).toBe(400000);
});

test.each([
  ['gpt-5.4', 1050000], ['gpt-5.4-pro', 1050000],
  ['gpt-5.4-mini', 400000], ['gpt-5.4-nano', 400000],
  ['gpt-5.4-mini-2026-03-17', 400000],
  ['openai/gpt-5.4-2026-03-05', 1050000],
] as const)('does not shadow the more specific %s window', (model, limit) => {
  expect(getModelLimit(model)).toBe(limit);
});
