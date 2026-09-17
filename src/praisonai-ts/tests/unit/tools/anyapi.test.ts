/**
 * AnyAPI built-in tool tests
 *
 * Mocks the optional @getanyapi/sdk package (it is not installed) and exercises
 * the three tools' metadata, SDK mapping, run normalization, and the custom
 * missing-environment / missing-dependency errors.
 */

import { describe, it, expect, beforeEach, afterEach, jest } from '@jest/globals';

const searchMock = jest.fn() as jest.Mock<any>;
const describeMock = jest.fn() as jest.Mock<any>;
const runMock = jest.fn() as jest.Mock<any>;

class MockAnyAPI {
  constructor(public options: { apiKey: string }) {}
  search = searchMock;
  describe = describeMock;
  run = runMock;
}

jest.mock('@getanyapi/sdk', () => ({ AnyAPI: MockAnyAPI }), { virtual: true });

import {
  anyapiSearchApis,
  anyapiGetApi,
  anyapiRunApi,
  ANYAPI_METADATA,
} from '../../../src/tools/builtins/anyapi';
import { MissingEnvVarError } from '../../../src/tools/registry/types';

describe('AnyAPI built-in tools', () => {
  const originalKey = process.env.ANYAPI_API_KEY;

  beforeEach(() => {
    process.env.ANYAPI_API_KEY = 'test-key';
    searchMock.mockReset();
    describeMock.mockReset();
    runMock.mockReset();
  });

  afterEach(() => {
    if (originalKey === undefined) {
      delete process.env.ANYAPI_API_KEY;
    } else {
      process.env.ANYAPI_API_KEY = originalKey;
    }
  });

  it('exposes stable metadata', () => {
    expect(ANYAPI_METADATA.id).toBe('anyapi');
    expect(ANYAPI_METADATA.requiredEnv).toContain('ANYAPI_API_KEY');
    expect(ANYAPI_METADATA.packageName).toBe('@getanyapi/sdk');
  });

  it('maps search hits to typed summaries', async () => {
    searchMock.mockResolvedValue({
      results: [
        {
          slug: 'instagram.profile',
          name: 'Instagram Profile',
          category: 'social',
          description: 'Fetch a profile',
          pricing: { from: { maxUsd: 0.01 }, failoverMaxUsd: 0.02 },
          relevance: 0.9,
        },
      ],
      total: 1,
    });

    const tool = anyapiSearchApis({ category: 'social', limit: 5 });
    const result = await tool.execute({ query: 'instagram profile' });

    expect(searchMock).toHaveBeenCalledWith({
      query: 'instagram profile',
      category: 'social',
      limit: 5,
    });
    expect(result.total).toBe(1);
    expect(result.apis[0]).toEqual({
      slug: 'instagram.profile',
      name: 'Instagram Profile',
      category: 'social',
      description: 'Fetch a profile',
      maxCostUsd: 0.01,
      failoverMaxUsd: 0.02,
      relevance: 0.9,
    });
  });

  it('maps describe entries including schemas', async () => {
    describeMock.mockResolvedValue({
      slug: 'instagram.profile',
      name: 'Instagram Profile',
      category: 'social',
      description: 'Fetch a profile',
      pricing: { from: { maxUsd: 0.01 }, failoverMaxUsd: 0.02 },
      inputSchema: { type: 'object' },
      outputSchema: { type: 'object' },
    });

    const tool = anyapiGetApi();
    const result = await tool.execute({ slug: 'instagram.profile' });

    expect(describeMock).toHaveBeenCalledWith('instagram.profile');
    expect(result.maxCostUsd).toBe(0.01);
    expect(result.inputSchema).toEqual({ type: 'object' });
  });

  it('normalizes a { found, data } envelope on run', async () => {
    runMock.mockResolvedValue({
      output: { found: true, data: { handle: 'praison' } },
      costUsd: 0.01,
      items: 1,
    });

    const tool = anyapiRunApi({ maxItems: 10, fields: ['handle'] });
    const result = await tool.execute({ slug: 'instagram.profile', input: { user: 'praison' } });

    expect(runMock).toHaveBeenCalledWith(
      'instagram.profile',
      { user: 'praison' },
      { fields: ['handle'], maxItems: 10 }
    );
    expect(result).toEqual({
      data: { handle: 'praison' },
      found: true,
      costUsd: 0.01,
      items: 1,
    });
  });

  it('preserves a direct object that happens to carry a non-boolean found field', async () => {
    const direct = { found: 3, results: ['a', 'b'] };
    runMock.mockResolvedValue({ output: direct, costUsd: 0.02, items: 2 });

    const tool = anyapiRunApi();
    const result = await tool.execute({ slug: 'demo.api' });

    expect(result.found).toBe(true);
    expect(result.data).toEqual(direct);
  });

  it('reports found=false for a null direct output', async () => {
    runMock.mockResolvedValue({ output: null, costUsd: 0, items: 0 });

    const tool = anyapiRunApi();
    const result = await tool.execute({ slug: 'demo.api' });

    expect(result.found).toBe(false);
    expect(result.data).toBeNull();
  });

  it('throws MissingEnvVarError when ANYAPI_API_KEY is absent', async () => {
    delete process.env.ANYAPI_API_KEY;
    const tool = anyapiSearchApis();
    await expect(tool.execute({ query: 'x' })).rejects.toBeInstanceOf(MissingEnvVarError);
  });
});
