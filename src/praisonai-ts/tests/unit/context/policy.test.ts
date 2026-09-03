/**
 * Tests for the context compaction policy (Python parity).
 *
 * Paired with:
 * - praisonaiagents/context/adapters.py (ContextCompactionPolicyAdapter, presets)
 * - praisonaiagents/context/protocols.py (enums, ContextBudgetResult, protocol)
 * - praisonaiagents/tests/unit/test_context_compaction_policy.py
 *
 * The "Python reference" numbers below were produced by running the real
 * Python implementation (no mocks) over the same inputs; see the comments on
 * each case for the exact Python call.
 */

import {
  AGGRESSIVE_POLICY,
  BALANCED_POLICY,
  CONSERVATIVE_POLICY,
  CompactionRoute,
  CompactionStrategy,
  ContextBudgetResult,
  ContextCompactionPolicy,
  type ContextCompactionPolicyProtocol,
  type ContextMessage,
  getDefaultPolicy,
  isContextCompactionPolicy,
  toCompactionStrategy,
} from '../../../src/context';
import {
  MODEL_LIMITS,
  OUTPUT_RESERVES,
  estimateMessagesTokens,
  estimateTokensHeuristic,
  estimateToolSchemaTokens,
  getModelLimit,
  getOutputReserve,
} from '../../../src/context/policy';

// ---------------------------------------------------------------------------
// Shared fixtures (identical to the Python reference script)
// ---------------------------------------------------------------------------

const TOOLS = [
  {
    type: 'function',
    function: {
      name: 'search',
      description: 'Search the web',
      parameters: {
        type: 'object',
        properties: { q: { type: 'string' }, limit: { type: 'integer', default: 5 } },
        required: ['q'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'தேடல்',
      description: 'Tamil name — unicode',
      parameters: { type: 'object', properties: {} },
    },
  },
];

const TOOL_MSG: ContextMessage = { role: 'tool', content: 'x'.repeat(2000), tool_call_id: 'call_123' };
const MULTI_MSG: ContextMessage = {
  role: 'user',
  content: [
    { type: 'text', text: 'look at this' },
    { type: 'image_url', image_url: { url: 'http://x' } },
    { type: 'audio', data: 'abc' },
    'raw part',
  ],
};
const TOOL_CALL_MSG: ContextMessage = {
  role: 'assistant',
  content: null,
  tool_calls: [{ id: 'c1', type: 'function', function: { name: 'search', arguments: '{"q": "cats"}' } }],
};
const NAMED_MSG: ContextMessage = { role: 'user', name: 'alice', content: 'hi' };
const TAMIL_MSG: ContextMessage = { role: 'user', content: 'வணக்கம் world' };

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

describe('CompactionRoute / CompactionStrategy (Python parity)', () => {
  it('CompactionRoute values equal Python enum values', () => {
    expect(CompactionRoute.FITS).toBe('fits');
    expect(CompactionRoute.COMPACT_NEEDED).toBe('compact_needed');
    expect(CompactionRoute.TRUNCATE_TOOLS).toBe('truncate_tools');
    expect(CompactionRoute.COMPACT_THEN_TRUNCATE).toBe('compact_then_truncate');
  });

  it('CompactionStrategy values equal Python enum values', () => {
    expect(CompactionStrategy.TRUNCATE).toBe('truncate');
    expect(CompactionStrategy.SUMMARISE).toBe('summarise');
    expect(CompactionStrategy.DROP_OLDEST_TOOLS).toBe('drop_oldest_tools');
    expect(CompactionStrategy.SLIDING_WINDOW).toBe('sliding_window');
  });

  it('toCompactionStrategy lower-cases like Python CompactionStrategy(value.lower())', () => {
    expect(toCompactionStrategy('SUMMARISE')).toBe('summarise');
    expect(toCompactionStrategy('Drop_Oldest_Tools')).toBe('drop_oldest_tools');
    expect(() => toCompactionStrategy('bogus')).toThrow("'bogus' is not a valid CompactionStrategy");
  });
});

// ---------------------------------------------------------------------------
// Presets
// ---------------------------------------------------------------------------

describe('Policy presets (Python parity with adapters.py)', () => {
  // Python: CONSERVATIVE_POLICY.to_dict()
  it('CONSERVATIVE_POLICY matches Python', () => {
    expect(CONSERVATIVE_POLICY.toDict()).toEqual({
      triggerAt: 0.8,
      strategy: 'drop_oldest_tools',
      preserveLastNTurns: 8,
      maxCompactionAttempts: 2,
      targetUtilization: 0.6,
      aggressiveToolTruncation: true,
      modelOverrides: null,
    });
  });

  // Python: BALANCED_POLICY.to_dict()
  it('BALANCED_POLICY matches Python', () => {
    expect(BALANCED_POLICY.toDict()).toEqual({
      triggerAt: 0.9,
      strategy: 'drop_oldest_tools',
      preserveLastNTurns: 5,
      maxCompactionAttempts: 2,
      targetUtilization: 0.7,
      aggressiveToolTruncation: true,
      modelOverrides: null,
    });
  });

  // Python: AGGRESSIVE_POLICY.to_dict()
  it('AGGRESSIVE_POLICY matches Python', () => {
    expect(AGGRESSIVE_POLICY.toDict()).toEqual({
      triggerAt: 0.95,
      strategy: 'summarise',
      preserveLastNTurns: 3,
      maxCompactionAttempts: 2,
      targetUtilization: 0.75,
      aggressiveToolTruncation: true,
      modelOverrides: null,
    });
  });

  it('constructor defaults equal the Python dataclass defaults', () => {
    const p = new ContextCompactionPolicy();
    expect(p.triggerAt).toBe(0.9);
    expect(p.strategy).toBe(CompactionStrategy.DROP_OLDEST_TOOLS);
    expect(p.preserveLastNTurns).toBe(5);
    expect(p.maxCompactionAttempts).toBe(2);
    expect(p.targetUtilization).toBe(0.7);
    expect(p.aggressiveToolTruncation).toBe(true);
    expect(p.modelOverrides).toBeNull();
    // The default policy *is* the balanced preset.
    expect(p.toDict()).toEqual(BALANCED_POLICY.toDict());
  });

  // Python: test_mutable_singleton_fix
  it('getDefaultPolicy returns an independent copy of BALANCED_POLICY', () => {
    const policy1 = getDefaultPolicy();
    const policy2 = getDefaultPolicy();
    expect(policy1).not.toBe(policy2);
    expect(policy1).not.toBe(BALANCED_POLICY);
    expect(policy1.triggerAt).toBe(policy2.triggerAt);

    policy1.triggerAt = 0.95;
    expect(policy2.triggerAt).not.toBe(0.95);
    expect(BALANCED_POLICY.triggerAt).toBe(0.9);

    policy1.modelOverrides = { 'gpt-4': { triggerAt: 0.88 } };
    expect(policy2.modelOverrides).toBeNull();
    expect(BALANCED_POLICY.modelOverrides).toBeNull();
  });

  it('presets satisfy the protocol', () => {
    expect(isContextCompactionPolicy(BALANCED_POLICY)).toBe(true);
    expect(isContextCompactionPolicy({})).toBe(false);
    expect(isContextCompactionPolicy(null)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Validation (Python: __post_init__, test_policy_validation)
// ---------------------------------------------------------------------------

describe('ContextCompactionPolicy validation (Python parity)', () => {
  it('accepts a valid configuration', () => {
    const p = new ContextCompactionPolicy({ triggerAt: 0.85, targetUtilization: 0.65 });
    expect(p.triggerAt).toBe(0.85);
    expect(p.targetUtilization).toBe(0.65);
  });

  it('rejects trigger_at outside [0.1, 0.99]', () => {
    expect(() => new ContextCompactionPolicy({ triggerAt: 1.1 })).toThrow('trigger_at must be between 0.1 and 0.99');
    expect(() => new ContextCompactionPolicy({ triggerAt: 0.05 })).toThrow('trigger_at must be between 0.1 and 0.99');
  });

  it('rejects target_utilization outside [0.1, 0.95]', () => {
    expect(() => new ContextCompactionPolicy({ triggerAt: 0.99, targetUtilization: 0.96 })).toThrow(
      'target_utilization must be between 0.1 and 0.95',
    );
    expect(() => new ContextCompactionPolicy({ targetUtilization: 0.05 })).toThrow(
      'target_utilization must be between 0.1 and 0.95',
    );
  });

  it('rejects trigger_at <= target_utilization', () => {
    expect(() => new ContextCompactionPolicy({ triggerAt: 0.75, targetUtilization: 0.85 })).toThrow(
      'trigger_at must be greater than target_utilization',
    );
    expect(() => new ContextCompactionPolicy({ triggerAt: 0.7, targetUtilization: 0.7 })).toThrow(
      'trigger_at must be greater than target_utilization',
    );
  });

  it('converts a string strategy to the enum value', () => {
    expect(new ContextCompactionPolicy({ strategy: 'SUMMARISE' }).strategy).toBe('summarise');
    expect(() => new ContextCompactionPolicy({ strategy: 'nope' })).toThrow('is not a valid CompactionStrategy');
  });
});

// ---------------------------------------------------------------------------
// Serialization (Python: test_policy_serialization, test_execution_config_round_trip)
// ---------------------------------------------------------------------------

describe('ContextCompactionPolicy serialization (Python parity)', () => {
  it('round-trips through toDict / fromDict', () => {
    const original = new ContextCompactionPolicy({
      triggerAt: 0.88,
      strategy: CompactionStrategy.SUMMARISE,
      preserveLastNTurns: 4,
      maxCompactionAttempts: 3,
      targetUtilization: 0.65,
      aggressiveToolTruncation: false,
      modelOverrides: { 'gpt-4': { triggerAt: 0.9 } },
    });

    const data = original.toDict();
    expect(Object.keys(data).sort()).toEqual(
      [
        'triggerAt',
        'strategy',
        'preserveLastNTurns',
        'maxCompactionAttempts',
        'targetUtilization',
        'aggressiveToolTruncation',
        'modelOverrides',
      ].sort(),
    );

    const restored = ContextCompactionPolicy.fromDict(data);
    expect(restored.toDict()).toEqual(data);
    expect(restored.strategy).toBe(CompactionStrategy.SUMMARISE);
    // Deep copy: mutating the restored overrides must not touch the original.
    restored.modelOverrides!['gpt-4'].triggerAt = 0.5;
    expect(original.modelOverrides!['gpt-4'].triggerAt).toBe(0.9);
  });

  it('fromDict accepts Python snake_case keys', () => {
    // Exactly what Python's to_dict() emits for CONSERVATIVE_POLICY.
    const restored = ContextCompactionPolicy.fromDict({
      trigger_at: 0.8,
      strategy: 'drop_oldest_tools',
      preserve_last_n_turns: 8,
      max_compaction_attempts: 2,
      target_utilization: 0.6,
      aggressive_tool_truncation: true,
      model_overrides: null,
    });
    expect(restored.toDict()).toEqual(CONSERVATIVE_POLICY.toDict());
  });

  it('clone() is a deep, independent copy', () => {
    const p = new ContextCompactionPolicy({ modelOverrides: { 'gpt-4': { triggerAt: 0.92 } } });
    const c = p.clone();
    c.modelOverrides!['gpt-4'].triggerAt = 0.5;
    expect(p.modelOverrides!['gpt-4'].triggerAt).toBe(0.92);
  });
});

// ---------------------------------------------------------------------------
// Token / model helpers (Python: tokens.py, budgeter.py)
// ---------------------------------------------------------------------------

describe('token estimation and model limits (Python parity)', () => {
  // Python: estimate_tokens_heuristic(s)
  it('estimateTokensHeuristic matches Python for ASCII and non-ASCII text', () => {
    expect(estimateTokensHeuristic('')).toBe(0);
    expect(estimateTokensHeuristic('a')).toBe(1);
    expect(estimateTokensHeuristic('abcd')).toBe(1);
    expect(estimateTokensHeuristic('abcde')).toBe(1);
    expect(estimateTokensHeuristic('வணக்கம் world')).toBe(10);
    expect(estimateTokensHeuristic('héllo')).toBe(2);
  });

  // Python: estimate_messages_tokens([msg])
  it('estimateMessagesTokens matches Python for each message shape', () => {
    expect(estimateMessagesTokens([])).toBe(0);
    expect(estimateMessagesTokens([TOOL_MSG])).toBe(517);
    expect(estimateMessagesTokens([MULTI_MSG])).toBe(105);
    expect(estimateMessagesTokens([TOOL_CALL_MSG])).toBe(21);
    expect(estimateMessagesTokens([NAMED_MSG])).toBe(9);
    expect(estimateMessagesTokens([TAMIL_MSG])).toBe(17);
    expect(estimateMessagesTokens([{ role: 'user', name: null, content: 'x' }])).toBe(8);
  });

  // Python: estimate_tool_schema_tokens(tools) -- exercises json.dumps
  // separators and ensure_ascii escaping of the Tamil tool name.
  it('estimateToolSchemaTokens matches Python json.dumps-based estimate', () => {
    expect(estimateToolSchemaTokens(TOOLS)).toBe(99);
    expect(estimateToolSchemaTokens([])).toBe(0);
    expect(estimateToolSchemaTokens(null)).toBe(0);
  });

  // Python: get_model_limit(m), get_output_reserve(m)
  it('getModelLimit / getOutputReserve match Python', () => {
    const expected: Record<string, [number, number]> = {
      'gpt-4o-mini': [128000, 16384],
      'gpt-4': [8192, 4096],
      'gpt-4o-2024-05-13': [128000, 16384],
      'my-custom-model': [128000, 8000],
      'claude-3-5-sonnet-20241022': [200000, 8192],
      'gemini-1.5-pro': [2097152, 8192],
      'o3-mini': [200000, 100000],
      'GPT-4O': [128000, 16384],
    };
    for (const [model, [limit, reserve]] of Object.entries(expected)) {
      expect([model, getModelLimit(model)]).toEqual([model, limit]);
      expect([model, getOutputReserve(model)]).toEqual([model, reserve]);
    }
    expect(MODEL_LIMITS['default']).toBe(128000);
    expect(OUTPUT_RESERVES['default']).toBe(8000);
  });
});

// ---------------------------------------------------------------------------
// computeContextBudget -- real numbers, pinned from the Python implementation
// ---------------------------------------------------------------------------

describe('computeContextBudget (Python reference numbers)', () => {
  const big = (n: number): ContextMessage[] => [{ role: 'user', content: 'a'.repeat(n) }];

  it('returns a ContextBudgetResult instance', () => {
    const r = BALANCED_POLICY.computeContextBudget([{ role: 'user', content: 'Hello' }]);
    expect(r).toBeInstanceOf(ContextBudgetResult);
  });

  // Python: BALANCED_POLICY.compute_context_budget([user Hello, assistant Hi there!], model="gpt-4o-mini")
  it('small conversation fits', () => {
    const r = BALANCED_POLICY.computeContextBudget(
      [
        { role: 'user', content: 'Hello' },
        { role: 'assistant', content: 'Hi there!' },
      ],
      'gpt-4o-mini',
    );
    expect(r.route).toBe(CompactionRoute.FITS);
    expect(r.currentTokens).toBe(14);
    expect(r.availableTokens).toBe(111616);
    expect(r.utilization).toBeCloseTo(0.00012543004587155964, 12);
    expect(r.needsAction).toBe(false);
    expect(r.recommendedStrategy).toBe('drop_oldest_tools');
    expect(r.details).toEqual({
      model: 'gpt-4o-mini',
      modelLimit: 128000,
      effectiveTrigger: 0.9,
      preserveTurns: 5,
      maxAttempts: 2,
      targetUtilization: 0.7,
    });
  });

  // Python: BALANCED_POLICY.compute_context_budget([], model="gpt-4o-mini")
  it('empty history has zero utilization', () => {
    const r = BALANCED_POLICY.computeContextBudget([]);
    expect(r.route).toBe(CompactionRoute.FITS);
    expect(r.currentTokens).toBe(0);
    expect(r.availableTokens).toBe(111616);
    expect(r.utilization).toBe(0);
  });

  // Python: BALANCED_POLICY.compute_context_budget([user 'a'*410000], model="gpt-4o-mini")
  it('over trigger without tool outputs -> COMPACT_NEEDED', () => {
    const r = BALANCED_POLICY.computeContextBudget(big(410000), 'gpt-4o-mini');
    expect(r.route).toBe(CompactionRoute.COMPACT_NEEDED);
    expect(r.currentTokens).toBe(102507);
    expect(r.availableTokens).toBe(111616);
    expect(r.utilization).toBeCloseTo(0.9183898365825688, 12);
    expect(r.needsAction).toBe(true);
  });

  // Python: BALANCED_POLICY.compute_context_budget([user 'a'*410000, tool 'x'*2000], model="gpt-4o-mini")
  it('over trigger with a large tool output -> TRUNCATE_TOOLS', () => {
    const r = BALANCED_POLICY.computeContextBudget([...big(410000), TOOL_MSG], 'gpt-4o-mini');
    expect(r.route).toBe(CompactionRoute.TRUNCATE_TOOLS);
    expect(r.currentTokens).toBe(103021);
    expect(r.utilization).toBeCloseTo(0.9229949111238532, 12);
    expect(r.needsAction).toBe(true);
  });

  // Python: ContextCompactionPolicyAdapter(trigger_at=0.90, aggressive_tool_truncation=False)
  //         .compute_context_budget([user 'a'*410000, tool 'x'*2000], model="gpt-4o-mini")
  it('large tool output but aggressiveToolTruncation=false -> COMPACT_NEEDED', () => {
    const policy = new ContextCompactionPolicy({ triggerAt: 0.9, aggressiveToolTruncation: false });
    const r = policy.computeContextBudget([...big(410000), TOOL_MSG], 'gpt-4o-mini');
    expect(r.route).toBe(CompactionRoute.COMPACT_NEEDED);
    expect(r.currentTokens).toBe(103021);
  });

  // Python: BALANCED_POLICY.compute_context_budget([user 'a'*430000], model="gpt-4o-mini")
  it('at or above 95% -> COMPACT_THEN_TRUNCATE', () => {
    const r = BALANCED_POLICY.computeContextBudget(big(430000), 'gpt-4o-mini');
    expect(r.route).toBe(CompactionRoute.COMPACT_THEN_TRUNCATE);
    expect(r.currentTokens).toBe(107507);
    expect(r.utilization).toBeCloseTo(0.9631862815366973, 12);
  });

  // Python: BALANCED_POLICY.compute_context_budget(
  //   [user 'a'*8000, tool-call msg, named msg, multipart msg, tamil msg],
  //   model="gpt-4", tools=TOOLS, system_prompt="Be helpful. வணக்கம்")
  it('counts system prompt and tool schemas like Python', () => {
    const r = BALANCED_POLICY.computeContextBudget(
      [...big(8000), TOOL_CALL_MSG, NAMED_MSG, MULTI_MSG, TAMIL_MSG],
      'gpt-4',
      TOOLS,
      'Be helpful. வணக்கம்',
    );
    expect(r.route).toBe(CompactionRoute.FITS);
    expect(r.currentTokens).toBe(2258);
    expect(r.availableTokens).toBe(4096);
    expect(r.utilization).toBeCloseTo(0.55126953125, 12);
    expect(r.details.modelLimit).toBe(8192);
  });

  it('ignores an empty system prompt and an empty tools list (Python truthiness)', () => {
    const a = BALANCED_POLICY.computeContextBudget(big(8000), 'gpt-4');
    const b = BALANCED_POLICY.computeContextBudget(big(8000), 'gpt-4', [], '');
    expect(b.currentTokens).toBe(a.currentTokens);
  });

  // Python: ContextCompactionPolicyAdapter(trigger_at=0.85, model_overrides={
  //   "gpt-4": {"trigger_at": 0.92, "strategy": "summarise"}, "claude-3": {"trigger_at": 0.88}})
  //   .compute_context_budget([user 'a'*14000], model="gpt-4")
  it('applies model-specific overrides (Python: test_model_specific_overrides intent)', () => {
    const policy = new ContextCompactionPolicy({
      triggerAt: 0.85,
      strategy: CompactionStrategy.DROP_OLDEST_TOOLS,
      modelOverrides: {
        'gpt-4': { trigger_at: 0.92, strategy: 'summarise' },
        'claude-3': { triggerAt: 0.88 },
      },
    });
    const r = policy.computeContextBudget(big(14000), 'gpt-4');
    // 85.6% >= 85% default trigger, but < 92% gpt-4 override -> fits.
    expect(r.utilization).toBeCloseTo(0.856201171875, 12);
    expect(r.route).toBe(CompactionRoute.FITS);
    expect(r.needsAction).toBe(false);
    expect(r.details.effectiveTrigger).toBe(0.92);
    expect(r.recommendedStrategy).toBe('summarise');

    // No override for this model -> base trigger applies.
    const base = policy.computeContextBudget(big(14000), 'gpt-4-0613');
    expect(base.details.effectiveTrigger).toBe(0.85);
    expect(base.needsAction).toBe(true);
  });

  // Python: CONSERVATIVE_POLICY.compute_context_budget([user 'a'*390000], model="my-custom-model")
  it('unknown model falls back to the default limit and reserve', () => {
    const r = CONSERVATIVE_POLICY.computeContextBudget(big(390000), 'my-custom-model');
    expect(r.route).toBe(CompactionRoute.COMPACT_NEEDED);
    expect(r.currentTokens).toBe(97507);
    expect(r.availableTokens).toBe(120000);
    expect(r.utilization).toBeCloseTo(0.8125583333333334, 12);
    expect(r.details).toEqual({
      model: 'my-custom-model',
      modelLimit: 128000,
      effectiveTrigger: 0.8,
      preserveTurns: 8,
      maxAttempts: 2,
      targetUtilization: 0.6,
    });
  });

  // Python: AGGRESSIVE_POLICY.compute_context_budget([user 'a'*430000], model="gpt-4o-2024-05-13")
  it('partial model names resolve like Python', () => {
    const r = AGGRESSIVE_POLICY.computeContextBudget(big(430000), 'gpt-4o-2024-05-13');
    expect(r.route).toBe(CompactionRoute.COMPACT_THEN_TRUNCATE);
    expect(r.currentTokens).toBe(107507);
    expect(r.availableTokens).toBe(111616);
    expect(r.recommendedStrategy).toBe('summarise');
    expect(r.details).toEqual({
      model: 'gpt-4o-2024-05-13',
      modelLimit: 128000,
      effectiveTrigger: 0.95,
      preserveTurns: 3,
      maxAttempts: 2,
      targetUtilization: 0.75,
    });
  });
});

// ---------------------------------------------------------------------------
// computeContextBudget -- the mocked scenarios from the Python unit tests,
// reproduced by overriding the estimation hooks (Python patches the module
// functions instead).
// ---------------------------------------------------------------------------

class StubbedPolicy extends ContextCompactionPolicy {
  usable = 3600;
  modelLimit = 4000;
  messageTokens = 0;

  protected override resolveModelLimit(): number {
    return this.modelLimit;
  }
  protected override resolveUsableTokens(): number {
    return this.usable;
  }
  protected override estimateMessages(): number {
    return this.messageTokens;
  }
}

describe('computeContextBudget routing (Python: test_policy_routing_logic)', () => {
  const messages: ContextMessage[] = [
    { role: 'user', content: 'Hello' },
    { role: 'assistant', content: 'Hi there!' },
  ];

  const make = (): StubbedPolicy =>
    new StubbedPolicy({
      triggerAt: 0.85,
      strategy: CompactionStrategy.DROP_OLDEST_TOOLS,
      preserveLastNTurns: 3,
      targetUtilization: 0.65,
    });

  it('case 1: under threshold -> FITS', () => {
    const policy = make();
    policy.messageTokens = 2500; // 69% (under the 85% trigger)
    const r = policy.computeContextBudget(messages, 'gpt-4o-mini', null, null);
    expect(r.route).toBe(CompactionRoute.FITS);
    expect(r.needsAction).toBe(false);
    expect(r.utilization).toBe(2500 / 3600);
    expect(r.availableTokens).toBe(3600);
    expect(r.details.modelLimit).toBe(4000);
  });

  it('case 2: over threshold -> COMPACT_NEEDED with the configured strategy', () => {
    const policy = make();
    policy.messageTokens = 3200; // 89%
    const r = policy.computeContextBudget(messages, 'gpt-4o-mini');
    expect(r.route).toBe(CompactionRoute.COMPACT_NEEDED);
    expect(r.needsAction).toBe(true);
    expect(r.recommendedStrategy).toBe(CompactionStrategy.DROP_OLDEST_TOOLS);
  });

  it('case 3: critical usage -> COMPACT_THEN_TRUNCATE', () => {
    const policy = make();
    policy.messageTokens = 3450; // 96%
    const r = policy.computeContextBudget(messages, 'gpt-4o-mini');
    expect(r.route).toBe(CompactionRoute.COMPACT_THEN_TRUNCATE);
    expect(r.needsAction).toBe(true);
  });

  // Python: test_policy_with_large_tool_outputs
  it('large tool outputs are truncated before general compaction', () => {
    const policy = new StubbedPolicy({ triggerAt: 0.85, aggressiveToolTruncation: true });
    policy.messageTokens = 3200;
    const r = policy.computeContextBudget([{ role: 'user', content: 'Run tool' }, TOOL_MSG], 'gpt-4o-mini');
    expect(r.route).toBe(CompactionRoute.TRUNCATE_TOOLS);
    expect(r.needsAction).toBe(true);
  });

  it('a message with tool_call_id but no tool role also counts as a tool output', () => {
    const policy = new StubbedPolicy({ triggerAt: 0.85 });
    policy.messageTokens = 3200;
    const r = policy.computeContextBudget(
      [{ role: 'function', tool_call_id: 'c', content: 'y'.repeat(1001) }],
      'gpt-4o-mini',
    );
    expect(r.route).toBe(CompactionRoute.TRUNCATE_TOOLS);
    // Exactly 1000 chars is not "large" (Python: len(content) > 1000).
    const r2 = policy.computeContextBudget([{ role: 'tool', content: 'y'.repeat(1000) }], 'gpt-4o-mini');
    expect(r2.route).toBe(CompactionRoute.COMPACT_NEEDED);
  });

  it('utilization is 1.0 when no tokens are available', () => {
    const policy = new StubbedPolicy({});
    policy.usable = 0;
    policy.messageTokens = 10;
    const r = policy.computeContextBudget(messages);
    expect(r.utilization).toBe(1.0);
    expect(r.route).toBe(CompactionRoute.COMPACT_THEN_TRUNCATE);
  });

  it('a custom protocol implementation is accepted structurally', () => {
    const custom: ContextCompactionPolicyProtocol = {
      triggerAt: 0.5,
      strategy: 'truncate',
      preserveLastNTurns: 1,
      maxCompactionAttempts: 1,
      targetUtilization: 0.3,
      aggressiveToolTruncation: false,
      modelOverrides: null,
      computeContextBudget: () =>
        new ContextBudgetResult({
          route: CompactionRoute.FITS,
          currentTokens: 0,
          availableTokens: 1,
          utilization: 0,
          needsAction: false,
          recommendedStrategy: CompactionStrategy.TRUNCATE,
          details: {},
        }),
      toDict: () => ({}),
    };
    expect(isContextCompactionPolicy(custom)).toBe(true);
  });
});
