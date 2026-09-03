/**
 * Data models for Goal Engineering.
 *
 * Python parity: praisonaiagents/goal/models.py. A {@link Goal} is a
 * structured, measurable representation of what an agent should achieve. It
 * is decomposed into {@link SuccessCriterion} items that can be tracked and
 * verified independently.
 */

import { randomUUID } from '../utils/uuid';

/** Python parity: goal/models.py:14 `CriterionStatus`. */
export type CriterionStatus = 'pending' | 'met' | 'unmet';

/** Python's `str(uuid.uuid4())[:8]` default id (goal/models.py:31, :70). */
function shortId(): string {
  return randomUUID().slice(0, 8);
}

// ============================================================================
// SuccessCriterion
// ============================================================================

/** Constructor options for {@link SuccessCriterion} (goal/models.py:18-34). */
export interface SuccessCriterionOptions {
  /** What must be true for this criterion to be met. */
  description: string;
  /** Unique identifier (default: 8-char UUID prefix). */
  id?: string;
  /** Relative importance when scoring the goal (default 1.0). */
  weight?: number;
  /** Current status (default "pending"). */
  status?: CriterionStatus;
  /** Optional notes from verification (default ""). */
  notes?: string;
}

/**
 * A single measurable condition that contributes to achieving a goal.
 *
 * Python parity: goal/models.py:18 `SuccessCriterion`.
 */
export class SuccessCriterion {
  description: string;
  id: string;
  weight: number;
  status: CriterionStatus;
  notes: string;

  constructor(options: SuccessCriterionOptions) {
    this.description = options.description;
    this.id = options.id ?? shortId();
    this.weight = options.weight ?? 1.0;
    this.status = options.status ?? 'pending';
    this.notes = options.notes ?? '';
  }

  /** Python parity: goal/models.py:36 `to_dict`. */
  toDict(): Record<string, unknown> {
    return {
      id: this.id,
      description: this.description,
      weight: this.weight,
      status: this.status,
      notes: this.notes,
    };
  }

  /** Python parity: goal/models.py:46 `from_dict`. */
  static fromDict(data: Record<string, unknown>): SuccessCriterion {
    return new SuccessCriterion({
      description: String(data.description ?? ''),
      id: data.id !== undefined ? String(data.id) : shortId(),
      weight: Number(data.weight ?? 1.0),
      status: (data.status as CriterionStatus | undefined) ?? 'pending',
      notes: String(data.notes ?? ''),
    });
  }

  /** Independent copy (Python `dataclasses.replace(criterion)`, goal/engineer.py:199). */
  clone(): SuccessCriterion {
    return new SuccessCriterion({
      description: this.description,
      id: this.id,
      weight: this.weight,
      status: this.status,
      notes: this.notes,
    });
  }
}

// ============================================================================
// Goal
// ============================================================================

/** Constructor options for {@link Goal} (goal/models.py:57-73). */
export interface GoalOptions {
  /** The high-level objective in natural language. */
  statement: string;
  /** Unique identifier (default: 8-char UUID prefix). */
  id?: string;
  /** Ordered list of success criteria (default []). */
  criteria?: SuccessCriterion[];
  /** Hard constraints that must never be violated (default []). */
  constraints?: string[];
  /** Free-form metadata (domain, owner, etc.) (default {}). */
  metadata?: Record<string, unknown>;
}

/**
 * A structured, measurable goal for an agent.
 *
 * Python parity: goal/models.py:57 `Goal`.
 */
export class Goal {
  statement: string;
  id: string;
  criteria: SuccessCriterion[];
  constraints: string[];
  metadata: Record<string, unknown>;

  constructor(options: GoalOptions) {
    this.statement = options.statement;
    this.id = options.id ?? shortId();
    this.criteria = options.criteria ?? [];
    this.constraints = options.constraints ?? [];
    this.metadata = options.metadata ?? {};
  }

  /**
   * Add a success criterion and return it.
   *
   * Python parity: goal/models.py:75 `add_criterion(description, weight=1.0)`.
   */
  addCriterion(description: string, weight: number = 1.0): SuccessCriterion {
    const criterion = new SuccessCriterion({ description, weight });
    this.criteria.push(criterion);
    return criterion;
  }

  /**
   * Fraction of weighted criteria currently met (0.0 - 1.0).
   *
   * Non-positive weights are treated as 0 so a single criterion cannot skew
   * the fraction outside the documented range. If no criterion carries a
   * positive weight, criteria are counted equally.
   *
   * Python parity: goal/models.py:84 `progress`.
   */
  get progress(): number {
    if (this.criteria.length === 0) {
      return 0.0;
    }
    const total = this.criteria.reduce((sum, c) => sum + Math.max(c.weight, 0.0), 0);
    if (total <= 0.0) {
      const met = this.criteria.filter((c) => c.status === 'met').length;
      return met / this.criteria.length;
    }
    const met = this.criteria
      .filter((c) => c.status === 'met')
      .reduce((sum, c) => sum + Math.max(c.weight, 0.0), 0);
    return met / total;
  }

  /**
   * True when there is at least one criterion and all are met.
   *
   * Python parity: goal/models.py:103 `is_achieved`.
   */
  get isAchieved(): boolean {
    return this.criteria.length > 0 && this.criteria.every((c) => c.status === 'met');
  }

  /** Python parity: goal/models.py:109 `to_dict`. */
  toDict(): Record<string, unknown> {
    return {
      id: this.id,
      statement: this.statement,
      criteria: this.criteria.map((c) => c.toDict()),
      constraints: [...this.constraints],
      metadata: { ...this.metadata },
    };
  }

  /** Python parity: goal/models.py:119 `from_dict`. */
  static fromDict(data: Record<string, unknown>): Goal {
    const rawCriteria = Array.isArray(data.criteria) ? data.criteria : [];
    return new Goal({
      statement: String(data.statement ?? ''),
      id: data.id !== undefined ? String(data.id) : shortId(),
      criteria: rawCriteria.map((c) => SuccessCriterion.fromDict(c as Record<string, unknown>)),
      constraints: Array.isArray(data.constraints) ? data.constraints.map(String) : [],
      metadata: { ...((data.metadata as Record<string, unknown> | undefined) ?? {}) },
    });
  }

  /**
   * Render the goal as an instruction block for an agent prompt.
   *
   * Python parity: goal/models.py:130 `to_prompt`.
   */
  toPrompt(): string {
    const lines = [`Goal: ${this.statement}`];
    if (this.criteria.length > 0) {
      lines.push('Success criteria:');
      for (const c of this.criteria) {
        lines.push(`  - ${c.description}`);
      }
    }
    if (this.constraints.length > 0) {
      lines.push('Constraints (must never be violated):');
      for (const constraint of this.constraints) {
        lines.push(`  - ${constraint}`);
      }
    }
    return lines.join('\n');
  }
}

// ============================================================================
// GoalCriteria / GoalState (goal-gated autonomous loop bookkeeping)
// ============================================================================

/** Constructor options for {@link GoalCriteria} (goal/models.py:145-157). */
export interface GoalCriteriaOptions {
  /** What "done" means, in one line (default ""). */
  outcome?: string;
  /** How to check it - the concrete bar the judge uses (default ""). */
  verification?: string;
  /** Must-not-violate conditions; any violation blocks `done` (default []). */
  constraints?: string[];
}

/**
 * A structured "definition of done" for a goal-gated autonomous loop.
 *
 * Python parity: goal/models.py:145 `GoalCriteria`.
 */
export class GoalCriteria {
  outcome: string;
  verification: string;
  constraints: string[];

  constructor(options: GoalCriteriaOptions = {}) {
    this.outcome = options.outcome ?? '';
    this.verification = options.verification ?? '';
    this.constraints = options.constraints ?? [];
  }

  /** Python parity: goal/models.py:159 `to_dict`. */
  toDict(): Record<string, unknown> {
    return {
      outcome: this.outcome,
      verification: this.verification,
      constraints: [...this.constraints],
    };
  }

  /** Python parity: goal/models.py:167 `from_dict`. */
  static fromDict(data: Record<string, unknown>): GoalCriteria {
    return new GoalCriteria({
      outcome: String(data.outcome ?? ''),
      verification: String(data.verification ?? ''),
      constraints: Array.isArray(data.constraints) ? data.constraints.map(String) : [],
    });
  }
}

/** Constructor options for {@link GoalState} (goal/models.py:176-201). */
export interface GoalStateOptions {
  /** The goal text (free text, or paired with `criteria`). */
  goal: string;
  /** Optional structured acceptance criteria (default null). */
  criteria?: GoalCriteria | null;
  /** `active` | `paused` | `done` (default "active"). */
  status?: string;
  /** Judged iterations consumed so far (default 0). */
  turnsUsed?: number;
  /** Budget of judged iterations before a recoverable pause (default 20). */
  maxTurns?: number;
  /** Most recent judge verdict (`done` | `continue`) (default ""). */
  lastVerdict?: string;
  /** Most recent judge reason (default ""). */
  lastReason?: string;
  /** Consecutive unparseable judge responses (default 0). */
  consecutiveParseFailures?: number;
}

/**
 * Persistent state for a goal-gated autonomous loop.
 *
 * Python parity: goal/models.py:176 `GoalState`.
 */
export class GoalState {
  goal: string;
  criteria: GoalCriteria | null;
  status: string;
  turnsUsed: number;
  maxTurns: number;
  lastVerdict: string;
  lastReason: string;
  consecutiveParseFailures: number;

  constructor(options: GoalStateOptions) {
    this.goal = options.goal;
    this.criteria = options.criteria ?? null;
    this.status = options.status ?? 'active';
    this.turnsUsed = options.turnsUsed ?? 0;
    this.maxTurns = options.maxTurns ?? 20;
    this.lastVerdict = options.lastVerdict ?? '';
    this.lastReason = options.lastReason ?? '';
    this.consecutiveParseFailures = options.consecutiveParseFailures ?? 0;
  }

  /** Python parity: goal/models.py:203 `to_dict` (snake_case keys for wire compatibility). */
  toDict(): Record<string, unknown> {
    return {
      goal: this.goal,
      criteria: this.criteria ? this.criteria.toDict() : null,
      status: this.status,
      turns_used: this.turnsUsed,
      max_turns: this.maxTurns,
      last_verdict: this.lastVerdict,
      last_reason: this.lastReason,
      consecutive_parse_failures: this.consecutiveParseFailures,
    };
  }

  /** Python parity: goal/models.py:216 `from_dict` (accepts snake_case or camelCase keys). */
  static fromDict(data: Record<string, unknown>): GoalState {
    const criteriaData = data.criteria as Record<string, unknown> | null | undefined;
    const pick = (snake: string, camel: string): unknown => data[snake] ?? data[camel];
    return new GoalState({
      goal: String(data.goal ?? ''),
      criteria: criteriaData ? GoalCriteria.fromDict(criteriaData) : null,
      status: String(data.status ?? 'active'),
      turnsUsed: Math.trunc(Number(pick('turns_used', 'turnsUsed') ?? 0)),
      maxTurns: Math.trunc(Number(pick('max_turns', 'maxTurns') ?? 20)),
      lastVerdict: String(pick('last_verdict', 'lastVerdict') ?? ''),
      lastReason: String(pick('last_reason', 'lastReason') ?? ''),
      consecutiveParseFailures: Math.trunc(
        Number(pick('consecutive_parse_failures', 'consecutiveParseFailures') ?? 0)
      ),
    });
  }
}

// ============================================================================
// GoalVerificationResult
// ============================================================================

/** Constructor options for {@link GoalVerificationResult} (goal/models.py:235-251). */
export interface GoalVerificationResultOptions {
  /** The verified goal's id. */
  goalId: string;
  /** Overall score in the 0.0 - 10.0 range. */
  score: number;
  /** Whether the goal is considered achieved. */
  achieved: boolean;
  /** The (updated) criteria with their statuses (default []). */
  criteria?: SuccessCriterion[];
  /** Explanation of the verification (default ""). */
  reasoning?: string;
}

/**
 * Outcome of verifying an output against a goal.
 *
 * Python parity: goal/models.py:235 `GoalVerificationResult`.
 */
export class GoalVerificationResult {
  goalId: string;
  score: number;
  achieved: boolean;
  criteria: SuccessCriterion[];
  reasoning: string;

  constructor(options: GoalVerificationResultOptions) {
    this.goalId = options.goalId;
    this.score = options.score;
    this.achieved = options.achieved;
    this.criteria = options.criteria ?? [];
    this.reasoning = options.reasoning ?? '';
  }

  /** Python parity: goal/models.py:253 `to_dict` (snake_case `goal_id` for wire compatibility). */
  toDict(): Record<string, unknown> {
    return {
      goal_id: this.goalId,
      score: this.score,
      achieved: this.achieved,
      criteria: this.criteria.map((c) => c.toDict()),
      reasoning: this.reasoning,
    };
  }
}
