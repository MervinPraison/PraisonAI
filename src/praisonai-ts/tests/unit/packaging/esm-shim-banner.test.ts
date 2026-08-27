/**
 * esm-shim createRequire banner — detection regression tests.
 *
 * The shim decides whether an emitted ESM file needs a `createRequire` banner
 * (plus hard imports of `module`, `url` and `path`). The original detector tested
 * for the *word* `require` anywhere in the file, so an error string like
 * "Zod schemas require zod-to-json-schema" gave 24/288 ESM files three Node
 * builtin imports that do not exist in the source — making the built ESM strictly
 * worse to bundle than the TypeScript it came from.
 *
 * These tests assert on the actual emit transform (applyBanner / needsCjsBanner
 * exported by scripts/esm-shim.js), in BOTH directions:
 *   - a `require`/`__dirname`/`__filename` that appears only inside strings or
 *     comments must NOT receive the banner, and
 *   - a genuine require(...) call / CJS global (including one nested inside a
 *     template-literal `${...}` interpolation) MUST still receive it.
 */

// eslint-disable-next-line @typescript-eslint/no-var-requires
const { applyBanner, needsCjsBanner, CJS_BANNER } = require('../../../scripts/esm-shim.js');

// What the banner is FOR, rather than how it happens to be spelled. The old
// marker was `__praisonCreateRequire(import.meta.url)` -- an internal
// identifier -- so renaming it broke four tests that were not about naming.
// A banner that stopped defining `require` would still fail these.
const BANNER_MARKER = 'const require =';

function hasBanner(code: string): boolean {
  return code.includes(BANNER_MARKER);
}

describe('esm-shim needsCjsBanner (false positives)', () => {
  it('does NOT banner a file whose only "require" is inside a string literal', () => {
    const code = 'const msg = "this require is a string";\n';
    expect(needsCjsBanner(code)).toBe(false);
    const out = applyBanner(code);
    expect(hasBanner(out)).toBe(false);
    // Output is untouched: no new module/url/path imports were injected.
    expect(out).toBe(code);
  });

  it('does NOT banner the real-world openai.js error-message case', () => {
    // dist/esm/llm/providers/openai.js was banner-ed solely because of this string.
    const code =
      'export function toJsonSchema(schema) {\n' +
      '  throw new Error("Zod schemas require zod-to-json-schema");\n' +
      '}\n';
    expect(needsCjsBanner(code)).toBe(false);
    expect(hasBanner(applyBanner(code))).toBe(false);
  });

  it('does NOT banner require / __dirname / __filename inside comments', () => {
    const line = '// require(x) here is a comment about __dirname and __filename\n';
    const block = '/* module.exports style note, require() mentioned */\n';
    expect(needsCjsBanner(line)).toBe(false);
    expect(needsCjsBanner(block)).toBe(false);
    expect(hasBanner(applyBanner(line))).toBe(false);
    expect(hasBanner(applyBanner(block))).toBe(false);
  });

  it('does NOT banner property accesses that merely spell __dirname/require', () => {
    const code =
      'const opts = { require: true };\n' +
      'foo.require = 1;\n' +
      'obj.require(); a.__dirname; b.__filename;\n' +
      'const p = ctx.__dirname;\n';
    expect(needsCjsBanner(code)).toBe(false);
    expect(hasBanner(applyBanner(code))).toBe(false);
  });

  it('does NOT banner require text inside a template literal', () => {
    const code = 'const help = `run require("x") to load the module`;\n';
    expect(needsCjsBanner(code)).toBe(false);
    expect(hasBanner(applyBanner(code))).toBe(false);
  });
});

describe('esm-shim needsCjsBanner (genuine CJS usage)', () => {
  it('DOES banner a file that genuinely calls require(...)', () => {
    const code = 'const fs = require("fs");\n';
    expect(needsCjsBanner(code)).toBe(true);
    expect(hasBanner(applyBanner(code))).toBe(true);
  });

  it('DOES banner genuine __dirname / __filename identifier usage', () => {
    expect(needsCjsBanner('const d = __dirname + "/x";\n')).toBe(true);
    expect(needsCjsBanner('console.log(__filename);\n')).toBe(true);
  });

  it('DOES banner module.exports and require.main === module usage', () => {
    expect(needsCjsBanner('module.exports = foo;\n')).toBe(true);
    expect(needsCjsBanner('if (require.main === module) run();\n')).toBe(true);
  });

  it('DOES banner a real require(...) call inside a template interpolation', () => {
    // The literal text is blanked, but ${...} is executable code: a genuine
    // require here would throw a ReferenceError at runtime without the banner.
    const code = 'const v = `value=${require("fs").readFileSync("x")}`;\n';
    expect(needsCjsBanner(code)).toBe(true);
    expect(hasBanner(applyBanner(code))).toBe(true);
  });

  it('DOES banner __dirname used inside a template interpolation', () => {
    const code = 'const p = `${__dirname}/data`;\n';
    expect(needsCjsBanner(code)).toBe(true);
    expect(hasBanner(applyBanner(code))).toBe(true);
  });

  it('does NOT banner a template whose interpolation is only a string mentioning require', () => {
    const code = 'const t = `${"please require nothing"}`;\n';
    expect(needsCjsBanner(code)).toBe(false);
    expect(hasBanner(applyBanner(code))).toBe(false);
  });

  it('DOES banner require after a regex literal containing } inside an interpolation', () => {
    // A `}` in the regex character class must not close the interpolation early
    // and hide the genuine require(...) that follows it.
    const code =
      'const v = `x=${/[}]/.test(s) ? require("fs").readFileSync("a") : 0}`;\n';
    expect(needsCjsBanner(code)).toBe(true);
    expect(hasBanner(applyBanner(code))).toBe(true);
  });

  it('DOES banner require after a comment containing } inside an interpolation', () => {
    const line =
      'const v = `x=${(() => { // note }\n return require("fs"); })()}`;\n';
    const block =
      'const v = `x=${(function(){ /* } */ return require("fs"); })()}`;\n';
    expect(needsCjsBanner(line)).toBe(true);
    expect(needsCjsBanner(block)).toBe(true);
  });

  it('does NOT confuse a division operator inside an interpolation for a regex', () => {
    const code = 'const v = `x=${a / b + c}`;\n';
    expect(needsCjsBanner(code)).toBe(false);
    expect(hasBanner(applyBanner(code))).toBe(false);
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
