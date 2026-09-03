/**
 * Tests for the structured error hierarchy (Python parity with praisonaiagents/errors.py).
 */

import {
  AGENT_ERROR_KINDS,
  LEGACY_ERROR_CATEGORY_MAP,
  isAgentErrorKind,
  resolveErrorCategory,
  FailoverDecision,
  IdleTimeoutBreaker,
  isErrorContext,
  PraisonAIError,
  ToolExecutionError,
  LLMError,
  ValidationError,
  NetworkError,
  PraisonAIConfigError,
} from '../../../src/errors';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

describe('AgentErrorKind taxonomy', () => {
  it('matches the Python closed taxonomy exactly', () => {
    expect([...AGENT_ERROR_KINDS]).toEqual([
      'auth', 'auth_permanent', 'rate_limit', 'overloaded',
      'context_overflow', 'idle_timeout', 'billing',
      'model_not_found', 'empty_response', 'format_error', 'unknown',
    ]);
  });

  it('maps legacy categories like Python', () => {
    expect(LEGACY_ERROR_CATEGORY_MAP).toEqual({
      tool: 'unknown', llm: 'unknown', budget: 'billing',
      validation: 'format_error', network: 'unknown', handoff: 'unknown',
    });
  });

  it('isAgentErrorKind accepts only taxonomy members', () => {
    expect(isAgentErrorKind('rate_limit')).toBe(true);
    expect(isAgentErrorKind('tool')).toBe(false);
    expect(isAgentErrorKind(42)).toBe(false);
  });

  it('resolveErrorCategory: null -> unknown, legacy -> mapped with warning, garbage throws', () => {
    expect(resolveErrorCategory(undefined)).toBe('unknown');
    expect(resolveErrorCategory(null)).toBe('unknown');
    expect(resolveErrorCategory('billing')).toBe('billing');

    const spy = jest.spyOn(process, 'emitWarning').mockImplementation(() => undefined);
    try {
      expect(resolveErrorCategory('budget')).toBe('billing');
      expect(spy).toHaveBeenCalledWith(expect.stringContaining("error_category='budget' is deprecated"), 'DeprecationWarning');
    } finally {
      spy.mockRestore();
    }

    expect(() => resolveErrorCategory('bogus')).toThrow("Unsupported error_category: 'bogus'");
  });
});

describe('FailoverDecision / IdleTimeoutBreaker', () => {
  it('FailoverDecision defaults mirror Python (backoff_ms=0, is_retryable=True)', () => {
    const d = new FailoverDecision('retry', 'rate_limit');
    expect(d.action).toBe('retry');
    expect(d.reason).toBe('rate_limit');
    expect(d.backoffMs).toBe(0);
    expect(d.isRetryable).toBe(true);
    const e = new FailoverDecision('surface_error', 'auth_permanent', { backoffMs: 500, isRetryable: false });
    expect(e.backoffMs).toBe(500);
    expect(e.isRetryable).toBe(false);
  });

  it('IdleTimeoutBreaker trips at max_consecutive (default 3) and resets', () => {
    const b = new IdleTimeoutBreaker();
    expect(b.maxConsecutive).toBe(3);
    expect(b.recordIdleTimeout()).toBe(false);
    expect(b.recordIdleTimeout()).toBe(false);
    expect(b.recordIdleTimeout()).toBe(true);
    b.reset();
    expect(b.recordIdleTimeout()).toBe(false);
    const one = new IdleTimeoutBreaker(1);
    expect(one.recordIdleTimeout()).toBe(true);
  });
});

describe('PraisonAIError (base)', () => {
  it('applies Python defaults', () => {
    const err = new PraisonAIError('boom');
    expect(err).toBeInstanceOf(Error);
    expect(err).toBeInstanceOf(PraisonAIError);
    expect(err.name).toBe('PraisonAIError');
    expect(err.message).toBe('boom');
    expect(err.agentId).toBe('unknown');
    expect(err.runId).toMatch(UUID_RE);
    expect(err.errorCategory).toBe('unknown');
    expect(err.isRetryable).toBe(false);
    expect(err.context).toEqual({});
    expect(err.stack).toBeDefined();
  });

  it('honours explicit options', () => {
    const err = new PraisonAIError('boom', {
      agentId: 'a1', runId: 'r1', errorCategory: 'rate_limit', isRetryable: true, context: { k: 'v' },
    });
    expect(err.agentId).toBe('a1');
    expect(err.runId).toBe('r1');
    expect(err.errorCategory).toBe('rate_limit');
    expect(err.isRetryable).toBe(true);
    expect(err.context).toEqual({ k: 'v' });
  });

  it('maps legacy error categories and rejects unknown ones', () => {
    const spy = jest.spyOn(process, 'emitWarning').mockImplementation(() => undefined);
    try {
      expect(new PraisonAIError('x', { errorCategory: 'validation' }).errorCategory).toBe('format_error');
    } finally {
      spy.mockRestore();
    }
    expect(() => new PraisonAIError('x', { errorCategory: 'nope' })).toThrow('Unsupported error_category');
  });

  it('toString matches Python __str__ while message stays raw', () => {
    const err = new PraisonAIError('boom', { agentId: 'a1', runId: 'r1', errorCategory: 'auth' });
    expect(String(err)).toBe('[auth] boom (agent: a1, run: r1)');
    expect(err.message).toBe('boom');
  });

  it('toDict serialises the structured context with snake_case keys', () => {
    const err = new PraisonAIError('boom', { agentId: 'a1', runId: 'r1', context: { k: 1 } });
    expect(err.toDict()).toEqual({
      name: 'PraisonAIError', message: 'boom', agent_id: 'a1', run_id: 'r1',
      error_category: 'unknown', is_retryable: false, context: { k: 1 },
    });
    // the dict is a copy, not the live context
    err.toDict().context.k = 2;
    expect(err.context.k).toBe(1);
  });

  it('satisfies ErrorContextProtocol structurally', () => {
    expect(isErrorContext(new PraisonAIError('x'))).toBe(true);
    expect(isErrorContext({ agentId: 'a', runId: 'r', isRetryable: false, errorCategory: 'unknown' })).toBe(true);
    expect(isErrorContext({ agentId: 'a' })).toBe(false);
    expect(isErrorContext(null)).toBe(false);
  });

  it('is catchable as a plain Error and keeps its prototype after throw', () => {
    try {
      throw new PraisonAIError('thrown');
    } catch (e) {
      expect(e instanceof Error).toBe(true);
      expect(e instanceof PraisonAIError).toBe(true);
      expect(Object.getPrototypeOf(e)).toBe(PraisonAIError.prototype);
    }
  });
});

describe('Error hierarchy: instanceof chain', () => {
  const cases: Array<[string, () => Error]> = [
    ['ToolExecutionError', () => new ToolExecutionError('t')],
    ['LLMError', () => new LLMError('l')],
    ['ValidationError', () => new ValidationError('v')],
    ['NetworkError', () => new NetworkError('n')],
    ['PraisonAIConfigError', () => new PraisonAIConfigError('c')],
  ];

  it.each(cases)('%s extends PraisonAIError and Error', (name, make) => {
    const err = make();
    expect(err).toBeInstanceOf(Error);
    expect(err).toBeInstanceOf(PraisonAIError);
    expect(err.name).toBe(name);
    expect(Object.getPrototypeOf(err).constructor.name).toBe(name);
  });

  it('siblings are not instances of each other', () => {
    expect(new LLMError('x')).not.toBeInstanceOf(ToolExecutionError);
    expect(new ToolExecutionError('x')).not.toBeInstanceOf(NetworkError);
    expect(new PraisonAIError('x')).not.toBeInstanceOf(ValidationError);
  });
});

describe('ToolExecutionError', () => {
  it('defaults: tool_name=unknown, retryable=True, category=unknown', () => {
    const err = new ToolExecutionError('failed');
    expect(err.toolName).toBe('unknown');
    expect(err.isRetryable).toBe(true);
    expect(err.errorCategory).toBe('unknown');
    expect(err.context).toEqual({ tool_name: 'unknown' });
  });

  it('records tool_name into context without mutating the caller context', () => {
    const ctx = { attempt: 2 };
    const err = new ToolExecutionError('failed', { toolName: 'search', context: ctx, isRetryable: false, errorCategory: 'idle_timeout' });
    expect(err.toolName).toBe('search');
    expect(err.context).toEqual({ attempt: 2, tool_name: 'search' });
    expect(ctx).toEqual({ attempt: 2 });
    expect(err.isRetryable).toBe(false);
    expect(err.errorCategory).toBe('idle_timeout');
    expect(err.toDict().context).toEqual({ attempt: 2, tool_name: 'search' });
  });
});

describe('LLMError', () => {
  it('defaults: model_name=unknown, retryable=False', () => {
    const err = new LLMError('rate limited');
    expect(err.modelName).toBe('unknown');
    expect(err.isRetryable).toBe(false);
    expect(err.context).toEqual({ model_name: 'unknown' });
  });

  it('accepts model_name and retryable rate limits', () => {
    const err = new LLMError('rate limited', { modelName: 'gpt-4o', errorCategory: 'rate_limit', isRetryable: true });
    expect(err.modelName).toBe('gpt-4o');
    expect(err.errorCategory).toBe('rate_limit');
    expect(err.isRetryable).toBe(true);
    expect(err.context.model_name).toBe('gpt-4o');
  });
});

describe('ValidationError', () => {
  it('is always format_error and non-retryable', () => {
    const err = new ValidationError('bad input');
    expect(err.errorCategory).toBe('format_error');
    expect(err.isRetryable).toBe(false);
    expect(err.fieldName).toBeUndefined();
    expect(err.context).toEqual({});
  });

  it('records field_name only when given', () => {
    const err = new ValidationError('bad input', { fieldName: 'email', agentId: 'a1' });
    expect(err.fieldName).toBe('email');
    expect(err.context).toEqual({ field_name: 'email' });
    expect(err.agentId).toBe('a1');
    expect(new ValidationError('x', { fieldName: '' }).context).toEqual({});
  });
});

describe('NetworkError', () => {
  it('defaults: service_name=unknown, status_code=None, retryable=True', () => {
    const err = new NetworkError('down');
    expect(err.serviceName).toBe('unknown');
    expect(err.statusCode).toBeUndefined();
    expect(err.isRetryable).toBe(true);
    expect(err.context).toEqual({ service_name: 'unknown', status_code: null });
  });

  it('records service_name and status_code', () => {
    const err = new NetworkError('down', { serviceName: 'openai', statusCode: 503, errorCategory: 'overloaded' });
    expect(err.serviceName).toBe('openai');
    expect(err.statusCode).toBe(503);
    expect(err.context).toEqual({ service_name: 'openai', status_code: 503 });
    expect(err.errorCategory).toBe('overloaded');
  });
});

describe('PraisonAIConfigError', () => {
  it('plain message: no key, no hint, format_error, non-retryable', () => {
    const err = new PraisonAIConfigError('Missing config');
    expect(err.message).toBe('Missing config');
    expect(err.configKey).toBeUndefined();
    expect(err.remediationHint).toBeUndefined();
    expect(err.errorCategory).toBe('format_error');
    expect(err.isRetryable).toBe(false);
    expect(err.context).toEqual({});
  });

  it('derives the remediation hint from config_key and appends it to the message', () => {
    const err = new PraisonAIConfigError('OPENAI_API_KEY is not set.', { configKey: 'OPENAI_API_KEY' });
    expect(err.remediationHint).toBe('Set OPENAI_API_KEY or run the setup wizard before retrying.');
    expect(err.message).toBe(
      'OPENAI_API_KEY is not set. Remediation: Set OPENAI_API_KEY or run the setup wizard before retrying.'
    );
    expect(err.context).toEqual({
      config_key: 'OPENAI_API_KEY',
      remediation_hint: 'Set OPENAI_API_KEY or run the setup wizard before retrying.',
    });
  });

  it('keeps an explicit remediation hint', () => {
    const err = new PraisonAIConfigError('Bad model.', { configKey: 'MODEL', remediationHint: 'Pick a listed model.' });
    expect(err.remediationHint).toBe('Pick a listed model.');
    expect(err.message).toBe('Bad model. Remediation: Pick a listed model.');
    expect(err.context.remediation_hint).toBe('Pick a listed model.');
  });

  it('hint without key still appends', () => {
    const err = new PraisonAIConfigError('Oops.', { remediationHint: 'Do X.', isRetryable: true });
    expect(err.message).toBe('Oops. Remediation: Do X.');
    expect(err.context).toEqual({ remediation_hint: 'Do X.' });
    expect(err.isRetryable).toBe(true);
  });
});
