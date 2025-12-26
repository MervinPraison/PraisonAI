/**
 * BaseTool Unit Tests
 * Tests for the abstract BaseTool class and plugin extensibility
 */

import { BaseTool, ToolResult, ToolValidationError, validateTool, createTool } from '../../../src/tools/base';

// Test implementation of BaseTool
class WeatherTool extends BaseTool<{ location: string }, { temp: number; condition: string }> {
  name = 'get_weather';
  description = 'Get current weather for a location';
  
  async run(params: { location: string }): Promise<{ temp: number; condition: string }> {
    return { temp: 22, condition: 'sunny' };
  }
}

class CalculatorTool extends BaseTool<{ expression: string }, number> {
  name = 'calculator';
  description = 'Evaluate a math expression';
  parameters = {
    type: 'object' as const,
    properties: {
      expression: { type: 'string', description: 'Math expression to evaluate' }
    },
    required: ['expression']
  };
  
  run(params: { expression: string }): number {
    return eval(params.expression);
  }
}

describe('BaseTool', () => {
  describe('Basic functionality', () => {
    it('should create a tool with name and description', () => {
      const tool = new WeatherTool();
      expect(tool.name).toBe('get_weather');
      expect(tool.description).toBe('Get current weather for a location');
    });

    it('should have default version', () => {
      const tool = new WeatherTool();
      expect(tool.version).toBe('1.0.0');
    });

    it('should execute run method', async () => {
      const tool = new WeatherTool();
      const result = await tool.run({ location: 'New York' });
      expect(result.temp).toBe(22);
      expect(result.condition).toBe('sunny');
    });

    it('should execute via execute method', async () => {
      const tool = new WeatherTool();
      const result = await tool.execute({ location: 'London' });
      expect(result.temp).toBe(22);
    });
  });

  describe('safeRun', () => {
    it('should return ToolResult on success', async () => {
      const tool = new WeatherTool();
      const result = await tool.safeRun({ location: 'Paris' });
      expect(result.success).toBe(true);
      expect(result.output.temp).toBe(22);
      expect(result.error).toBeUndefined();
    });

    it('should catch errors and return ToolResult', async () => {
      class FailingTool extends BaseTool<{}, string> {
        name = 'failing';
        description = 'Always fails';
        run(): string {
          throw new Error('Intentional failure');
        }
      }
      
      const tool = new FailingTool();
      const result = await tool.safeRun({});
      expect(result.success).toBe(false);
      expect(result.error).toBe('Intentional failure');
    });
  });

  describe('getSchema', () => {
    it('should return OpenAI-compatible schema', () => {
      const tool = new CalculatorTool();
      const schema = tool.getSchema();
      
      expect(schema.type).toBe('function');
      expect(schema.function.name).toBe('calculator');
      expect(schema.function.description).toBe('Evaluate a math expression');
      expect(schema.function.parameters.properties.expression.type).toBe('string');
    });

    it('should return empty parameters if not defined', () => {
      const tool = new WeatherTool();
      const schema = tool.getSchema();
      
      expect(schema.function.parameters.type).toBe('object');
      expect(schema.function.parameters.properties).toEqual({});
    });
  });

  describe('validate', () => {
    it('should pass validation for valid tool', () => {
      const tool = new WeatherTool();
      expect(tool.validate()).toBe(true);
    });

    it('should throw ToolValidationError for invalid tool', () => {
      class InvalidTool extends BaseTool<{}, string> {
        name = '';
        description = '';
        run(): string {
          return 'test';
        }
      }
      
      const tool = new InvalidTool();
      expect(() => tool.validate()).toThrow(ToolValidationError);
    });
  });

  describe('toString', () => {
    it('should return string representation', () => {
      const tool = new WeatherTool();
      expect(tool.toString()).toBe("WeatherTool(name='get_weather')");
    });
  });
});

describe('validateTool', () => {
  it('should validate BaseTool instance', () => {
    const tool = new WeatherTool();
    expect(validateTool(tool)).toBe(true);
  });

  it('should validate callable with name', () => {
    const fn = function myTool() { return 'test'; };
    expect(validateTool(fn)).toBe(true);
  });

  it('should throw for invalid tool', () => {
    expect(() => validateTool({})).toThrow(ToolValidationError);
  });
});

describe('createTool', () => {
  it('should create a tool from config', async () => {
    const tool = createTool({
      name: 'greeter',
      description: 'Greet someone',
      run: (params: { name: string }) => `Hello, ${params.name}!`
    });

    expect(tool.name).toBe('greeter');
    expect(tool.description).toBe('Greet someone');
    
    const result = await tool.run({ name: 'World' });
    expect(result).toBe('Hello, World!');
  });

  it('should support async run function', async () => {
    const tool = createTool({
      name: 'async_tool',
      description: 'Async tool',
      run: async (params: { delay: number }) => {
        await new Promise(r => setTimeout(r, params.delay));
        return 'done';
      }
    });

    const result = await tool.run({ delay: 10 });
    expect(result).toBe('done');
  });

  it('should have safeRun method', async () => {
    const tool = createTool({
      name: 'safe_tool',
      description: 'Safe tool',
      run: () => 'success'
    });

    const result = await tool.safeRun({});
    expect(result.success).toBe(true);
    expect(result.output).toBe('success');
  });

  it('should have getSchema method', () => {
    const tool = createTool({
      name: 'schema_tool',
      description: 'Tool with schema',
      parameters: {
        type: 'object',
        properties: {
          input: { type: 'string' }
        },
        required: ['input']
      },
      run: (params: { input: string }) => params.input
    });

    const schema = tool.getSchema();
    expect(schema.function.name).toBe('schema_tool');
    expect(schema.function.parameters.properties.input.type).toBe('string');
  });
});
