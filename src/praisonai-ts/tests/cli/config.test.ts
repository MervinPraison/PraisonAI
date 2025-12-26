/**
 * CLI Config Tests
 */

import { DEFAULT_CONFIG, validateConfig, mergeConfigs } from '../../src/cli/config/schema';
import { resolveConfig } from '../../src/cli/config/resolve';

describe('Config Schema', () => {
  describe('DEFAULT_CONFIG', () => {
    it('should have correct defaults', () => {
      expect(DEFAULT_CONFIG.model).toBe('openai/gpt-4o-mini');
      expect(DEFAULT_CONFIG.verbose).toBe(false);
      expect(DEFAULT_CONFIG.stream).toBe(false);
      expect(DEFAULT_CONFIG.profiles).toEqual({});
    });
  });

  describe('validateConfig', () => {
    it('should validate correct config', () => {
      const config = {
        model: 'gpt-4',
        verbose: true,
        stream: false
      };
      expect(validateConfig(config)).toBe(true);
    });

    it('should reject invalid model type', () => {
      const config = { model: 123 };
      expect(validateConfig(config)).toBe(false);
    });

    it('should reject invalid verbose type', () => {
      const config = { verbose: 'yes' };
      expect(validateConfig(config)).toBe(false);
    });

    it('should validate config with profiles', () => {
      const config = {
        model: 'gpt-4',
        profiles: {
          fast: { model: 'gpt-4o-mini' },
          quality: { model: 'gpt-4', verbose: true }
        }
      };
      expect(validateConfig(config)).toBe(true);
    });

    it('should reject invalid profile structure', () => {
      const config = {
        profiles: {
          bad: 'not an object'
        }
      };
      expect(validateConfig(config)).toBe(false);
    });
  });

  describe('mergeConfigs', () => {
    it('should merge multiple configs', () => {
      const result = mergeConfigs(
        { model: 'gpt-3.5' },
        { verbose: true },
        { model: 'gpt-4' }
      );
      expect(result.model).toBe('gpt-4');
      expect(result.verbose).toBe(true);
    });

    it('should preserve profiles from multiple sources', () => {
      const result = mergeConfigs(
        { profiles: { a: { model: 'gpt-3.5' } } },
        { profiles: { b: { model: 'gpt-4' } } }
      );
      expect(result.profiles?.a).toBeDefined();
      expect(result.profiles?.b).toBeDefined();
    });
  });
});

describe('Config Resolution', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it('should use defaults when no config provided', () => {
    const config = resolveConfig();
    expect(config.model).toBe('openai/gpt-4o-mini');
    expect(config.verbose).toBe(false);
    expect(config.stream).toBe(false);
  });

  it('should override with CLI options', () => {
    const config = resolveConfig({
      model: 'anthropic/claude-3',
      verbose: true
    });
    expect(config.model).toBe('anthropic/claude-3');
    expect(config.verbose).toBe(true);
  });

  it('should respect environment variables', () => {
    process.env.PRAISONAI_MODEL = 'env-model';
    process.env.PRAISONAI_VERBOSE = 'true';
    
    const config = resolveConfig();
    expect(config.model).toBe('env-model');
    expect(config.verbose).toBe(true);
  });

  it('should prioritize CLI options over env vars', () => {
    process.env.PRAISONAI_MODEL = 'env-model';
    
    const config = resolveConfig({ model: 'cli-model' });
    expect(config.model).toBe('cli-model');
  });
});
