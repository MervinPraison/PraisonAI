/**
 * Goal models (Python parity: praisonaiagents/goal/models.py).
 */

import { Goal, SuccessCriterion, GoalVerificationResult, GoalCriteria, GoalState } from '../../../src/goal';

describe('SuccessCriterion', () => {
  it('defaults weight 1.0, status pending, notes "" and an 8-char id', () => {
    const c = new SuccessCriterion({ description: 'd' });
    expect(c.weight).toBe(1.0);
    expect(c.status).toBe('pending');
    expect(c.notes).toBe('');
    expect(c.id).toHaveLength(8);
  });

  it('round-trips through toDict/fromDict', () => {
    const c = new SuccessCriterion({ description: 'd', id: 'abc12345', weight: 2, status: 'met', notes: 'n' });
    expect(SuccessCriterion.fromDict(c.toDict())).toEqual(c);
  });
});

describe('Goal.progress', () => {
  it('is 0 with no criteria', () => {
    expect(new Goal({ statement: 's' }).progress).toBe(0);
  });

  it('is the weighted fraction of met criteria', () => {
    const goal = new Goal({ statement: 's' });
    const a = goal.addCriterion('a', 3);
    goal.addCriterion('b', 1);
    expect(goal.progress).toBe(0);
    a.status = 'met';
    expect(goal.progress).toBeCloseTo(0.75);
  });

  it('clamps non-positive weights to 0', () => {
    const goal = new Goal({ statement: 's' });
    const a = goal.addCriterion('a', 1);
    const b = goal.addCriterion('b', -5);
    a.status = 'met';
    b.status = 'met';
    expect(goal.progress).toBe(1);
    b.status = 'unmet';
    expect(goal.progress).toBe(1);
  });

  it('counts criteria equally when no weight is positive', () => {
    const goal = new Goal({ statement: 's' });
    const a = goal.addCriterion('a', 0);
    goal.addCriterion('b', 0);
    a.status = 'met';
    expect(goal.progress).toBe(0.5);
  });
});

describe('Goal.isAchieved', () => {
  it('is false with no criteria and false until every criterion is met', () => {
    const goal = new Goal({ statement: 's' });
    expect(goal.isAchieved).toBe(false);
    const a = goal.addCriterion('a');
    const b = goal.addCriterion('b');
    a.status = 'met';
    expect(goal.isAchieved).toBe(false);
    b.status = 'met';
    expect(goal.isAchieved).toBe(true);
  });
});

describe('Goal.toPrompt', () => {
  it('renders statement, criteria and constraints in the Python layout', () => {
    const goal = new Goal({ statement: 'Ship it', constraints: ['No secrets'] });
    goal.addCriterion('Tests pass');
    goal.addCriterion('Docs updated');
    expect(goal.toPrompt()).toBe(
      ['Goal: Ship it', 'Success criteria:', '  - Tests pass', '  - Docs updated', 'Constraints (must never be violated):', '  - No secrets'].join('\n')
    );
  });

  it('omits empty sections', () => {
    expect(new Goal({ statement: 'Only' }).toPrompt()).toBe('Goal: Only');
  });
});

describe('Goal.toDict/fromDict', () => {
  it('round-trips and copies containers', () => {
    const goal = new Goal({ statement: 's', id: 'g1', constraints: ['c'], metadata: { k: 1 } });
    goal.addCriterion('a', 2);
    const dict = goal.toDict();
    expect(dict.constraints).not.toBe(goal.constraints);
    const back = Goal.fromDict(dict);
    expect(back.id).toBe('g1');
    expect(back.criteria[0].weight).toBe(2);
    expect(back.toPrompt()).toBe(goal.toPrompt());
  });
});

describe('GoalVerificationResult', () => {
  it('defaults criteria [] and reasoning "" and serialises goal_id', () => {
    const r = new GoalVerificationResult({ goalId: 'g', score: 9, achieved: true });
    expect(r.criteria).toEqual([]);
    expect(r.reasoning).toBe('');
    expect(r.toDict()).toEqual({ goal_id: 'g', score: 9, achieved: true, criteria: [], reasoning: '' });
  });
});

describe('GoalState', () => {
  it('defaults and round-trips with snake_case keys', () => {
    const state = new GoalState({ goal: 'g', criteria: new GoalCriteria({ outcome: 'o' }) });
    expect(state.maxTurns).toBe(20);
    expect(state.status).toBe('active');
    const dict = state.toDict();
    expect(dict.max_turns).toBe(20);
    const back = GoalState.fromDict(dict);
    expect(back.criteria?.outcome).toBe('o');
    expect(back.turnsUsed).toBe(0);
  });
});
