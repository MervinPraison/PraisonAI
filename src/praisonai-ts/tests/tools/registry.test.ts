/**
 * Tests for AI SDK Tools Registry
 */

import {
  ToolsRegistry,
  getToolsRegistry,
  createToolsRegistry,
  resetToolsRegistry,
} from '../../src/tools/registry/registry';
import {
  createLoggingMiddleware,
  createTimeoutMiddleware,
  createRedactionMiddleware,
  createRateLimitMiddleware,
  composeMiddleware,
} from '../../src/tools/registry/middleware';
import type { ToolMetadata, PraisonTool, ToolExecutionContext } from '../../src/tools/registry/types';
import { MissingDependencyError, MissingEnvVarError } from '../../src/tools/registry/types';

describe('ToolsRegistry', () => {
  let registry: ToolsRegistry;

  beforeEach(() => {
    registry = createToolsRegistry();
  });

  describe('registration', () => {
    const mockMetadata: ToolMetadata = {
      id: 'test-tool',
      displayName: 'Test Tool',
      description: 'A test tool',
      tags: ['test', 'mock'],
      requiredEnv: [],
      optionalEnv: [],
      install: {
        npm: 'npm install test-tool',
        pnpm: 'pnpm add test-tool',
        yarn: 'yarn add test-tool',
        bun: 'bun add test-tool',
      },
      docsSlug: 'tools/test',
      capabilities: { search: true },
      packageName: 'test-tool',
    };

    const mockFactory = () => ({
      name: 'testTool',
      description: 'A test tool',
      parameters: { type: 'object' as const, properties: {} },
      execute: async () => ({ result: 'success' }),
    });

    it('should register a tool', () => {
      registry.register(mockMetadata, mockFactory);
      expect(registry.has('test-tool')).toBe(true);
    });

    it('should unregister a tool', () => {
      registry.register(mockMetadata, mockFactory);
      expect(registry.unregister('test-tool')).toBe(true);
      expect(registry.has('test-tool')).toBe(false);
    });

    it('should get tool metadata', () => {
      registry.register(mockMetadata, mockFactory);
      const meta = registry.getMetadata('test-tool');
      expect(meta).toEqual(mockMetadata);
    });

    it('should list all tools', () => {
      registry.register(mockMetadata, mockFactory);
      const list = registry.list();
      expect(list).toHaveLength(1);
      expect(list[0].id).toBe('test-tool');
    });

    it('should list tools by tag', () => {
      registry.register(mockMetadata, mockFactory);
      registry.register({ ...mockMetadata, id: 'other-tool', tags: ['other'] }, mockFactory);
      
      const testTools = registry.listByTag('test');
      expect(testTools).toHaveLength(1);
      expect(testTools[0].id).toBe('test-tool');
    });

    it('should list tools by capability', () => {
      registry.register(mockMetadata, mockFactory);
      registry.register({ ...mockMetadata, id: 'no-search', capabilities: {} }, mockFactory);
      
      const searchTools = registry.listByCapability('search');
      expect(searchTools).toHaveLength(1);
      expect(searchTools[0].id).toBe('test-tool');
    });
  });

  describe('tool creation', () => {
    const mockMetadata: ToolMetadata = {
      id: 'create-test',
      displayName: 'Create Test',
      description: 'Test creation',
      tags: [],
      requiredEnv: [],
      optionalEnv: [],
      install: { npm: '', pnpm: '', yarn: '', bun: '' },
      docsSlug: '',
      capabilities: {},
      packageName: 'test',
    };

    it('should create a tool instance', () => {
      const mockTool: PraisonTool = {
        name: 'createTest',
        description: 'Test',
        parameters: { type: 'object', properties: {} },
        execute: async (input) => ({ input }),
      };

      registry.register(mockMetadata, () => mockTool);
      const tool = registry.create('create-test');
      
      expect(tool.name).toBe('createTest');
      expect(typeof tool.execute).toBe('function');
    });

    it('should throw for unknown tool', () => {
      expect(() => registry.create('unknown')).toThrow('Tool "unknown" is not registered');
    });
  });

  describe('middleware', () => {
    it('should execute middleware in order', async () => {
      const order: number[] = [];
      
      const mockTool: PraisonTool = {
        name: 'mwTest',
        description: 'Test',
        parameters: { type: 'object', properties: {} },
        execute: async () => {
          order.push(3);
          return { result: 'done' };
        },
      };

      registry.register({
        id: 'mw-test',
        displayName: 'MW Test',
        description: '',
        tags: [],
        requiredEnv: [],
        optionalEnv: [],
        install: { npm: '', pnpm: '', yarn: '', bun: '' },
        docsSlug: '',
        capabilities: {},
        packageName: '',
      }, () => mockTool);

      registry.use(async (input, ctx, next) => {
        order.push(1);
        const result = await next();
        order.push(4);
        return result;
      });

      registry.use(async (input, ctx, next) => {
        order.push(2);
        const result = await next();
        order.push(5);
        return result;
      });

      const tool = registry.create('mw-test');
      await tool.execute({});

      expect(order).toEqual([1, 2, 3, 5, 4]);
    });
  });

  describe('hooks', () => {
    it('should call beforeToolCall hook', async () => {
      let hookCalled = false;
      
      const mockTool: PraisonTool = {
        name: 'hookTest',
        description: 'Test',
        parameters: { type: 'object', properties: {} },
        execute: async () => ({ result: 'done' }),
      };

      registry.register({
        id: 'hook-test',
        displayName: 'Hook Test',
        description: '',
        tags: [],
        requiredEnv: [],
        optionalEnv: [],
        install: { npm: '', pnpm: '', yarn: '', bun: '' },
        docsSlug: '',
        capabilities: {},
        packageName: '',
      }, () => mockTool);

      registry.setHooks({
        beforeToolCall: (name, input, ctx) => {
          hookCalled = true;
          expect(name).toBe('hookTest');
        },
      });

      const tool = registry.create('hook-test');
      await tool.execute({});

      expect(hookCalled).toBe(true);
    });

    it('should call afterToolCall hook', async () => {
      let hookCalled = false;
      
      const mockTool: PraisonTool = {
        name: 'afterHookTest',
        description: 'Test',
        parameters: { type: 'object', properties: {} },
        execute: async () => ({ result: 'done' }),
      };

      registry.register({
        id: 'after-hook-test',
        displayName: 'After Hook Test',
        description: '',
        tags: [],
        requiredEnv: [],
        optionalEnv: [],
        install: { npm: '', pnpm: '', yarn: '', bun: '' },
        docsSlug: '',
        capabilities: {},
        packageName: '',
      }, () => mockTool);

      registry.setHooks({
        afterToolCall: (name, input, output, ctx) => {
          hookCalled = true;
          expect(output).toEqual({ result: 'done' });
        },
      });

      const tool = registry.create('after-hook-test');
      await tool.execute({});

      expect(hookCalled).toBe(true);
    });
  });
});

describe('Global Registry', () => {
  beforeEach(() => {
    resetToolsRegistry();
  });

  it('should return singleton instance', () => {
    const r1 = getToolsRegistry();
    const r2 = getToolsRegistry();
    expect(r1).toBe(r2);
  });

  it('should reset registry', () => {
    const r1 = getToolsRegistry();
    r1.register({
      id: 'temp',
      displayName: 'Temp',
      description: '',
      tags: [],
      requiredEnv: [],
      optionalEnv: [],
      install: { npm: '', pnpm: '', yarn: '', bun: '' },
      docsSlug: '',
      capabilities: {},
      packageName: '',
    }, () => ({
      name: 'temp',
      description: '',
      parameters: { type: 'object', properties: {} },
      execute: async () => ({}),
    }));

    expect(r1.size).toBe(1);
    
    resetToolsRegistry();
    const r2 = getToolsRegistry();
    expect(r2.size).toBe(0);
    expect(r1).not.toBe(r2);
  });
});

describe('Middleware Functions', () => {
  describe('createTimeoutMiddleware', () => {
    it('should timeout long operations', async () => {
      const middleware = createTimeoutMiddleware(100);
      
      const slowNext = () => new Promise<unknown>((resolve) => {
        setTimeout(() => resolve('done'), 500);
      });

      await expect(middleware({}, {}, slowNext)).rejects.toThrow('timed out');
    });

    it('should allow fast operations', async () => {
      const middleware = createTimeoutMiddleware(1000);
      
      const fastNext = () => Promise.resolve('done');

      const result = await middleware({}, {}, fastNext);
      expect(result).toBe('done');
    });
  });

  describe('createRedactionMiddleware', () => {
    it('should redact email addresses', async () => {
      const middleware = createRedactionMiddleware();
      
      const next = () => Promise.resolve({ text: 'Contact john@example.com for help' });

      const result = await middleware({}, {}, next) as { text: string };
      expect(result.text).toContain('[REDACTED]');
      expect(result.text).not.toContain('john@example.com');
    });

    it('should redact SSN', async () => {
      const middleware = createRedactionMiddleware();
      
      const next = () => Promise.resolve({ ssn: '123-45-6789' });

      const result = await middleware({}, {}, next) as { ssn: string };
      expect(result.ssn).toBe('[REDACTED]');
    });
  });

  describe('createRateLimitMiddleware', () => {
    it('should allow requests within limit', async () => {
      const middleware = createRateLimitMiddleware(5, 1000);
      const next = () => Promise.resolve('ok');

      // Should allow 5 requests
      for (let i = 0; i < 5; i++) {
        await expect(middleware({}, {}, next)).resolves.toBe('ok');
      }
    });

    it('should reject requests over limit', async () => {
      const middleware = createRateLimitMiddleware(2, 1000);
      const next = () => Promise.resolve('ok');

      await middleware({}, {}, next);
      await middleware({}, {}, next);
      
      await expect(middleware({}, {}, next)).rejects.toThrow('Rate limit exceeded');
    });
  });

  describe('composeMiddleware', () => {
    it('should compose multiple middleware', async () => {
      const order: string[] = [];

      const mw1 = async (input: unknown, ctx: ToolExecutionContext, next: () => Promise<unknown>) => {
        order.push('mw1-before');
        const result = await next();
        order.push('mw1-after');
        return result;
      };

      const mw2 = async (input: unknown, ctx: ToolExecutionContext, next: () => Promise<unknown>) => {
        order.push('mw2-before');
        const result = await next();
        order.push('mw2-after');
        return result;
      };

      const composed = composeMiddleware(mw1, mw2);
      const next = () => {
        order.push('handler');
        return Promise.resolve('done');
      };

      await composed({}, {}, next);

      expect(order).toEqual(['mw1-before', 'mw2-before', 'handler', 'mw2-after', 'mw1-after']);
    });
  });
});

describe('Error Classes', () => {
  describe('MissingDependencyError', () => {
    it('should include install instructions', () => {
      const error = new MissingDependencyError(
        'test-tool',
        '@test/package',
        {
          npm: 'npm install @test/package',
          pnpm: 'pnpm add @test/package',
          yarn: 'yarn add @test/package',
          bun: 'bun add @test/package',
        },
        ['TEST_API_KEY'],
        'tools/test'
      );

      expect(error.message).toContain('@test/package');
      expect(error.message).toContain('npm install');
      expect(error.message).toContain('TEST_API_KEY');
      expect(error.name).toBe('MissingDependencyError');
    });
  });

  describe('MissingEnvVarError', () => {
    it('should include env var name', () => {
      const error = new MissingEnvVarError('test-tool', 'API_KEY', 'tools/test');

      expect(error.message).toContain('API_KEY');
      expect(error.message).toContain('test-tool');
      expect(error.name).toBe('MissingEnvVarError');
    });
  });
});
