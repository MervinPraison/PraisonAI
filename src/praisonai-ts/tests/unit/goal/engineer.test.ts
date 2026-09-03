/**
 * GoalEngineer (Python parity: praisonaiagents/goal/engineer.py) driven by a
 * stubbed LLM.
 */

import { GoalEngineer, GoalConfig, GoalVerificationResult, GoalLLM } from '../../../src/goal';

function stubLLM(reply: string | ((prompt: string) => string)): GoalLLM & { prompts: string[] } {
  const prompts: string[] = [];
  return {
    prompts,
    async generate(prompt: string) {
      prompts.push(prompt);
      return { text: typeof reply === 'function' ? reply(prompt) : reply };
    },
  };
}

describe('GoalEngineer constructor', () => {
  it('applies Python defaults via GoalConfig', () => {
    const engineer = new GoalEngineer();
    expect(engineer.config).toBeInstanceOf(GoalConfig);
    expect(engineer.config.maxCriteria).toBe(5);
    expect(engineer.config.threshold).toBe(8.0);
    expect(engineer.config.autoDecompose).toBe(true);
    expect(engineer.config.verbose).toBe(false);
  });

  it('lets kwargs override a supplied config', () => {
    const config = new GoalConfig({ maxCriteria: 2, threshold: 5 });
    const engineer = new GoalEngineer({ config, threshold: 9, autoDecompose: false, model: 'm' });
    expect(engineer.config).toBe(config);
    expect(engineer.config.maxCriteria).toBe(2);
    expect(engineer.config.threshold).toBe(9);
    expect(engineer.config.autoDecompose).toBe(false);
    expect(engineer.config.model).toBe('m');
  });
});

describe('GoalEngineer.engineer', () => {
  it('parses a JSON-array reply from the stubbed LLM into criteria', async () => {
    const llm = stubLLM('Sure:\n["Under 100 words", "Keeps key findings"]');
    const engineer = new GoalEngineer({ llm, maxCriteria: 3 });
    const goal = await engineer.engineer('Summarise the report', null, ['No hallucinations']);
    expect(goal.criteria.map((c) => c.description)).toEqual(['Under 100 words', 'Keeps key findings']);
    expect(goal.constraints).toEqual(['No hallucinations']);
    expect(llm.prompts).toHaveLength(1);
    expect(llm.prompts[0]).toContain('at most 3');
    expect(llm.prompts[0]).toContain('GOAL: Summarise the report');
  });

  it('control: a malformed (non-JSON) reply falls back to bullet splitting', async () => {
    const llm = stubLLM('- first thing\n2. second thing\n\n* third');
    const goal = await new GoalEngineer({ llm }).engineer('x');
    expect(goal.criteria.map((c) => c.description)).toEqual(['first thing', 'second thing', 'third']);
  });

  it('control: an LLM failure yields a goal with no criteria', async () => {
    const llm: GoalLLM = { generate: async () => { throw new Error('offline'); } };
    const goal = await new GoalEngineer({ llm }).engineer('x');
    expect(goal.criteria).toEqual([]);
    expect(goal.statement).toBe('x');
  });

  it('uses explicit criteria without calling the LLM', async () => {
    const llm = stubLLM('["ignored"]');
    const goal = await new GoalEngineer({ llm }).engineer('x', ['a', 'b']);
    expect(goal.criteria.map((c) => c.description)).toEqual(['a', 'b']);
    expect(llm.prompts).toHaveLength(0);
  });

  it('skips decomposition when autoDecompose is false', async () => {
    const llm = stubLLM('["ignored"]');
    const goal = await new GoalEngineer({ llm, autoDecompose: false }).engineer('x');
    expect(goal.criteria).toEqual([]);
    expect(llm.prompts).toHaveLength(0);
  });
});

describe('GoalEngineer.parseCriteria', () => {
  it('drops blank items and stringifies non-strings', () => {
    expect(GoalEngineer.parseCriteria('[" a ", "", 3]')).toEqual(['a', '3']);
  });
});

describe('GoalEngineer.verify', () => {
  it('returns an achieved GoalVerificationResult when the judge score meets the threshold', async () => {
    const llm = stubLLM('SCORE: 9\nREASONING: Meets every criterion.\nSUGGESTIONS:\n- none');
    const engineer = new GoalEngineer({ llm, autoDecompose: false });
    const goal = await engineer.engineer('Summarise', ['Short', 'Accurate'], ['No jargon']);

    const result = await engineer.verify(goal, 'A short accurate summary.');

    expect(result).toBeInstanceOf(GoalVerificationResult);
    expect(result.goalId).toBe(goal.id);
    expect(result.score).toBe(9);
    expect(result.achieved).toBe(true);
    expect(result.reasoning).toBe('Meets every criterion.');
    expect(result.criteria.map((c) => c.status)).toEqual(['met', 'met']);
    expect(goal.isAchieved).toBe(true);

    // The judge prompt carries the goal, criteria and constraints.
    expect(llm.prompts[0]).toContain('Goal: Summarise');
    expect(llm.prompts[0]).toContain('- Short');
    expect(llm.prompts[0]).toContain('Constraints (must not be violated):\n- No jargon');
    expect(llm.prompts[0]).toContain('A short accurate summary.');
  });

  it('marks criteria unmet below the threshold', async () => {
    const llm = stubLLM('SCORE: 4\nREASONING: Too long.');
    const engineer = new GoalEngineer({ llm, autoDecompose: false, threshold: 8 });
    const goal = await engineer.engineer('Summarise', ['Short']);
    const result = await engineer.verify(goal, 'A very long summary');
    expect(result.achieved).toBe(false);
    expect(result.score).toBe(4);
    expect(goal.criteria[0].status).toBe('unmet');
  });

  it('control: a malformed judge reply still returns a result and is not achieved', async () => {
    const llm = stubLLM('I cannot evaluate this.');
    const engineer = new GoalEngineer({ llm, autoDecompose: false });
    const goal = await engineer.engineer('Summarise', ['Short']);
    const result = await engineer.verify(goal, 'text');
    expect(result).toBeInstanceOf(GoalVerificationResult);
    expect(result.achieved).toBe(false);
    expect(result.score).toBeLessThan(engineer.config.threshold);
    expect(result.reasoning).toBe('Unable to parse response');
    expect(goal.criteria[0].status).toBe('unmet');
  });

  it('control: an LLM failure is inconclusive - criteria stay pending', async () => {
    const llm: GoalLLM = { generate: async () => { throw new Error('offline'); } };
    const engineer = new GoalEngineer({ llm, autoDecompose: false });
    const goal = await engineer.engineer('Summarise', ['Short']);
    const result = await engineer.verify(goal, 'text');
    expect(result.achieved).toBe(false);
    expect(result.score).toBe(0);
    expect(result.reasoning).toContain('Verification unavailable: offline');
    expect(goal.criteria[0].status).toBe('pending');
    expect(result.criteria[0].status).toBe('pending');
  });

  it('returns a snapshot so mutating the result does not touch the goal', async () => {
    const llm = stubLLM('SCORE: 10\nREASONING: ok');
    const engineer = new GoalEngineer({ llm, autoDecompose: false });
    const goal = await engineer.engineer('g', ['a']);
    const result = await engineer.verify(goal, 'out');
    result.criteria[0].status = 'unmet';
    expect(goal.criteria[0].status).toBe('met');
  });
});
