import { isLoopbackHost, requireBindToken, tokenMatches } from '../../../src/utils/bind-guard';

describe('requireBindToken', () => {
  test.each(['127.0.0.1', '127.0.0.2', 'localhost', '::1', '[::1]', '::ffff:127.0.0.1'])('loopback %s may be keyless', (h) => {
    expect(isLoopbackHost(h)).toBe(true);
    expect(() => requireBindToken(h, undefined, { server: 's', hint: 'h' })).not.toThrow();
  });

  test.each(['0.0.0.0', '::', '10.0.0.5', 'example.com', '127.0.0.1.foreign.com', '1270.0.0.1'])('%s needs a token', (h) => {
    expect(isLoopbackHost(h)).toBe(false);
    expect(() => requireBindToken(h, '', { server: 'S', hint: 'Set X' })).toThrow(/S refuses .*Set X/);
    expect(() => requireBindToken(h, 'tok', { server: 'S', hint: 'Set X' })).not.toThrow();
  });
});

describe('tokenMatches', () => {
  test('matches only the exact token', () => {
    expect(tokenMatches('secret', 'secret')).toBe(true);
    expect(tokenMatches('secreT', 'secret')).toBe(false);
    expect(tokenMatches('secret-longer', 'secret')).toBe(false);
    expect(tokenMatches('', 'secret')).toBe(false);
    expect(tokenMatches(undefined, 'secret')).toBe(false);
    expect(tokenMatches(['secret'], 'secret')).toBe(false);
    expect(tokenMatches('anything', '')).toBe(false);
  });
});
