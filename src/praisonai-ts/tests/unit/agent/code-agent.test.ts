/**
 * CodeAgent Tests - TDD for code generation, execution, review
 * Python parity with praisonaiagents/agent/code_agent.py
 */

import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import {
  CodeAgent,
  CodeConfig,
  CodeExecutionResult,
  createCodeAgent,
} from '../../../src/agent/code';

describe('CodeConfig (Python Parity)', () => {
  it('should have sensible defaults', () => {
    const config: CodeConfig = {};
    expect(config.sandbox).toBeUndefined(); // defaults applied in class
    expect(config.timeout).toBeUndefined();
    expect(config.allowedLanguages).toBeUndefined();
  });

  it('should accept all configuration options', () => {
    const config: CodeConfig = {
      sandbox: true,
      timeout: 30,
      allowedLanguages: ['python', 'javascript'],
      maxOutputLength: 10000,
      workingDirectory: '/tmp',
      environment: { NODE_ENV: 'test' },
    };
    expect(config.sandbox).toBe(true);
    expect(config.timeout).toBe(30);
    expect(config.allowedLanguages).toEqual(['python', 'javascript']);
    expect(config.maxOutputLength).toBe(10000);
    expect(config.workingDirectory).toBe('/tmp');
    expect(config.environment).toEqual({ NODE_ENV: 'test' });
  });
});

describe('CodeAgent', () => {
  describe('Construction', () => {
    it('should create with minimal config', () => {
      const agent = new CodeAgent({ name: 'Coder' });
      expect(agent.name).toBe('Coder');
    });

    it('should create with full config', () => {
      const agent = new CodeAgent({
        name: 'Coder',
        llm: 'gpt-4o-mini',
        code: {
          sandbox: true,
          timeout: 60,
          allowedLanguages: ['python', 'typescript'],
        },
        instructions: 'Write clean code',
        verbose: false,
      });
      expect(agent.name).toBe('Coder');
    });

    it('should accept boolean for code config', () => {
      const agent = new CodeAgent({
        name: 'Coder',
        code: true,
      });
      expect(agent.name).toBe('Coder');
    });
  });

  describe('Code Generation', () => {
    it('should have generate method', () => {
      const agent = new CodeAgent({ name: 'Coder' });
      expect(typeof agent.generate).toBe('function');
    });

    it('should have generateCode alias', () => {
      const agent = new CodeAgent({ name: 'Coder' });
      expect(typeof agent.generateCode).toBe('function');
    });
  });

  describe('Code Execution', () => {
    it('should have execute method', () => {
      const agent = new CodeAgent({ name: 'Coder' });
      expect(typeof agent.execute).toBe('function');
    });

    it('should have executeCode alias', () => {
      const agent = new CodeAgent({ name: 'Coder' });
      expect(typeof agent.executeCode).toBe('function');
    });
  });

  describe('Code Review', () => {
    it('should have review method', () => {
      const agent = new CodeAgent({ name: 'Coder' });
      expect(typeof agent.review).toBe('function');
    });

    it('should have reviewCode alias', () => {
      const agent = new CodeAgent({ name: 'Coder' });
      expect(typeof agent.reviewCode).toBe('function');
    });
  });

  describe('Code Refactoring', () => {
    it('should have refactor method', () => {
      const agent = new CodeAgent({ name: 'Coder' });
      expect(typeof agent.refactor).toBe('function');
    });

    it('should have fix method', () => {
      const agent = new CodeAgent({ name: 'Coder' });
      expect(typeof agent.fix).toBe('function');
    });

    it('should have explain method', () => {
      const agent = new CodeAgent({ name: 'Coder' });
      expect(typeof agent.explain).toBe('function');
    });
  });
});

describe('CodeExecutionResult', () => {
  it('should have all required fields', () => {
    const result: CodeExecutionResult = {
      success: true,
      output: 'Hello, World!',
      error: undefined,
      exitCode: 0,
      executionTime: 0.5,
    };
    expect(result.success).toBe(true);
    expect(result.output).toBe('Hello, World!');
    expect(result.exitCode).toBe(0);
    expect(result.executionTime).toBe(0.5);
  });

  it('should handle error case', () => {
    const result: CodeExecutionResult = {
      success: false,
      output: '',
      error: 'SyntaxError: invalid syntax',
      exitCode: 1,
      executionTime: 0.1,
    };
    expect(result.success).toBe(false);
    expect(result.error).toBe('SyntaxError: invalid syntax');
    expect(result.exitCode).toBe(1);
  });
});

describe('createCodeAgent factory', () => {
  it('should create CodeAgent instance', () => {
    const agent = createCodeAgent({ name: 'Coder' });
    expect(agent).toBeInstanceOf(CodeAgent);
    expect(agent.name).toBe('Coder');
  });
});
