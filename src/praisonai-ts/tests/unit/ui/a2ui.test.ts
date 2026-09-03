/**
 * Parity tests for src/ui/a2ui.ts against praisonaiagents/ui/a2ui/__init__.py.
 */

import { describe, it, expect, afterEach } from '@jest/globals';
import {
  A2UI,
  A2UI_MIME_TYPE,
  A2UINotInstalledError,
  createA2uiPart,
  isA2uiPart,
  parseA2uiResponse,
  getSchemaManager,
  generateA2uiSystemPrompt,
  type A2UIAdapter,
} from '../../../src/ui/a2ui';

function recordingAdapter() {
  const calls: Array<[string, unknown[]]> = [];
  const adapter: A2UIAdapter = {
    createA2uiPart: (...args) => {
      calls.push(['createA2uiPart', args]);
      return { part: args[0] };
    },
    isA2uiPart: (...args) => {
      calls.push(['isA2uiPart', args]);
      return true;
    },
    parseA2uiResponse: (...args) => {
      calls.push(['parseA2uiResponse', args]);
      return ['p1'];
    },
    getSchemaManager: (...args) => {
      calls.push(['getSchemaManager', args]);
      return { manager: true };
    },
    generateA2uiSystemPrompt: (...args) => {
      calls.push(['generateA2uiSystemPrompt', args]);
      return 'PROMPT';
    },
  };
  return { adapter, calls };
}

describe('A2UI facade', () => {
  afterEach(() => A2UI.useAdapter(null));

  it('exposes the Python MIME type', () => {
    expect(A2UI_MIME_TYPE).toBe('application/json+a2ui');
  });

  it('every method throws a clear "no A2UI adapter installed" error without an adapter', () => {
    expect(A2UI.hasAdapter()).toBe(false);
    const calls: Array<() => unknown> = [
      () => A2UI.createPart({}),
      () => A2UI.isPart({}),
      () => A2UI.parseResponse('x'),
      () => A2UI.schemaManager(),
      () => A2UI.systemPrompt('role'),
      () => createA2uiPart({}),
      () => isA2uiPart({}),
      () => parseA2uiResponse('x'),
      () => getSchemaManager(),
      () => generateA2uiSystemPrompt('role'),
    ];
    for (const call of calls) {
      expect(call).toThrow(A2UINotInstalledError);
      expect(call).toThrow('no A2UI adapter installed');
    }
    expect(() => A2UI.createPart({})).toThrow('A2UI.createPart');
  });

  it('delegates to the installed adapter and applies the Python defaults', () => {
    const { adapter, calls } = recordingAdapter();
    A2UI.useAdapter(adapter);
    expect(A2UI.hasAdapter()).toBe(true);

    expect(A2UI.createPart({ createSurface: {} })).toEqual({ part: { createSurface: {} } });
    expect(A2UI.isPart('p')).toBe(true);
    expect(A2UI.parseResponse('text')).toEqual(['p1']);
    expect(A2UI.schemaManager()).toEqual({ manager: true });
    expect(A2UI.systemPrompt('You are helpful.')).toBe('PROMPT');
    A2UI.systemPrompt('r', 'w', 'u', { version: '1.0', includeSchema: false });

    expect(calls).toEqual([
      ['createA2uiPart', [{ createSurface: {} }]],
      ['isA2uiPart', ['p']],
      ['parseA2uiResponse', ['text']],
      ['getSchemaManager', ['0.9', null, false]],
      ['generateA2uiSystemPrompt', ['You are helpful.', '', '', { version: '0.9', includeSchema: true, includeExamples: true }]],
      ['generateA2uiSystemPrompt', ['r', 'w', 'u', { version: '1.0', includeSchema: false, includeExamples: true }]],
    ]);
  });

  it('module-level functions are twins of the static methods', () => {
    const { adapter, calls } = recordingAdapter();
    A2UI.useAdapter(adapter);
    getSchemaManager('0.8', ['cat'], true);
    generateA2uiSystemPrompt('r');
    expect(calls[0]).toEqual(['getSchemaManager', ['0.8', ['cat'], true]]);
    expect(calls[1][0]).toBe('generateA2uiSystemPrompt');
  });

  it('control: removing the adapter restores the throwing behaviour', () => {
    A2UI.useAdapter(recordingAdapter().adapter);
    A2UI.useAdapter(null);
    expect(() => A2UI.isPart({})).toThrow(A2UINotInstalledError);
  });
});
