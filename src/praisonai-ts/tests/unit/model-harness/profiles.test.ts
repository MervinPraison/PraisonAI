import {
  HarnessProfile,
  DEFAULT_PROFILE,
  registerProfile,
  resolveHarness,
  listHarnessProfiles,
  resetHarnessRegistry,
} from '../../../src/model-harness';
import type { HarnessResolverProtocol } from '../../../src/model-harness';

describe('HarnessProfile', () => {
  it('uses the Python defaults', () => {
    const profile = new HarnessProfile();
    expect(profile.name).toBe('default');
    expect(profile.basePrompt).toBeNull();
    expect(profile.preferredEditFormat).toBeNull();
  });

  it('is frozen like the Python frozen dataclass', () => {
    const profile = new HarnessProfile({ name: 'x' });
    expect(Object.isFrozen(profile)).toBe(true);
    expect(() => {
      (profile as { name: string }).name = 'y';
    }).toThrow();
  });
});

describe('resolveHarness', () => {
  beforeEach(() => resetHarnessRegistry());

  it('resolves Anthropic models by substring, case-insensitively', () => {
    const profile = resolveHarness('Claude-Opus-4');
    expect(profile.name).toBe('anthropic');
    expect(profile.preferredEditFormat).toBe('apply_patch');
    expect(profile.basePrompt).toContain('apply_patch');
    expect(resolveHarness('ANTHROPIC/whatever').name).toBe('anthropic');
  });

  it('resolves OpenAI models including o-series', () => {
    expect(resolveHarness('gpt-4o').name).toBe('openai');
    expect(resolveHarness('o3-mini').preferredEditFormat).toBe('edit_file');
    expect(resolveHarness('openai/gpt-4.1').name).toBe('openai');
  });

  it('falls back to DEFAULT_PROFILE (same object) for unknown and falsy models', () => {
    expect(resolveHarness('llama-3-70b')).toBe(DEFAULT_PROFILE);
    expect(resolveHarness(null)).toBe(DEFAULT_PROFILE);
    expect(resolveHarness(undefined)).toBe(DEFAULT_PROFILE);
    expect(resolveHarness('')).toBe(DEFAULT_PROFILE);
    expect(DEFAULT_PROFILE.basePrompt).toBeNull();
    expect(DEFAULT_PROFILE.preferredEditFormat).toBeNull();
  });

  it('first match wins in registry order', () => {
    // "gpt" appears after "claude" in the id; the anthropic entry is earlier so it wins.
    expect(resolveHarness('claude-gpt-hybrid').name).toBe('anthropic');
  });
});

describe('registerProfile', () => {
  beforeEach(() => resetHarnessRegistry());

  it('prepends so a new registration overrides the built-in defaults', () => {
    const custom = new HarnessProfile({ name: 'my-claude', preferredEditFormat: 'edit_file' });
    registerProfile(['CLAUDE'], custom);
    expect(resolveHarness('claude-3')).toBe(custom);
    expect(listHarnessProfiles()[0]).toEqual([['claude'], custom]);
  });

  it('drops empty matchers, so an entry with none never matches', () => {
    const custom = new HarnessProfile({ name: 'never' });
    registerProfile(['', ''], custom);
    expect(listHarnessProfiles()[0][0]).toEqual([]);
    expect(resolveHarness('anything')).toBe(DEFAULT_PROFILE);
    expect(resolveHarness('claude').name).toBe('anthropic');
  });

  it('resetHarnessRegistry restores the built-ins', () => {
    registerProfile(['llama'], new HarnessProfile({ name: 'llama' }));
    expect(resolveHarness('llama').name).toBe('llama');
    resetHarnessRegistry();
    expect(resolveHarness('llama')).toBe(DEFAULT_PROFILE);
    expect(listHarnessProfiles()).toHaveLength(2);
  });

  it('a custom resolver can satisfy HarnessResolverProtocol', () => {
    const resolver: HarnessResolverProtocol = { resolveHarness: (m) => resolveHarness(m) };
    expect(resolver.resolveHarness('gpt-4').name).toBe('openai');
  });
});
