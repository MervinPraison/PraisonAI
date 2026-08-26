/**
 * esm-shim CJS banner detection — regression tests.
 *
 * The shim prepends a createRequire(import.meta.url) banner (importing the
 * Node builtins `module`, `url`, `path`) to any emitted ESM file that still
 * relies on CommonJS globals. The old detector tested `/\brequire\b/` against
 * the raw file text, so the *word* `require` inside a string literal or comment
 * falsely triggered the banner — coupling ESM output to Node builtins that the
 * source never used (e.g. openai.js bannered purely by an error message).
 *
 * These tests assert on the actual emit transform (applyBanner / needsCjsBanner
 * exported by scripts/esm-shim.js), in BOTH directions:
 *   - a `require`/`__dirname`/`__filename` that appears only inside strings or
 *     comments must NOT receive the banner, and
 *   - a genuine require(...) call / CJS global must still receive it.
 */

// eslint-disable-next-line @typescript-eslint/no-var-requires
const { applyBanner, needsCjsBanner, CJS_BANNER } = require('../../../scripts/esm-shim.js');

function bannered(code: string): boolean {
  return needsCjsBanner(code);
}

describe('esm-shim needsCjsBanner', () => {
  it('does not banner the exact string-literal case from the issue', () => {
    const code = 'const msg = "this require is a string";\n';
    expect(bannered(code)).toBe(false);
  });

  it('does not banner the openai.js error-message case', () => {
    const code =
      'throw new Error("Zod schemas require zod-to-json-schema");\n';
    expect(bannered(code)).toBe(false);
  });

  it('does not banner require inside a template literal', () => {
    const code = 'const t = `you must require the module`;\n';
    expect(bannered(code)).toBe(false);
  });

  it('does not banner require / __dirname / __filename inside comments', () => {
    const code = [
      '// require(x) here is just a comment about __dirname and __filename',
      '/* module.exports style note, require() mentioned */',
      'export const x = 1;',
    ].join('\n');
    expect(bannered(code)).toBe(false);
  });

  it('does not banner a property access named require', () => {
    const code = 'obj.require(); a.__dirname; b.__filename;\n';
    expect(bannered(code)).toBe(false);
  });

  it('DOES banner a genuine require(...) call', () => {
    const code = "const fs = require('fs');\n";
    expect(bannered(code)).toBe(true);
  });

  it('DOES banner genuine __dirname / __filename usage', () => {
    expect(bannered('const p = __dirname + "/x";\n')).toBe(true);
    expect(bannered('console.log(__filename);\n')).toBe(true);
  });

  it('DOES banner module.exports and require.main === module', () => {
    expect(bannered('module.exports = {};\n')).toBe(true);
    expect(bannered('if (require.main === module) {}\n')).toBe(true);
  });
});

describe('esm-shim applyBanner', () => {
  it('leaves string-only require files untouched (no Node builtins injected)', () => {
    const code = 'const msg = "this require is a string";\n';
    const out = applyBanner(code);
    expect(out).toBe(code);
    expect(out).not.toContain("from 'module'");
    expect(out).not.toContain("from 'url'");
  });

  it('prepends the banner to files with a real require() call', () => {
    const code = "const fs = require('fs');\n";
    const out = applyBanner(code);
    expect(out.startsWith(CJS_BANNER)).toBe(true);
  });
});
