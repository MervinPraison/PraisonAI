import { describe, expect, it, jest } from '@jest/globals';
import { createValidationMiddleware } from '../../../src/tools/registry/middleware';

const payloads: Array<[string, unknown]> = [
  ['CJK text', '你好'],
  ['emoji', '🙂'],
  ['nested JSON', { message: '中文🙂', values: ['é'] }],
];

describe('tool payload UTF-8 byte limits', () => {
  it.each(payloads)('rejects %s above its actual byte budget', async (_label, input) => {
    const bytes = Buffer.byteLength(JSON.stringify(input), 'utf8');
    const next = jest.fn(async () => 'executed');
    await expect(createValidationMiddleware()(input, { limits: { maxPayloadBytes: bytes - 1 } }, next))
      .rejects.toThrow(`Input payload size (${bytes} bytes) exceeds limit (${bytes - 1} bytes)`);
    expect(next).not.toHaveBeenCalled();
  });

  it.each(payloads)('accepts %s at the exact byte budget', async (_label, input) => {
    const bytes = Buffer.byteLength(JSON.stringify(input), 'utf8');
    const next = jest.fn(async () => 'executed');
    expect(await createValidationMiddleware()(input, { limits: { maxPayloadBytes: bytes } }, next)).toBe('executed');
    expect(next).toHaveBeenCalledTimes(1);
  });

  it('preserves ASCII boundaries', async () => {
    const next = jest.fn(async () => 'executed');
    const validate = createValidationMiddleware();
    await expect(validate('hello', { limits: { maxPayloadBytes: 6 } }, next)).rejects.toThrow('7 bytes');
    expect(await validate('hello', { limits: { maxPayloadBytes: 7 } }, next)).toBe('executed');
    expect(next).toHaveBeenCalledTimes(1);
  });

  it('does not serialize inputs when no payload limit is configured', async () => {
    const cyclic: { self?: unknown } = {};
    cyclic.self = cyclic;
    const next = jest.fn(async () => 'executed');
    expect(await createValidationMiddleware()(cyclic, {}, next)).toBe('executed');
  });

  it('continues rejecting non-JSON undefined input when a limit is configured', async () => {
    const next = jest.fn(async () => 'executed');
    await expect(createValidationMiddleware()(undefined, { limits: { maxPayloadBytes: 10 } }, next)).rejects.toThrow(TypeError);
    expect(next).not.toHaveBeenCalled();
  });

  it('preserves circular JSON errors when a limit is configured', async () => {
    const cyclic: { self?: unknown } = {};
    cyclic.self = cyclic;
    const next = jest.fn(async () => 'executed');
    await expect(createValidationMiddleware()(cyclic, { limits: { maxPayloadBytes: 100 } }, next)).rejects.toThrow(TypeError);
    expect(next).not.toHaveBeenCalled();
  });
});
