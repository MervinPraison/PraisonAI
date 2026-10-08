/**
 * Regression tests for the shared CLI output helpers used by ~38 commands:
 * printPlainHelp, printCommandHelp (output/help.ts) and handleCommandError (output/errors.ts).
 * These lock the JSON shapes, exact plain-text spacing/widths, description handling and
 * error exit behaviour so a later change to one helper cannot silently alter every command.
 */

import { printPlainHelp, printCommandHelp } from '../../../src/cli/output/help';
import { handleCommandError, ERROR_CODES } from '../../../src/cli/output/errors';

function captureLog(): { lines: string[]; restore: () => void } {
  const lines: string[] = [];
  const log = jest.spyOn(console, 'log').mockImplementation((...args: unknown[]) => {
    lines.push(args.map((a) => String(a)).join(' '));
  });
  return { lines, restore: () => log.mockRestore() };
}

describe('printPlainHelp', () => {
  const help = {
    subcommands: { set: 'Set a value', list: 'List all' },
    examples: ['cmd set k v', 'cmd list'],
  };

  it('prints the raw help object as 2-space JSON when isJson is true', () => {
    const { lines, restore } = captureLog();
    printPlainHelp(true, help, 'Heading', [{ label: 'Subcommands:', entries: help.subcommands }]);
    restore();
    expect(lines).toEqual([JSON.stringify(help, null, 2)]);
  });

  it('prints heading then titled sections with default width 12 and literal items', () => {
    const { lines, restore } = captureLog();
    printPlainHelp(false, help, 'My Command', [
      { label: 'Subcommands:', entries: help.subcommands },
      { label: 'Examples:', items: help.examples },
    ]);
    restore();
    expect(lines).toEqual([
      'My Command',
      '\nSubcommands:',
      `  ${'set'.padEnd(12)} Set a value`,
      `  ${'list'.padEnd(12)} List all`,
      '\nExamples:',
      '  cmd set k v',
      '  cmd list',
    ]);
  });

  it('honours a custom column width override', () => {
    const { lines, restore } = captureLog();
    printPlainHelp(false, help, 'H', [{ label: 'Modes:', entries: { auto: 'Auto' }, width: 6 }]);
    restore();
    expect(lines).toContain(`  ${'auto'.padEnd(6)} Auto`);
  });
});

describe('printCommandHelp', () => {
  const help = {
    description: 'Does things',
    subcommands: [{ name: 'run', description: 'Run it' }],
    flags: [{ name: '--json', description: 'JSON output' }],
  };

  it('emits formatSuccess JSON when outputFormat is json', async () => {
    const { lines, restore } = captureLog();
    await printCommandHelp('json', help, { heading: 'X' });
    restore();
    expect(JSON.parse(lines.join('\n'))).toEqual({ success: true, data: help });
  });

  it('renders pretty layout: subcommands at width 25, flags at width 20, dim examples', async () => {
    const { lines, restore } = captureLog();
    await printCommandHelp('text', help, { heading: 'X Command', examples: ['cmd run'] });
    restore();
    expect(lines).toContain(`  ${'run'.padEnd(25)} Run it`);
    expect(lines).toContain(`  ${'--json'.padEnd(20)} JSON output`);
    expect(lines).toContain('Examples:');
    expect(lines).toContain('  cmd run');
  });

  it('prints help.description followed by a blank line when no override is given', async () => {
    const { lines, restore } = captureLog();
    await printCommandHelp('text', help, { heading: 'X' });
    restore();
    const idx = lines.indexOf('Does things');
    expect(idx).toBeGreaterThanOrEqual(0);
    expect(lines[idx + 1]).toBe('');
  });

  it('uses a literal description override without the extra blank line', async () => {
    const { lines, restore } = captureLog();
    await printCommandHelp('text', help, { heading: 'X', description: 'Does things\n' });
    restore();
    expect(lines).toContain('Does things\n');
    expect(lines).not.toContain('Does things');
  });

  it('omits the Flags section when no flags are present', async () => {
    const { lines, restore } = captureLog();
    await printCommandHelp('text', { description: 'd', subcommands: [] }, { heading: 'X' });
    restore();
    expect(lines).not.toContain('Flags:');
  });
});

describe('handleCommandError', () => {
  let exitSpy: jest.SpyInstance;

  beforeEach(() => {
    exitSpy = jest
      .spyOn(process, 'exit')
      .mockImplementation(((code?: number) => undefined as never) as never);
  });
  afterEach(() => exitSpy.mockRestore());

  it('outputs an UNKNOWN error JSON object and exits with the runtime code', async () => {
    const { lines, restore } = captureLog();
    await handleCommandError('json', new Error('boom'));
    restore();
    expect(JSON.parse(lines.join('\n'))).toEqual({
      success: false,
      error: { code: ERROR_CODES.UNKNOWN, message: 'boom' },
    });
    expect(exitSpy).toHaveBeenCalledWith(1);
  });

  it('coerces non-Error values to a string message', async () => {
    const errSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined);
    await handleCommandError('text', 'plain failure');
    expect(errSpy).toHaveBeenCalledWith(expect.stringContaining('plain failure'));
    expect(exitSpy).toHaveBeenCalledWith(1);
    errSpy.mockRestore();
  });
});
