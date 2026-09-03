/**
 * Escalation Triggers for PraisonAI Agents.
 *
 * Python parity: praisonaiagents/escalation/triggers.py. Detects signals
 * that indicate escalation or de-escalation is needed. Uses heuristics only -
 * no extra LLM calls for signal detection.
 */

import {
  EscalationConfig,
  EscalationConfigOptions,
  EscalationSignal,
  EscalationStage,
  toEscalationConfig,
} from './types';

/**
 * Detects escalation signals from prompts and context.
 *
 * Python parity: escalation/triggers.py:13 `EscalationTrigger`.
 *
 * @example
 * const trigger = new EscalationTrigger();
 * const signals = trigger.analyze('Refactor the auth module');
 * const stage = trigger.recommendStage(signals);
 */
export class EscalationTrigger {
  /** Keywords indicating complex tasks (triggers.py:28). */
  static readonly COMPLEX_KEYWORDS: readonly string[] = [
    'analyze', 'research', 'comprehensive', 'detailed',
    'compare', 'evaluate', 'synthesize', 'multi-step',
    'code review', 'architecture', 'design pattern',
    'optimize', 'debug', 'refactor', 'implement',
    'build', 'create', 'develop', 'integrate',
  ];

  /** Keywords indicating simple tasks (triggers.py:37). */
  static readonly SIMPLE_KEYWORDS: readonly string[] = [
    'what is', 'define', 'list', 'name', 'when',
    'where', 'who', 'simple', 'quick', 'brief',
    'explain', 'describe', 'tell me', 'show me',
  ];

  /** Keywords indicating edit intent (triggers.py:44). */
  static readonly EDIT_KEYWORDS: readonly string[] = [
    'edit', 'modify', 'change', 'update', 'fix',
    'add', 'remove', 'delete', 'replace', 'rename',
    'write', 'create file', 'save',
  ];

  /** Keywords indicating test intent (triggers.py:51). */
  static readonly TEST_KEYWORDS: readonly string[] = [
    'test', 'run tests', 'pytest', 'unittest',
    'verify', 'check', 'validate', 'assert',
  ];

  /** Keywords indicating build intent (triggers.py:57). */
  static readonly BUILD_KEYWORDS: readonly string[] = [
    'build', 'compile', 'make', 'npm', 'pip install',
    'cargo build', 'go build', 'mvn', 'gradle',
  ];

  /** Keywords indicating refactor intent (triggers.py:63). */
  static readonly REFACTOR_KEYWORDS: readonly string[] = [
    'refactor', 'restructure', 'reorganize', 'clean up',
    'improve', 'optimize', 'simplify', 'extract',
    'move', 'split', 'merge', 'consolidate',
  ];

  /** File path pattern (triggers.py:70). */
  static readonly FILE_PATTERN = /(?:^|[\s'"(])([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)(?:[\s'")]|$)/m;

  /** Code block pattern (triggers.py:76). */
  static readonly CODE_BLOCK_PATTERN = /```[\s\S]*?```|`[^`]+`/;

  config: EscalationConfig;

  /** Python parity: escalation/triggers.py:78 `__init__(config=None)`. */
  constructor(config: EscalationConfig | EscalationConfigOptions | null = null) {
    this.config = toEscalationConfig(config);
  }

  /**
   * Analyze prompt and context for escalation signals.
   *
   * Python parity: escalation/triggers.py:82 `analyze(prompt, context=None)`.
   */
  analyze(prompt: string, context: Record<string, unknown> | null = null): Set<EscalationSignal> {
    const signals = new Set<EscalationSignal>();
    const promptLower = prompt.toLowerCase();
    const wordCount = prompt.split(/\s+/).filter((w) => w.length > 0).length;

    if (wordCount > this.config.longPromptThreshold) {
      signals.add(EscalationSignal.LONG_PROMPT);
    }

    const complexCount = EscalationTrigger.COMPLEX_KEYWORDS.filter((kw) => promptLower.includes(kw)).length;
    if (complexCount >= this.config.complexKeywordThreshold) {
      signals.add(EscalationSignal.COMPLEX_KEYWORDS);
    }

    const simpleCount = EscalationTrigger.SIMPLE_KEYWORDS.filter((kw) => promptLower.includes(kw)).length;
    if (simpleCount >= 1 && complexCount === 0 && wordCount < 30) {
      signals.add(EscalationSignal.SIMPLE_QUESTION);
    }

    if (this.hasMultiStepIntent(prompt)) {
      signals.add(EscalationSignal.MULTI_STEP_INTENT);
    }

    if (EscalationTrigger.FILE_PATTERN.test(prompt)) {
      signals.add(EscalationSignal.FILE_REFERENCES);
    }

    if (EscalationTrigger.CODE_BLOCK_PATTERN.test(prompt)) {
      signals.add(EscalationSignal.CODE_BLOCKS);
    }

    if (EscalationTrigger.EDIT_KEYWORDS.some((kw) => promptLower.includes(kw))) {
      signals.add(EscalationSignal.EDIT_INTENT);
    }

    if (EscalationTrigger.TEST_KEYWORDS.some((kw) => promptLower.includes(kw))) {
      signals.add(EscalationSignal.TEST_INTENT);
    }

    if (EscalationTrigger.BUILD_KEYWORDS.some((kw) => promptLower.includes(kw))) {
      signals.add(EscalationSignal.BUILD_INTENT);
    }

    if (EscalationTrigger.REFACTOR_KEYWORDS.some((kw) => promptLower.includes(kw))) {
      signals.add(EscalationSignal.REFACTOR_INTENT);
    }

    if (context) {
      if (context.is_git_repo || context.isGitRepo || context.workspace) {
        signals.add(EscalationSignal.REPO_CONTEXT);
      }
    }

    return signals;
  }

  /** Python parity: escalation/triggers.py:156 `_has_multi_step_intent`. */
  private hasMultiStepIntent(prompt: string): boolean {
    const promptLower = prompt.toLowerCase();

    const questionCount = (prompt.match(/\?/g) ?? []).length;
    if (questionCount > 1) {
      return true;
    }

    const sequentialPatterns = [
      'and then', 'after that', 'next,', 'finally,',
      'first,', 'second,', 'third,', 'step 1', 'step 2',
      '1.', '2.', '3.',
    ];
    if (sequentialPatterns.some((p) => promptLower.includes(p))) {
      return true;
    }

    const actionVerbs = ['create', 'update', 'delete', 'add', 'remove', 'fix', 'change'];
    const verbCount = actionVerbs.filter((v) => promptLower.includes(v)).length;
    if (verbCount > 2) {
      return true;
    }

    return false;
  }

  /**
   * Recommend an escalation stage based on signals.
   *
   * Python parity: escalation/triggers.py:182 `recommend_stage(signals, current_stage=None)`.
   */
  recommendStage(signals: Set<EscalationSignal>, currentStage: EscalationStage | null = null): EscalationStage {
    let stage = EscalationStage.DIRECT;

    if (signals.has(EscalationSignal.SIMPLE_QUESTION)) {
      if (!this.hasEscalationSignals(signals)) {
        return EscalationStage.DIRECT;
      }
    }

    const heuristicSignals = [
      EscalationSignal.FILE_REFERENCES,
      EscalationSignal.CODE_BLOCKS,
      EscalationSignal.REPO_CONTEXT,
    ];
    if (heuristicSignals.some((s) => signals.has(s))) {
      stage = Math.max(stage, EscalationStage.HEURISTIC);
    }

    const plannedSignals = [
      EscalationSignal.EDIT_INTENT,
      EscalationSignal.TEST_INTENT,
      EscalationSignal.BUILD_INTENT,
      EscalationSignal.COMPLEX_KEYWORDS,
    ];
    if (plannedSignals.some((s) => signals.has(s))) {
      stage = Math.max(stage, EscalationStage.PLANNED);
    }

    const autonomousSignals = [
      EscalationSignal.MULTI_STEP_INTENT,
      EscalationSignal.REFACTOR_INTENT,
      EscalationSignal.LONG_PROMPT,
    ];
    if (autonomousSignals.some((s) => signals.has(s))) {
      stage = Math.max(stage, EscalationStage.AUTONOMOUS);
    }

    if (currentStage !== null) {
      const failureSignals = [
        EscalationSignal.TOOL_FAILURE,
        EscalationSignal.INCOMPLETE_TASK,
        EscalationSignal.AMBIGUOUS_RESULT,
      ];
      if (failureSignals.some((s) => signals.has(s))) {
        stage = Math.max(stage, Math.min(currentStage + 1, 3));
      }
    }

    return stage as EscalationStage;
  }

  /** Python parity: escalation/triggers.py:246 `_has_escalation_signals`. */
  private hasEscalationSignals(signals: Set<EscalationSignal>): boolean {
    const escalationSignals = [
      EscalationSignal.COMPLEX_KEYWORDS,
      EscalationSignal.MULTI_STEP_INTENT,
      EscalationSignal.EDIT_INTENT,
      EscalationSignal.REFACTOR_INTENT,
      EscalationSignal.TOOL_FAILURE,
    ];
    return escalationSignals.some((s) => signals.has(s));
  }

  /**
   * Check if escalation is recommended.
   *
   * Python parity: escalation/triggers.py:257 `should_escalate(signals, current_stage, context=None)`.
   */
  shouldEscalate(
    signals: Set<EscalationSignal>,
    currentStage: EscalationStage,
    context: Record<string, unknown> | null = null
  ): boolean {
    void context; // Accepted for parity; Python does not consult it either.
    const recommended = this.recommendStage(signals, currentStage);
    return recommended > currentStage;
  }

  /**
   * Check if de-escalation is appropriate.
   *
   * Python parity: escalation/triggers.py:277 `should_deescalate(signals, current_stage, context=None)`.
   */
  shouldDeescalate(
    signals: Set<EscalationSignal>,
    currentStage: EscalationStage,
    context: Record<string, unknown> | null = null
  ): boolean {
    if (currentStage === EscalationStage.DIRECT) {
      return false;
    }

    if (signals.has(EscalationSignal.SIMPLE_QUESTION)) {
      if (!this.hasEscalationSignals(signals)) {
        return true;
      }
    }

    if (context) {
      if (context.task_complete || context.taskComplete) {
        return true;
      }
      const recentSteps = (context.recent_steps ?? context.recentSteps) as
        | Array<{ success?: boolean }>
        | undefined;
      if (Array.isArray(recentSteps) && recentSteps.length >= 3) {
        if (recentSteps.every((s) => s.success ?? true)) {
          return true;
        }
      }
    }

    return false;
  }

  /** Python parity: escalation/triggers.py:316 `get_stage_description(stage)`. */
  getStageDescription(stage: EscalationStage): string {
    switch (stage) {
      case EscalationStage.DIRECT:
        return 'Direct response (no tools)';
      case EscalationStage.HEURISTIC:
        return 'Heuristic tool selection';
      case EscalationStage.PLANNED:
        return 'Lightweight planning';
      case EscalationStage.AUTONOMOUS:
        return 'Full autonomous execution';
      default:
        return 'Unknown stage';
    }
  }
}
