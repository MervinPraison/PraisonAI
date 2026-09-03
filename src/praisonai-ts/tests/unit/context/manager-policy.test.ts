/**
 * Tests for ContextManager driven by a ContextCompactionPolicy, plus the
 * ContextConfig <- policy bridge in context/models.ts.
 */

import {
  AGGRESSIVE_POLICY,
  BALANCED_POLICY,
  CONSERVATIVE_POLICY,
  CompactionRoute,
  CompactionStrategy,
  ContextCompactionPolicy,
  ContextManager,
  OptimizerStrategy,
  applyCompactionPolicy,
  compactionStrategyToOptimizerStrategy,
  createContextConfig,
  createContextManager,
} from '../../../src/context';

/** Manager with a 1000-token usable budget (tokenRatio 1 => 1 char = 1 token). */
function makeManager(extra: ConstructorParameters<typeof ContextManager>[0] = {}): ContextManager {
  return new ContextManager({ maxTokens: 1000, reservedTokens: 0, tokenRatio: 1, ...extra });
}

const chars = (n: number): string => 'x'.repeat(n);

describe('ContextManager without a policy (existing behaviour)', () => {
  it('has no compaction threshold and never compacts below the hard limit', () => {
    const m = makeManager();
    expect(m.getPolicy()).toBeNull();
    expect(m.getCompactThreshold()).toBeNull();
    expect(m.evaluateBudget()).toBeNull();

    m.addSystem(chars(100));
    for (let i = 0; i < 8; i++) m.addUser(chars(100)); // 900 / 1000 = 90%
    expect(m.getUtilization()).toBeCloseTo(0.9);
    expect(m.shouldCompact()).toBe(false);
    expect(m.getAll()).toHaveLength(9);
    expect(m.compact()).toBe(0);
    expect(m.getAll()).toHaveLength(9);
  });

  it('still evicts by priority once the hard limit is exceeded', () => {
    const m = makeManager();
    m.addSystem(chars(100));
    for (let i = 0; i < 10; i++) m.addUser(chars(100)); // 1100 > 1000
    expect(m.getBudget().usedTokens).toBeLessThanOrEqual(1000);
    expect(m.getByRole('system')).toHaveLength(1);
  });
});

describe('ContextManager with a policy', () => {
  it('derives compactThreshold from policy.triggerAt', () => {
    expect(makeManager({ policy: CONSERVATIVE_POLICY }).getCompactThreshold()).toBe(0.8);
    expect(makeManager({ policy: BALANCED_POLICY }).getCompactThreshold()).toBe(0.9);
    expect(makeManager({ policy: AGGRESSIVE_POLICY }).getCompactThreshold()).toBe(0.95);
    expect(makeManager({ policy: BALANCED_POLICY }).getPolicy()).toBe(BALANCED_POLICY);
  });

  it('an explicit compactThreshold overrides the policy', () => {
    const m = makeManager({ policy: BALANCED_POLICY, compactThreshold: 0.5 });
    expect(m.getCompactThreshold()).toBe(0.5);
    expect(() => makeManager({ compactThreshold: 1.5 })).toThrow('compactThreshold must be in (0, 1]');
  });

  it('compacts when the policy says so and not otherwise (same items, different presets)', () => {
    // 1 system + 16 user items of 50 tokens = 850 / 1000 = 85%. Sixteen user
    // items so that CONSERVATIVE's preserveLastNTurns (8) still leaves
    // something removable.
    const fill = (m: ContextManager): void => {
      m.addSystem(chars(50));
      for (let i = 0; i < 16; i++) m.addUser(chars(50));
    };

    // CONSERVATIVE triggers at 80% -> compacts to its 60% target, keeping the
    // system item and the last 8 turns.
    // Compaction fires as the 15th user item reaches 800 (80%): the four
    // oldest user items go (800 -> 600), then the 16th item lands on top.
    const conservative = makeManager({ policy: CONSERVATIVE_POLICY });
    fill(conservative);
    expect(conservative.getAll()).toHaveLength(13);
    expect(conservative.getBudget().usedTokens).toBe(650);
    expect(conservative.getUtilization()).toBeLessThan(CONSERVATIVE_POLICY.triggerAt);
    expect(conservative.getByRole('system')).toHaveLength(1);
    expect(conservative.getByRole('user')).toHaveLength(12);

    // AGGRESSIVE triggers at 95% -> untouched.
    const aggressive = makeManager({ policy: AGGRESSIVE_POLICY });
    fill(aggressive);
    expect(aggressive.getAll()).toHaveLength(17);
    expect(aggressive.shouldCompact()).toBe(false);

    // No policy -> untouched (regression guard for the default path).
    const plain = makeManager();
    fill(plain);
    expect(plain.getAll()).toHaveLength(17);
  });

  it('compacts down to targetUtilization, keeping system items and the last N turns', () => {
    const policy = new ContextCompactionPolicy({
      triggerAt: 0.8,
      targetUtilization: 0.5,
      preserveLastNTurns: 2,
      strategy: CompactionStrategy.TRUNCATE,
    });
    const m = makeManager({ policy });
    const sys = m.addSystem(chars(100));
    const olds = [] as string[];
    for (let i = 0; i < 6; i++) olds.push(m.addUser(chars(100)).id); // 700 -> 70%, no compaction yet
    expect(m.getAll()).toHaveLength(7);

    const last1 = m.addAssistant(chars(100)); // 800 -> 80% -> compacts
    const ids = m.getAll().map(i => i.id);
    expect(m.getUtilization()).toBeLessThanOrEqual(0.5);
    expect(ids).toContain(sys.id); // system preserved
    expect(ids).toContain(last1.id); // most recent turn preserved
    expect(ids).toContain(olds[olds.length - 1]); // second most recent preserved
    // Oldest items were the ones dropped.
    expect(ids).not.toContain(olds[0]);
    expect(ids).not.toContain(olds[1]);
  });

  it('drop_oldest_tools removes tool outputs before other messages', () => {
    const policy = new ContextCompactionPolicy({
      triggerAt: 0.8,
      targetUtilization: 0.5,
      preserveLastNTurns: 0,
      strategy: CompactionStrategy.DROP_OLDEST_TOOLS,
    });
    const m = makeManager({ policy });
    const u1 = m.addUser(chars(100));
    const t1 = m.addTool(chars(200));
    const u2 = m.addUser(chars(100));
    const t2 = m.addTool(chars(200));
    const u3 = m.addUser(chars(100)); // 700 -> 70%
    expect(m.getAll()).toHaveLength(5);

    m.addAssistant(chars(100)); // 800 -> 80% -> compacts to <= 500
    const ids = m.getAll().map(i => i.id);
    expect(m.getUtilization()).toBeLessThanOrEqual(0.5);
    // Both tool outputs (400 tokens) go first; that alone reaches the target,
    // so every non-tool message survives.
    expect(ids).not.toContain(t1.id);
    expect(ids).not.toContain(t2.id);
    expect(ids).toEqual(expect.arrayContaining([u1.id, u2.id, u3.id]));
  });

  it('drop_oldest_tools falls through to oldest messages when tools are not enough', () => {
    const policy = new ContextCompactionPolicy({
      triggerAt: 0.8,
      targetUtilization: 0.3,
      preserveLastNTurns: 1,
      strategy: CompactionStrategy.DROP_OLDEST_TOOLS,
    });
    const m = makeManager({ policy });
    const u1 = m.addUser(chars(300));
    const t1 = m.addTool(chars(100));
    const u2 = m.addUser(chars(300));
    m.addAssistant(chars(100)); // 800 -> compacts to <= 300
    const ids = m.getAll().map(i => i.id);
    expect(m.getUtilization()).toBeLessThanOrEqual(0.3);
    expect(ids).not.toContain(t1.id);
    expect(ids).not.toContain(u1.id);
    expect(ids).not.toContain(u2.id);
    expect(m.getAll()).toHaveLength(1); // only the preserved last turn
  });

  it('compact() returns the number of tokens removed and 0 when nothing to do', () => {
    const m = makeManager({ policy: CONSERVATIVE_POLICY });
    m.addUser(chars(50));
    expect(m.compact()).toBe(0);
    for (let i = 0; i < 15; i++) m.addUser(chars(50)); // 800 -> 80% -> compacts on add
    expect(m.getUtilization()).toBeLessThanOrEqual(0.6);
    expect(m.compact()).toBe(0); // already under target

    // Manual compaction reports the tokens it removed.
    const manual = makeManager({ policy: CONSERVATIVE_POLICY, compactThreshold: 1.0 });
    for (let i = 0; i < 16; i++) manual.addUser(chars(50)); // 800, threshold 1.0 -> no auto-compaction
    expect(manual.getAll()).toHaveLength(16);
    const removed = manual.compact();
    expect(removed).toBeGreaterThan(0);
    expect(manual.getBudget().usedTokens).toBe(800 - removed);
    expect(manual.getUtilization()).toBeLessThanOrEqual(0.6);
  });

  it('evaluateBudget delegates to the policy with the current messages', () => {
    const m = makeManager({ policy: BALANCED_POLICY });
    m.addUser('Hello');
    m.addAssistant('Hi there!');
    const r = m.evaluateBudget('gpt-4o-mini')!;
    expect(r).not.toBeNull();
    // Same numbers as policy.test.ts "small conversation fits".
    expect(r.route).toBe(CompactionRoute.FITS);
    expect(r.currentTokens).toBe(14);
    expect(r.availableTokens).toBe(111616);
  });

  it('createContextManager passes the policy through', () => {
    const m = createContextManager({ policy: AGGRESSIVE_POLICY });
    expect(m.getCompactThreshold()).toBe(0.95);
  });
});

describe('applyCompactionPolicy (ContextConfig bridge)', () => {
  it('maps CompactionStrategy onto OptimizerStrategy', () => {
    expect(compactionStrategyToOptimizerStrategy(CompactionStrategy.TRUNCATE)).toBe(OptimizerStrategy.TRUNCATE);
    expect(compactionStrategyToOptimizerStrategy(CompactionStrategy.SUMMARISE)).toBe(OptimizerStrategy.SUMMARIZE);
    expect(compactionStrategyToOptimizerStrategy(CompactionStrategy.DROP_OLDEST_TOOLS)).toBe(
      OptimizerStrategy.PRUNE_TOOLS,
    );
    expect(compactionStrategyToOptimizerStrategy(CompactionStrategy.SLIDING_WINDOW)).toBe(
      OptimizerStrategy.SLIDING_WINDOW,
    );
    expect(compactionStrategyToOptimizerStrategy('SUMMARISE')).toBe(OptimizerStrategy.SUMMARIZE);
    expect(compactionStrategyToOptimizerStrategy('unknown')).toBe(OptimizerStrategy.SMART);
  });

  it('drives compactThreshold and friends from the policy without mutating the input', () => {
    const base = createContextConfig({ autoCompact: false, compactThreshold: 0.8, keepRecentTurns: 5 });
    const derived = applyCompactionPolicy(base, AGGRESSIVE_POLICY);

    expect(derived.autoCompact).toBe(true);
    expect(derived.compactThreshold).toBe(0.95);
    expect(derived.keepRecentTurns).toBe(3);
    expect(derived.compressionMaxAttempts).toBe(2);
    expect(derived.strategy).toBe(OptimizerStrategy.SUMMARIZE);
    // Unrelated fields carried over.
    expect(derived.outputReserve).toBe(base.outputReserve);
    expect(derived.toolOutputMax).toBe(base.toolOutputMax);

    // Input untouched.
    expect(base.autoCompact).toBe(false);
    expect(base.compactThreshold).toBe(0.8);
    expect(base.keepRecentTurns).toBe(5);
  });

  it('default ContextConfig is unchanged when no policy is applied', () => {
    const cfg = createContextConfig();
    expect(cfg.compactThreshold).toBe(0.8);
    expect(cfg.keepRecentTurns).toBe(5);
    expect(cfg.strategy).toBe(OptimizerStrategy.SMART);
  });
});
