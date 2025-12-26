/**
 * CLI Commands Tests
 */

import { formatSuccess, formatError } from '../../src/cli/output/json';
import { ERROR_CODES } from '../../src/cli/output/errors';

describe('Output Formatting', () => {
  describe('formatSuccess', () => {
    it('should format success response without meta', () => {
      const result = formatSuccess({ response: 'Hello' });
      expect(result).toEqual({
        success: true,
        data: { response: 'Hello' }
      });
    });

    it('should format success response with meta', () => {
      const result = formatSuccess(
        { response: 'Hello' },
        { duration_ms: 100, model: 'gpt-4' }
      );
      expect(result).toEqual({
        success: true,
        data: { response: 'Hello' },
        meta: { duration_ms: 100, model: 'gpt-4' }
      });
    });

    it('should include token counts in meta', () => {
      const result = formatSuccess(
        { response: 'Hello' },
        { tokens: { input: 10, output: 5 } }
      );
      expect(result.meta?.tokens).toEqual({ input: 10, output: 5 });
    });
  });

  describe('formatError', () => {
    it('should format error response', () => {
      const result = formatError('MISSING_ARGUMENT', 'Please provide a prompt');
      expect(result).toEqual({
        success: false,
        error: {
          code: 'MISSING_ARGUMENT',
          message: 'Please provide a prompt'
        }
      });
    });

    it('should include details when provided', () => {
      const result = formatError('INVALID_ARGUMENTS', 'Bad input', { field: 'model' });
      expect(result.error.details).toEqual({ field: 'model' });
    });
  });
});

describe('Error Codes', () => {
  it('should have all required error codes', () => {
    expect(ERROR_CODES.UNKNOWN).toBe('UNKNOWN_ERROR');
    expect(ERROR_CODES.INVALID_ARGS).toBe('INVALID_ARGUMENTS');
    expect(ERROR_CODES.MISSING_ARG).toBe('MISSING_ARGUMENT');
    expect(ERROR_CODES.MISSING_API_KEY).toBe('MISSING_API_KEY');
    expect(ERROR_CODES.NETWORK_TIMEOUT).toBe('NETWORK_TIMEOUT');
    expect(ERROR_CODES.PROVIDER_ERROR).toBe('PROVIDER_ERROR');
  });
});
