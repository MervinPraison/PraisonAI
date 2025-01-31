import { Tool, ToolManager } from '../../../src/tools/tools';

describe('Tool Manager', () => {
  let toolManager: ToolManager;

  beforeEach(() => {
    toolManager = new ToolManager();
  });

  describe('tool registration', () => {
    it('should register tools', () => {
      const calculatorTool: Tool = {
        name: 'calculator',
        description: 'Performs calculations',
        execute: async () => '42'
      };

      const translatorTool: Tool = {
        name: 'translator',
        description: 'Translates text',
        execute: async () => 'translated'
      };

      toolManager.register(calculatorTool);
      toolManager.register(translatorTool);

      const registeredTools = toolManager.list();
      expect(registeredTools.length).toBe(2);
      expect(registeredTools.map(t => t.name)).toEqual(['calculator', 'translator']);
    });

    it('should prevent duplicate tool registration', () => {
      const tool: Tool = {
        name: 'calculator',
        description: 'Performs calculations',
        execute: async () => '42'
      };

      toolManager.register(tool);
      expect(() => toolManager.register(tool)).toThrow();
    });
  });

  describe('tool execution', () => {
    it('should execute registered tool', async () => {
      const tool: Tool = {
        name: 'calculator',
        description: 'Performs calculations',
        execute: async () => '42'
      };

      toolManager.register(tool);
      const result = await toolManager.execute('calculator', '2 + 2');
      expect(result).toBe('42');
    });

    it('should throw error for unregistered tool', async () => {
      await expect(toolManager.execute('unknown', 'input')).rejects.toThrow();
    });
  });

  describe('tool discovery', () => {
    it('should find tools by category', () => {
      const calculator: Tool = {
        name: 'calculator',
        description: 'Performs calculations',
        category: 'math',
        execute: async () => '42'
      };

      const adder: Tool = {
        name: 'adder',
        description: 'Adds numbers',
        category: 'math',
        execute: async () => '2'
      };

      toolManager.register(calculator);
      toolManager.register(adder);

      const mathTools = toolManager.findByCategory('math');
      expect(mathTools.length).toBe(2);
      expect(mathTools.map(t => t.name)).toEqual(['calculator', 'adder']);
    });
  });
});
