/**
 * Goal Engineering Module for PraisonAI Agents.
 *
 * Python parity: praisonaiagents/goal/__init__.py. Goal Engineering is the
 * systematic practice of turning a vague objective into a structured,
 * measurable goal - a statement plus weighted success criteria and
 * constraints - then verifying agent output against it.
 *
 * @example
 * import { GoalEngineer } from 'praisonai/goal';
 *
 * const engineer = new GoalEngineer();
 * const goal = await engineer.engineer('Summarise the report in under 100 words');
 * const result = await engineer.verify(goal, agentOutput);
 * console.log(result.score, result.achieved);
 */

export { GoalEngineer } from './engineer';
export type { GoalEngineerOptions, GoalLLM } from './engineer';
export { GoalConfig, resolveDefaultModel } from './config';
export type { GoalConfigOptions } from './config';
export { Goal, SuccessCriterion, GoalVerificationResult, GoalCriteria, GoalState } from './models';
export type {
  CriterionStatus,
  GoalOptions,
  SuccessCriterionOptions,
  GoalVerificationResultOptions,
  GoalCriteriaOptions,
  GoalStateOptions,
} from './models';
