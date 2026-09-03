/**
 * getAISDKVersion reads ai/package.json through a dynamic import (with a JSON
 * import attribute for the ESM build) instead of a bare require(). Under the
 * CommonJS build ts-jest runs here, tsc lowers that import() to require(), so
 * this pins that the lowered form still finds the real installed version
 * rather than falling back to 'installed'.
 */

import { getAISDKVersion } from '../../../../src/llm/providers/ai-sdk';

describe('getAISDKVersion', () => {
  it('returns the installed ai package version', async () => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const expected = require('ai/package.json').version as string;
    expect(typeof expected).toBe('string');
    await expect(getAISDKVersion()).resolves.toBe(expected);
  });
});
