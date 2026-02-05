/**
 * Tests for Config Module (Python parity)
 */

import {
  // Enums
  MemoryBackend,
  ChunkingStrategy,
  GuardrailAction,
  WebSearchProvider,
  OutputPreset,
  ExecutionPreset,
  ArrayMode,
  // Presets
  MEMORY_PRESETS,
  MEMORY_URL_SCHEMES,
  OUTPUT_PRESETS,
  EXECUTION_PRESETS,
  WEB_PRESETS,
  PLANNING_PRESETS,
  REFLECTION_PRESETS,
  GUARDRAIL_PRESETS,
  CONTEXT_PRESETS,
  AUTONOMY_PRESETS,
  CACHING_PRESETS,
  MULTI_AGENT_OUTPUT_PRESETS,
  MULTI_AGENT_EXECUTION_PRESETS,
  KNOWLEDGE_PRESETS,
  // Resolver functions
  resolve_memory,
  resolve_output,
  resolve_execution,
  resolve_web,
  resolve_planning,
  resolve_reflection,
  resolve_knowledge,
  resolve_context,
  resolve_autonomy,
  resolve_caching,
  resolve_guardrails,
  // Parse utilities
  detect_url_scheme,
  is_path_like,
  suggest_similar,
  clean_triple_backticks,
  is_policy_string,
  parse_policy_string,
  validate_config,
  apply_config_defaults,
  get_config,
  get_default,
  // Errors
  ConfigValidationError,
} from '../../../src/config';

describe('Config Enums (Python Parity)', () => {
  describe('MemoryBackend', () => {
    it('should have all backend values', () => {
      expect(MemoryBackend.FILE).toBe('file');
      expect(MemoryBackend.SQLITE).toBe('sqlite');
      expect(MemoryBackend.REDIS).toBe('redis');
      expect(MemoryBackend.POSTGRES).toBe('postgres');
      expect(MemoryBackend.MEM0).toBe('mem0');
      expect(MemoryBackend.MONGODB).toBe('mongodb');
    });
  });

  describe('GuardrailAction', () => {
    it('should have all action values', () => {
      expect(GuardrailAction.RAISE).toBe('raise');
      expect(GuardrailAction.SKIP).toBe('skip');
      expect(GuardrailAction.RETRY).toBe('retry');
      expect(GuardrailAction.WARN).toBe('warn');
    });
  });

  describe('OutputPreset', () => {
    it('should have all preset values', () => {
      expect(OutputPreset.SILENT).toBe('silent');
      expect(OutputPreset.VERBOSE).toBe('verbose');
      expect(OutputPreset.DEBUG).toBe('debug');
      expect(OutputPreset.STREAM).toBe('stream');
    });
  });
});

describe('Config Presets (Python Parity)', () => {
  describe('MEMORY_PRESETS', () => {
    it('should have file preset', () => {
      expect(MEMORY_PRESETS.file).toEqual({ backend: MemoryBackend.FILE });
    });

    it('should have learn preset', () => {
      expect(MEMORY_PRESETS.learn).toEqual({ backend: MemoryBackend.FILE, learn: true });
    });

    it('should have history preset', () => {
      expect(MEMORY_PRESETS.history.history).toBe(true);
      expect(MEMORY_PRESETS.history.historyLimit).toBe(10);
    });
  });

  describe('OUTPUT_PRESETS', () => {
    it('should have silent preset', () => {
      expect(OUTPUT_PRESETS.silent.verbose).toBe(false);
      expect(OUTPUT_PRESETS.silent.stream).toBe(false);
    });

    it('should have verbose preset', () => {
      expect(OUTPUT_PRESETS.verbose.verbose).toBe(true);
      expect(OUTPUT_PRESETS.verbose.markdown).toBe(true);
    });

    it('should have debug preset', () => {
      expect(OUTPUT_PRESETS.debug.metrics).toBe(true);
      expect(OUTPUT_PRESETS.debug.reasoningSteps).toBe(true);
    });
  });

  describe('EXECUTION_PRESETS', () => {
    it('should have fast preset', () => {
      expect(EXECUTION_PRESETS.fast.maxIter).toBe(10);
      expect(EXECUTION_PRESETS.fast.maxRetryLimit).toBe(1);
    });

    it('should have thorough preset', () => {
      expect(EXECUTION_PRESETS.thorough.maxIter).toBe(50);
      expect(EXECUTION_PRESETS.thorough.maxRetryLimit).toBe(5);
    });
  });

  describe('GUARDRAIL_PRESETS', () => {
    it('should have strict preset', () => {
      expect(GUARDRAIL_PRESETS.strict.maxRetries).toBe(5);
      expect(GUARDRAIL_PRESETS.strict.onFail).toBe(GuardrailAction.RAISE);
    });
  });
});

describe('Resolver Functions (Python Parity)', () => {
  describe('resolve_memory', () => {
    it('should return undefined for false', () => {
      expect(resolve_memory(false)).toBeUndefined();
    });

    it('should return file backend for true', () => {
      expect(resolve_memory(true)).toEqual({ backend: MemoryBackend.FILE });
    });

    it('should resolve preset string', () => {
      expect(resolve_memory('redis')).toEqual({ backend: MemoryBackend.REDIS });
    });

    it('should pass through config object', () => {
      const config = { backend: MemoryBackend.SQLITE, userId: 'test' };
      expect(resolve_memory(config)).toEqual(config);
    });
  });

  describe('resolve_output', () => {
    it('should return silent for false', () => {
      expect(resolve_output(false)).toEqual(OUTPUT_PRESETS.silent);
    });

    it('should return verbose for true', () => {
      expect(resolve_output(true)).toEqual(OUTPUT_PRESETS.verbose);
    });

    it('should resolve preset string', () => {
      expect(resolve_output('debug')).toEqual(OUTPUT_PRESETS.debug);
    });
  });

  describe('resolve_execution', () => {
    it('should return undefined for false', () => {
      expect(resolve_execution(false)).toBeUndefined();
    });

    it('should return balanced for true', () => {
      expect(resolve_execution(true)).toEqual(EXECUTION_PRESETS.balanced);
    });

    it('should resolve preset string', () => {
      expect(resolve_execution('fast')).toEqual(EXECUTION_PRESETS.fast);
    });
  });

  describe('resolve_planning', () => {
    it('should return undefined for false', () => {
      expect(resolve_planning(false)).toBeUndefined();
    });

    it('should return reasoning config for true', () => {
      const result = resolve_planning(true);
      expect(result?.reasoning).toBe(true);
    });

    it('should resolve preset string', () => {
      expect(resolve_planning('auto')).toEqual(PLANNING_PRESETS.auto);
    });
  });

  describe('resolve_guardrails', () => {
    it('should return safety preset for true', () => {
      expect(resolve_guardrails(true)).toEqual(GUARDRAIL_PRESETS.safety);
    });

    it('should resolve preset string', () => {
      expect(resolve_guardrails('strict')).toEqual(GUARDRAIL_PRESETS.strict);
    });
  });

  describe('resolve_knowledge', () => {
    it('should handle array of sources', () => {
      const result = resolve_knowledge(['docs/', 'data/']);
      expect(result?.sources).toEqual(['docs/', 'data/']);
    });

    it('should handle single string', () => {
      const result = resolve_knowledge('docs/');
      expect(result?.sources).toEqual(['docs/']);
    });
  });
});

describe('Parse Utilities (Python Parity)', () => {
  describe('detect_url_scheme', () => {
    it('should detect postgres scheme', () => {
      expect(detect_url_scheme('postgresql://localhost:5432/db')).toBe('postgres');
    });

    it('should detect redis scheme', () => {
      expect(detect_url_scheme('redis://localhost:6379')).toBe('redis');
    });

    it('should detect mongodb scheme', () => {
      expect(detect_url_scheme('mongodb://localhost:27017')).toBe('mongodb');
    });

    it('should return undefined for no scheme', () => {
      expect(detect_url_scheme('localhost:5432')).toBeUndefined();
    });
  });

  describe('is_path_like', () => {
    it('should detect absolute paths', () => {
      expect(is_path_like('/Users/test/file.txt')).toBe(true);
    });

    it('should detect relative paths', () => {
      expect(is_path_like('./config.json')).toBe(true);
      expect(is_path_like('../data/')).toBe(true);
    });

    it('should detect home paths', () => {
      expect(is_path_like('~/Documents')).toBe(true);
    });

    it('should detect Windows paths', () => {
      expect(is_path_like('C:\\Users\\test')).toBe(true);
    });
  });

  describe('suggest_similar', () => {
    it('should suggest similar options', () => {
      const options = ['verbose', 'silent', 'debug', 'stream'];
      expect(suggest_similar('verbos', options)).toContain('verbose');
    });

    it('should suggest prefix matches', () => {
      const options = ['verbose', 'silent', 'debug'];
      expect(suggest_similar('verb', options)).toContain('verbose');
    });
  });

  describe('clean_triple_backticks', () => {
    it('should remove code block markers', () => {
      const input = '```python\nprint("hello")\n```';
      expect(clean_triple_backticks(input)).toBe('print("hello")');
    });
  });

  describe('is_policy_string', () => {
    it('should detect policy strings', () => {
      expect(is_policy_string('allow:read')).toBe(true);
      expect(is_policy_string('deny:write')).toBe(true);
      expect(is_policy_string('max:100')).toBe(true);
    });

    it('should reject non-policy strings', () => {
      expect(is_policy_string('hello world')).toBe(false);
    });
  });

  describe('parse_policy_string', () => {
    it('should parse policy string', () => {
      const result = parse_policy_string('allow:read');
      expect(result?.action).toBe('allow');
      expect(result?.value).toBe('read');
    });
  });

  describe('validate_config', () => {
    it('should validate required fields', () => {
      const schema = { name: { type: 'string', required: true } };
      const result = validate_config({}, schema);
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Missing required field: name');
    });

    it('should validate types', () => {
      const schema = { count: { type: 'number' } };
      const result = validate_config({ count: 'not a number' }, schema);
      expect(result.valid).toBe(false);
    });

    it('should pass valid config', () => {
      const schema = { name: { type: 'string', required: true } };
      const result = validate_config({ name: 'test' }, schema);
      expect(result.valid).toBe(true);
    });
  });

  describe('apply_config_defaults', () => {
    it('should apply defaults', () => {
      const defaults = { a: 1, b: 2, c: 3 };
      const config = { b: 20 };
      const result = apply_config_defaults(config, defaults);
      expect(result).toEqual({ a: 1, b: 20, c: 3 });
    });
  });

  describe('get_default', () => {
    it('should return default values', () => {
      expect(get_default('llm')).toBe('gpt-4o-mini');
      expect(get_default('temperature')).toBe(0.7);
    });
  });
});

describe('ConfigValidationError', () => {
  it('should create error with message', () => {
    const error = new ConfigValidationError('Invalid config');
    expect(error.message).toBe('Invalid config');
    expect(error.name).toBe('ConfigValidationError');
  });

  it('should include field and value', () => {
    const error = new ConfigValidationError('Invalid field', 'name', 123);
    expect(error.field).toBe('name');
    expect(error.value).toBe(123);
  });
});
