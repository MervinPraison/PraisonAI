/**
 * Tool Decorator Unit Tests
 */

import { describe, it, expect, beforeEach } from '@jest/globals';
import { tool, FunctionTool, ToolRegistry, getRegistry, registerTool, getTool } from '../../../src/tools/decorator';

describe('Tool Decorator', () => {
  describe('tool function', () => {
    it('should create tool from config', () => {
      const myTool = tool({
        name: 'greet',
        description: 'Greet a person',
        execute: async ({ name }: { name: string }) => `Hello, ${name}!`,
      });
      expect(myTool.name).toBe('greet');
      expect(myTool.description).toBe('Greet a person');
    });

    it('should execute with parameters', async () => {
      const myTool = tool({
        name: 'add',
        execute: async ({ a, b }: { a: number; b: number }) => a + b,
      });
      const result = await myTool.execute({ a: 1, b: 2 });
      expect(result).toBe(3);
    });

    it('should have default description', () => {
      const myTool = tool({
        name: 'test',
        execute: async () => 'result',
      });
      expect(myTool.description).toBe('Function test');
    });

    it('should support category', () => {
      const myTool = tool({
        name: 'search',
        category: 'web',
        execute: async () => 'results',
      });
      expect(myTool.category).toBe('web');
    });

    it('should generate OpenAI tool format', () => {
      const myTool = tool({
        name: 'test',
        description: 'Test tool',
        parameters: {
          type: 'object',
          properties: { input: { type: 'string' } },
          required: ['input'],
        },
        execute: async () => 'result',
      });
      const openaiTool = myTool.toOpenAITool();
      expect(openaiTool.type).toBe('function');
      expect(openaiTool.function.name).toBe('test');
      expect(openaiTool.function.description).toBe('Test tool');
    });
  });

  describe('ToolRegistry', () => {
    let registry: ToolRegistry;

    beforeEach(() => {
      registry = new ToolRegistry();
    });

    it('should register and retrieve tools', () => {
      const myTool = tool({ name: 'test', execute: async () => 'result' });
      registry.register(myTool);
      expect(registry.get('test')).toBe(myTool);
    });

    it('should check if tool exists', () => {
      const myTool = tool({ name: 'test', execute: async () => 'result' });
      registry.register(myTool);
      expect(registry.has('test')).toBe(true);
      expect(registry.has('nonexistent')).toBe(false);
    });

    it('should list all tools', () => {
      registry.register(tool({ name: 'tool1', execute: async () => {} }));
      registry.register(tool({ name: 'tool2', execute: async () => {} }));
      expect(registry.list().length).toBe(2);
    });

    it('should get tools by category', () => {
      registry.register(tool({ name: 'search', category: 'web', execute: async () => {} }));
      registry.register(tool({ name: 'read', category: 'file', execute: async () => {} }));
      const webTools = registry.getByCategory('web');
      expect(webTools.length).toBe(1);
      expect(webTools[0].name).toBe('search');
    });

    it('should prevent duplicate registration', () => {
      registry.register(tool({ name: 'dup', execute: async () => {} }));
      expect(() => registry.register(tool({ name: 'dup', execute: async () => {} }))).toThrow();
    });

    it('should allow overwrite with flag', async () => {
      registry.register(tool({ name: 'dup', execute: async () => 'v1' }));
      registry.register(tool({ name: 'dup', execute: async () => 'v2' }), { overwrite: true });
      const result = await registry.get('dup')!.execute({});
      expect(result).toBe('v2');
    });

    it('should get definitions', () => {
      registry.register(tool({ name: 'test', description: 'Test', execute: async () => {} }));
      const defs = registry.getDefinitions();
      expect(defs.length).toBe(1);
      expect(defs[0].name).toBe('test');
    });

    it('should get OpenAI tools format', () => {
      registry.register(tool({ name: 'test', execute: async () => {} }));
      const tools = registry.toOpenAITools();
      expect(tools.length).toBe(1);
      expect(tools[0].type).toBe('function');
    });
  });

  describe('Global Registry', () => {
    beforeEach(() => {
      getRegistry().clear();
    });

    it('should register globally', () => {
      const myTool = tool({ name: 'global_test', execute: async () => 'result' });
      registerTool(myTool);
      expect(getTool('global_test')).toBe(myTool);
    });

    it('should return singleton', () => {
      const registry1 = getRegistry();
      const registry2 = getRegistry();
      expect(registry1).toBe(registry2);
    });
  });
});
