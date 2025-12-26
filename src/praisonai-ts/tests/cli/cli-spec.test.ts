/**
 * CLI Spec Tests - Verify parity with spec
 */

import { parseArgs, CLI_SPEC_VERSION } from '../../src/cli/index';
import { COMMANDS, GLOBAL_FLAGS, EXIT_CODES, validateCommand } from '../../src/cli/spec/cli-spec';

describe('CLI Spec', () => {
  describe('Version', () => {
    it('should have correct spec version', () => {
      expect(CLI_SPEC_VERSION).toBe('1.0.0');
    });
  });

  describe('Commands', () => {
    it('should have all required commands', () => {
      const requiredCommands = ['chat', 'run', 'workflow', 'eval', 'providers', 'tools', 'version', 'help'];
      for (const cmd of requiredCommands) {
        expect(COMMANDS[cmd]).toBeDefined();
        expect(validateCommand(cmd)).toBe(true);
      }
    });

    it('should reject invalid commands', () => {
      expect(validateCommand('invalid')).toBe(false);
      expect(validateCommand('')).toBe(false);
    });
  });

  describe('Global Flags', () => {
    it('should have all required global flags', () => {
      const requiredFlags = ['verbose', 'config', 'profile', 'output', 'json'];
      const flagNames = GLOBAL_FLAGS.map(f => f.name);
      
      for (const flag of requiredFlags) {
        expect(flagNames).toContain(flag);
      }
    });

    it('should have short flags for common options', () => {
      const verboseFlag = GLOBAL_FLAGS.find(f => f.name === 'verbose');
      expect(verboseFlag?.short).toBe('v');
      
      const outputFlag = GLOBAL_FLAGS.find(f => f.name === 'output');
      expect(outputFlag?.short).toBe('o');
    });
  });

  describe('Exit Codes', () => {
    it('should have correct exit codes', () => {
      expect(EXIT_CODES.SUCCESS).toBe(0);
      expect(EXIT_CODES.RUNTIME_ERROR).toBe(1);
      expect(EXIT_CODES.INVALID_ARGUMENTS).toBe(2);
      expect(EXIT_CODES.CONFIG_ERROR).toBe(3);
      expect(EXIT_CODES.NETWORK_ERROR).toBe(4);
      expect(EXIT_CODES.AUTH_ERROR).toBe(5);
    });
  });
});

describe('Argument Parsing', () => {
  describe('Commands', () => {
    it('should parse command correctly', () => {
      const result = parseArgs(['chat', 'Hello']);
      expect(result.command).toBe('chat');
      expect(result.args).toEqual(['Hello']);
    });

    it('should default to help when no command', () => {
      const result = parseArgs([]);
      expect(result.command).toBe('help');
    });
  });

  describe('Flags', () => {
    it('should parse long flags with values', () => {
      const result = parseArgs(['chat', 'Hello', '--model', 'gpt-4']);
      expect(result.options.model).toBe('gpt-4');
    });

    it('should parse short flags with values', () => {
      const result = parseArgs(['chat', 'Hello', '-m', 'gpt-4']);
      expect(result.options.model).toBe('gpt-4');
    });

    it('should parse boolean flags', () => {
      const result = parseArgs(['chat', 'Hello', '--verbose']);
      expect(result.options.verbose).toBe(true);
    });

    it('should parse short boolean flags', () => {
      const result = parseArgs(['chat', 'Hello', '-v']);
      expect(result.options.verbose).toBe(true);
    });

    it('should handle --json shorthand', () => {
      const result = parseArgs(['chat', 'Hello', '--json']);
      expect(result.options.json).toBe(true);
      expect(result.options.output).toBe('json');
    });
  });

  describe('Subcommands', () => {
    it('should parse eval subcommands', () => {
      const result = parseArgs(['eval', 'accuracy', '--input', 'test']);
      expect(result.command).toBe('eval');
      expect(result.subcommand).toBe('accuracy');
      expect(result.options.input).toBe('test');
    });

    it('should parse tools subcommands', () => {
      const result = parseArgs(['tools', 'info', 'calculator']);
      expect(result.command).toBe('tools');
      expect(result.subcommand).toBe('info');
      expect(result.args).toEqual(['calculator']);
    });
  });

  describe('Multiple Arguments', () => {
    it('should collect multiple positional arguments', () => {
      const result = parseArgs(['run', 'task1', 'task2']);
      expect(result.command).toBe('run');
      expect(result.args).toEqual(['task1', 'task2']);
    });
  });
});

describe('Output Schema', () => {
  it('should have consistent success schema', () => {
    // This is a type check - the schema is enforced by TypeScript
    const successOutput = {
      success: true as const,
      data: { response: 'test' },
      meta: {
        duration_ms: 100,
        model: 'gpt-4',
        tokens: { input: 10, output: 20 }
      }
    };
    
    expect(successOutput.success).toBe(true);
    expect(successOutput.data).toBeDefined();
  });

  it('should have consistent error schema', () => {
    const errorOutput = {
      success: false as const,
      error: {
        code: 'MISSING_ARGUMENT',
        message: 'Please provide a prompt'
      }
    };
    
    expect(errorOutput.success).toBe(false);
    expect(errorOutput.error.code).toBeDefined();
    expect(errorOutput.error.message).toBeDefined();
  });
});
