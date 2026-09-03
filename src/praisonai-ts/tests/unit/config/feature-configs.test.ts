/**
 * Tests for the dataclass-style feature configs and learn enums
 * (Python parity with praisonaiagents/config/feature_configs.py and tools/tool_search.py).
 */

import {
  LearnScope,
  LearnMode,
  LearnBackend,
  RulesConfig,
  PreCompactionMemoryFlushConfig,
  ToolSearchConfig,
  ConfigValidationError,
} from '../../../src/config';

describe('Learn enums (Python parity)', () => {
  it('LearnScope values', () => {
    expect(LearnScope.PRIVATE).toBe('private');
    expect(LearnScope.SHARED).toBe('shared');
    expect(Object.values(LearnScope)).toEqual(['private', 'shared']);
  });

  it('LearnMode values', () => {
    expect(LearnMode.DISABLED).toBe('disabled');
    expect(LearnMode.AGENTIC).toBe('agentic');
    expect(LearnMode.PROPOSE).toBe('propose');
    expect(Object.values(LearnMode)).toEqual(['disabled', 'agentic', 'propose']);
  });

  it('LearnBackend values', () => {
    expect(LearnBackend.FILE).toBe('file');
    expect(LearnBackend.SQLITE).toBe('sqlite');
    expect(LearnBackend.REDIS).toBe('redis');
    expect(LearnBackend.MONGODB).toBe('mongodb');
    expect(Object.values(LearnBackend)).toEqual(['file', 'sqlite', 'redis', 'mongodb']);
  });
});

describe('RulesConfig', () => {
  it('defaults every field to None', () => {
    const c = new RulesConfig();
    expect(c.charBudget).toBeUndefined();
    expect(c.files).toBeUndefined();
    expect(c.workspacePath).toBeUndefined();
    expect(c.toDict()).toEqual({ char_budget: null, files: [], workspace_path: null });
  });

  it('stores fields and serialises like Python to_dict', () => {
    const c = new RulesConfig({ charBudget: 6000, files: ['docs/CONVENTIONS.md'], workspacePath: '/repo' });
    expect(c.charBudget).toBe(6000);
    expect(c.files).toEqual(['docs/CONVENTIONS.md']);
    expect(c.workspacePath).toBe('/repo');
    const d = c.toDict();
    expect(d).toEqual({ char_budget: 6000, files: ['docs/CONVENTIONS.md'], workspace_path: '/repo' });
    // to_dict returns list(self.files) -> a copy
    d.files.push('x');
    expect(c.files).toEqual(['docs/CONVENTIONS.md']);
  });
});

describe('PreCompactionMemoryFlushConfig', () => {
  it('defaults mirror Python (enabled, 20s, 2 turns, 8000 tokens, no llm)', () => {
    const c = new PreCompactionMemoryFlushConfig();
    expect(c.enabled).toBe(true);
    expect(c.timeoutSeconds).toBe(20);
    expect(c.minTurnsToFlush).toBe(2);
    expect(c.maxFlushTokens).toBe(8000);
    expect(c.llm).toBeUndefined();
    expect(c.toDict()).toEqual({
      enabled: true, timeout_seconds: 20, min_turns_to_flush: 2, max_flush_tokens: 8000, llm: null,
    });
  });

  it('accepts valid overrides and coerces timeout to a number', () => {
    const c = new PreCompactionMemoryFlushConfig({
      enabled: false, timeoutSeconds: '5.5' as any, minTurnsToFlush: 1, maxFlushTokens: 1, llm: 'gpt-4o-mini',
    });
    expect(c.enabled).toBe(false);
    expect(c.timeoutSeconds).toBe(5.5);
    expect(c.minTurnsToFlush).toBe(1);
    expect(c.maxFlushTokens).toBe(1);
    expect(c.llm).toBe('gpt-4o-mini');
  });

  // Same inputs Python's __post_init__ rejects with ValueError.
  it.each([
    ['timeoutSeconds = 0', { timeoutSeconds: 0 }, 'timeoutSeconds must be finite and positive'],
    ['timeoutSeconds < 0', { timeoutSeconds: -1 }, 'timeoutSeconds must be finite and positive'],
    ['timeoutSeconds = Infinity', { timeoutSeconds: Infinity }, 'timeoutSeconds must be finite and positive'],
    ['timeoutSeconds = NaN', { timeoutSeconds: NaN }, 'timeoutSeconds must be finite and positive'],
    ['timeoutSeconds = "abc"', { timeoutSeconds: 'abc' as any }, 'timeoutSeconds must be finite and positive'],
    ['timeoutSeconds = null', { timeoutSeconds: null as any }, 'timeoutSeconds must be finite and positive'],
    ['minTurnsToFlush = 0', { minTurnsToFlush: 0 }, 'minTurnsToFlush must be >= 1'],
    ['minTurnsToFlush < 0', { minTurnsToFlush: -3 }, 'minTurnsToFlush must be >= 1'],
    ['maxFlushTokens = 0', { maxFlushTokens: 0 }, 'maxFlushTokens must be >= 1'],
    ['maxFlushTokens < 0', { maxFlushTokens: -100 }, 'maxFlushTokens must be >= 1'],
  ])('rejects %s', (_label, options, message) => {
    expect(() => new PreCompactionMemoryFlushConfig(options)).toThrow(ConfigValidationError);
    expect(() => new PreCompactionMemoryFlushConfig(options)).toThrow(message);
  });

  it('reports the offending field on the error', () => {
    try {
      new PreCompactionMemoryFlushConfig({ maxFlushTokens: 0 });
      throw new Error('expected to throw');
    } catch (e) {
      expect(e).toBeInstanceOf(ConfigValidationError);
      expect((e as ConfigValidationError).field).toBe('maxFlushTokens');
      expect((e as ConfigValidationError).value).toBe(0);
    }
  });
});

describe('ToolSearchConfig', () => {
  it('defaults mirror Python', () => {
    const c = new ToolSearchConfig();
    expect(c.enabled).toBe('auto');
    expect(c.thresholdPct).toBe(10);
    expect(c.searchDefaultLimit).toBe(5);
    expect(c.maxSearchLimit).toBe(20);
    expect(c.coreTools).toBeUndefined();
  });

  it('stores overrides; coreTools becomes a Set', () => {
    const c = new ToolSearchConfig({ enabled: 'on', thresholdPct: 25, searchDefaultLimit: 3, maxSearchLimit: 10, coreTools: ['a', 'b', 'a'] });
    expect(c.enabled).toBe('on');
    expect(c.thresholdPct).toBe(25);
    expect(c.searchDefaultLimit).toBe(3);
    expect(c.maxSearchLimit).toBe(10);
    expect(c.coreTools).toBeInstanceOf(Set);
    expect([...c.coreTools!]).toEqual(['a', 'b']);
  });

  describe('fromRaw', () => {
    it('returns an existing instance unchanged', () => {
      const c = new ToolSearchConfig({ enabled: 'off' });
      expect(ToolSearchConfig.fromRaw(c)).toBe(c);
    });

    it('booleans -> on/off', () => {
      expect(ToolSearchConfig.fromRaw(true).enabled).toBe('on');
      expect(ToolSearchConfig.fromRaw(false).enabled).toBe('off');
    });

    it.each([
      ['true', 'on'], ['on', 'on'], ['yes', 'on'], ['1', 'on'], ['TRUE', 'on'], ['On', 'on'],
      ['false', 'off'], ['off', 'off'], ['no', 'off'], ['0', 'off'], ['FALSE', 'off'],
      ['auto', 'auto'], ['AUTO', 'auto'],
    ])('string %s -> %s', (raw, enabled) => {
      expect(ToolSearchConfig.fromRaw(raw).enabled).toBe(enabled);
    });

    it('rejects unknown strings like Python ValueError', () => {
      expect(() => ToolSearchConfig.fromRaw('maybe')).toThrow(ConfigValidationError);
      expect(() => ToolSearchConfig.fromRaw('maybe')).toThrow('Invalid tool_search string value: maybe');
    });

    it('accepts plain objects with snake_case (Python dict) or camelCase keys', () => {
      const snake = ToolSearchConfig.fromRaw({ enabled: 'on', threshold_pct: 15, search_default_limit: 2, max_search_limit: 8, core_tools: ['x'] });
      expect(snake.enabled).toBe('on');
      expect(snake.thresholdPct).toBe(15);
      expect(snake.searchDefaultLimit).toBe(2);
      expect(snake.maxSearchLimit).toBe(8);
      expect([...snake.coreTools!]).toEqual(['x']);
      const camel = ToolSearchConfig.fromRaw({ thresholdPct: 15, maxSearchLimit: 8 });
      expect(camel.thresholdPct).toBe(15);
      expect(camel.maxSearchLimit).toBe(8);
      expect(camel.enabled).toBe('auto');
    });

    it('rejects unknown dict keys (Python: cls(**raw) TypeError)', () => {
      expect(() => ToolSearchConfig.fromRaw({ bogus: 1 })).toThrow('Unknown tool_search option: bogus');
    });

    it.each([[null], [undefined], [42], [['on']]])('rejects unsupported type %p', (raw) => {
      expect(() => ToolSearchConfig.fromRaw(raw)).toThrow(ConfigValidationError);
      expect(() => ToolSearchConfig.fromRaw(raw)).toThrow('Invalid tool_search type');
    });
  });
});
