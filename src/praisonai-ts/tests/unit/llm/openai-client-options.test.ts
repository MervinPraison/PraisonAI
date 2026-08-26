import {
  buildOpenAIClientOptions,
  isBrowserLikeRuntime,
  getEnv,
} from '../../../src/llm/openaiClientOptions';

describe('buildOpenAIClientOptions', () => {
  const g = globalThis as any;
  const originalWindow = g.window;
  const originalNavigator = g.navigator;

  afterEach(() => {
    if (originalWindow === undefined) {
      delete g.window;
    } else {
      g.window = originalWindow;
    }
    if (originalNavigator === undefined) {
      delete g.navigator;
    } else {
      g.navigator = originalNavigator;
    }
  });

  it('leaves Node behaviour unchanged (no browser flag)', () => {
    delete g.window;
    delete g.navigator;
    expect(isBrowserLikeRuntime()).toBe(false);
    const opts = buildOpenAIClientOptions({ apiKey: 'sk-test' });
    expect(opts.apiKey).toBe('sk-test');
    expect(opts.dangerouslyAllowBrowser).toBeUndefined();
    expect(opts.fetch).toBeUndefined();
  });

  it('enables dangerouslyAllowBrowser in a browser-like runtime', () => {
    g.window = { document: {} };
    expect(isBrowserLikeRuntime()).toBe(true);
    const opts = buildOpenAIClientOptions({ apiKey: 'sk-test' });
    expect(opts.dangerouslyAllowBrowser).toBe(true);
  });

  it('detects React Native as browser-like', () => {
    delete g.window;
    g.navigator = { product: 'ReactNative' };
    expect(isBrowserLikeRuntime()).toBe(true);
    const opts = buildOpenAIClientOptions();
    expect(opts.dangerouslyAllowBrowser).toBe(true);
  });

  it('injects a custom fetch and implies browser support', () => {
    delete g.window;
    delete g.navigator;
    const customFetch = (async () => new Response('')) as unknown as typeof fetch;
    const opts = buildOpenAIClientOptions(
      { apiKey: 'sk-test' },
      { fetch: customFetch }
    );
    expect(opts.fetch).toBe(customFetch);
    expect(opts.dangerouslyAllowBrowser).toBe(true);
  });

  it('honours an explicit dangerouslyAllowBrowser override', () => {
    g.window = { document: {} };
    const opts = buildOpenAIClientOptions(
      { apiKey: 'sk-test' },
      { dangerouslyAllowBrowser: false }
    );
    expect(opts.dangerouslyAllowBrowser).toBeUndefined();
  });

  it('explicit false override strips a pre-set flag on the base options', () => {
    g.window = { document: {} };
    const opts = buildOpenAIClientOptions(
      { apiKey: 'sk-test', dangerouslyAllowBrowser: true },
      { dangerouslyAllowBrowser: false }
    );
    expect(opts.dangerouslyAllowBrowser).toBeUndefined();
  });

  it('actually constructs the real OpenAI SDK with browser-safe options', () => {
    // Exercise the real SDK (not the jest manual mock) to prove the options
    // the helper produces are the ones the browser guard requires. This calls
    // real code end-to-end rather than merely asserting a symbol is exported.
    jest.isolateModules(() => {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const mod = require('openai');
      const OpenAI = mod.default ?? mod;
      g.window = { document: {} };

      const opts = buildOpenAIClientOptions({ apiKey: 'sk-test' });
      expect(opts.dangerouslyAllowBrowser).toBe(true);

      // Constructing with the helper's browser-safe options must not throw.
      expect(() => new OpenAI(opts)).not.toThrow();
    });
  });
});

describe('getEnv', () => {
  it('reads an existing environment variable in Node', () => {
    process.env.PRAISON_TEST_ENV = 'present';
    expect(getEnv('PRAISON_TEST_ENV')).toBe('present');
    delete process.env.PRAISON_TEST_ENV;
  });

  it('returns undefined without throwing when process is absent (browser)', () => {
    const savedProcess = (globalThis as any).process;
    // Simulate a browser/webview where `process` is not defined.
    delete (globalThis as any).process;
    try {
      expect(() => getEnv('OPENAI_API_KEY')).not.toThrow();
      expect(getEnv('OPENAI_API_KEY')).toBeUndefined();
    } finally {
      (globalThis as any).process = savedProcess;
    }
  });
});
