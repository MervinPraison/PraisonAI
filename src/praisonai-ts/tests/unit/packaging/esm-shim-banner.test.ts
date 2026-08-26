/**
 * esm-shim createRequire banner — false-positive regression tests.
 *
 * The shim decides whether an emitted ESM file needs a `createRequire` banner
 * (plus hard imports of `module`, `url` and `path`). The original detector tested
 * for the *word* `require` anywhere in the file, so an error string like
 * "Zod schemas require zod-to-json-schema" gave 24/288 ESM files three Node
 * builtin imports that do not exist in the source — making the built ESM strictly
 * worse to bundle than the TypeScript it came from.
 *
 * These tests assert on the EMITTED output of the shim's own transform
 * (`applyBanner`), not on the regex, so a future regex tweak that reintroduces the
 * bug fails here rather than silently only at bundle time.
 */

// eslint-disable-next-line @typescript-eslint/no-var-requires
const { applyBanner, needsCjsBanner } = require('../../../scripts/esm-shim.js');

const BANNER_MARKER = '__praisonCreateRequire(import.meta.url)';

function hasBanner(code: string): boolean {
  return code.includes(BANNER_MARKER);
}

describe('esm-shim createRequire banner detection', () => {
  it('does NOT banner a file whose only "require" is inside a string literal', () => {
    const code = 'const msg = "this require is a string";\n';
    expect(needsCjsBanner(code)).toBe(false);
    const out = applyBanner(code);
    expect(hasBanner(out)).toBe(false);
    // Output is untouched: no new module/url/path imports were injected.
    expect(out).toBe(code);
  });

  it('does NOT banner the real-world error-message case from the issue', () => {
    // dist/esm/llm/providers/openai.js was banner-ed solely because of this string.
    const code =
      'export function toJsonSchema(schema) {\n' +
      '  throw new Error("Zod schemas require zod-to-json-schema");\n' +
      '}\n';
    expect(needsCjsBanner(code)).toBe(false);
    expect(hasBanner(applyBanner(code))).toBe(false);
  });

  it('does NOT banner "require" inside line or block comments', () => {
    const line = '// we require nothing here\nexport const x = 1;\n';
    const block = '/* this may require attention */\nexport const y = 2;\n';
    expect(needsCjsBanner(line)).toBe(false);
    expect(needsCjsBanner(block)).toBe(false);
    expect(hasBanner(applyBanner(line))).toBe(false);
    expect(hasBanner(applyBanner(block))).toBe(false);
  });

  it('does NOT banner property accesses that merely spell __dirname/require', () => {
    const code =
      'const opts = { require: true };\n' +
      'foo.require = 1;\n' +
      'const p = ctx.__dirname;\n';
    expect(needsCjsBanner(code)).toBe(false);
    expect(hasBanner(applyBanner(code))).toBe(false);
  });

  it('DOES banner a file that genuinely calls require(...)', () => {
    const code = 'const fs = require("fs");\n';
    expect(needsCjsBanner(code)).toBe(true);
    expect(hasBanner(applyBanner(code))).toBe(true);
  });

  it('DOES banner genuine __dirname / __filename identifier usage', () => {
    expect(needsCjsBanner('const d = __dirname;\n')).toBe(true);
    expect(needsCjsBanner('console.log(__filename);\n')).toBe(true);
  });

  it('DOES banner module.exports and require.main === module usage', () => {
    expect(needsCjsBanner('module.exports = foo;\n')).toBe(true);
    expect(needsCjsBanner('if (require.main === module) run();\n')).toBe(true);
  });

  it('does NOT banner a require() call that lives only inside a template literal', () => {
    const code = 'const help = `run require("x") to load`;\n';
    expect(needsCjsBanner(code)).toBe(false);
    expect(hasBanner(applyBanner(code))).toBe(false);
  });
});
