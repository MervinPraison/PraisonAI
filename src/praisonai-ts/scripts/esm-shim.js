// Post-processes the ESM build in dist/esm so it is valid native ESM:
//   1. Rewrites extensionless relative specifiers (import/export ... from './x')
//      to './x.js' or './x/index.js' as required by Node's ESM resolver.
//   2. Prepends a createRequire(import.meta.url) banner (plus __filename/__dirname
//      shims) to any emitted file that still relies on CommonJS globals, so the
//      rare require()/__dirname site keeps working under ESM.
//   3. Writes dist/esm/package.json with { "type": "module" } so Node treats the
//      directory as ESM regardless of the root package.json "type".
// Source files are never touched; the CJS build in dist/ is unaffected.

const fs = require('fs');
const path = require('path');

const DIST_DIR = path.join(__dirname, '..', 'dist');
const ESM_DIR = path.join(DIST_DIR, 'esm');

function walk(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...walk(full));
    } else if (entry.isFile() && full.endsWith('.js')) {
      out.push(full);
    }
  }
  return out;
}

function resolveSpecifier(fileDir, spec) {
  // Only rewrite relative specifiers that lack an extension.
  if (!spec.startsWith('./') && !spec.startsWith('../')) return null;
  if (/\.[a-zA-Z0-9]+$/.test(spec)) return null; // already has an extension

  const target = path.resolve(fileDir, spec);
  try {
    if (fs.existsSync(target) && fs.statSync(target).isDirectory()) {
      return spec.replace(/\/?$/, '') + '/index.js';
    }
  } catch {
    // ignore
  }
  return spec + '.js';
}

function rewriteSpecifiers(code, fileDir) {
  // Matches static import/export ... from '...' and dynamic import('...').
  const patterns = [
    /((?:import|export)[\s\S]*?from\s*)(['"])(\.[^'"]+)\2/g,
    /(\bimport\s*\(\s*)(['"])(\.[^'"]+)\2(\s*\))/g,
  ];
  let out = code;
  // from '...'
  out = out.replace(patterns[0], (match, pre, quote, spec) => {
    const resolved = resolveSpecifier(fileDir, spec);
    return resolved ? `${pre}${quote}${resolved}${quote}` : match;
  });
  // import('...')
  out = out.replace(patterns[1], (match, pre, quote, spec, post) => {
    const resolved = resolveSpecifier(fileDir, spec);
    return resolved ? `${pre}${quote}${resolved}${quote}${post}` : match;
  });
  return out;
}

function resolveCjsTarget(fileDir, spec) {
  // Every ESM file in dist/esm has a CommonJS twin at the mirrored path in dist/.
  // Resolve the specifier from the TWIN's directory so it lands wherever the CJS
  // build's require would (internal module, package.json at the root, etc.), and
  // return that concrete file so createRequire loads real CommonJS/JSON.
  const relDir = path.relative(ESM_DIR, fileDir);
  // Files outside dist/esm are not part of the ESM build; leave them alone.
  if (relDir.startsWith('..') || path.isAbsolute(relDir)) return null;
  const cjsDir = path.join(DIST_DIR, relDir);
  const target = path.resolve(cjsDir, spec);
  if (/\.[a-zA-Z0-9]+$/.test(spec)) {
    return fs.existsSync(target) ? target : null;
  }
  if (fs.existsSync(target + '.js')) return target + '.js';
  const asIndex = path.join(target, 'index.js');
  if (fs.existsSync(asIndex)) return asIndex;
  return null;
}

function rewriteRelativeRequires(code, fileDir) {
  // `tsc --module esnext` leaves explicit require('./x') calls untouched. Under
  // native ESM (dist/esm is type:module) those would resolve to ESM siblings and
  // throw ERR_REQUIRE_ESM on Node <22. Repoint each internal relative require to
  // the mirrored CommonJS file in dist/ so createRequire loads real CJS.
  return code.replace(
    /(\brequire\s*\(\s*)(['"])(\.[^'"]+)\2(\s*\))/g,
    (match, pre, quote, spec, post) => {
      const cjsAbs = resolveCjsTarget(fileDir, spec);
      if (!cjsAbs) return match;
      let relToCjs = path.relative(fileDir, cjsAbs).split(path.sep).join('/');
      if (!relToCjs.startsWith('.')) relToCjs = './' + relToCjs;
      return `${pre}${quote}${relToCjs}${quote}${post}`;
    }
  );
}

// STATIC imports of 'module', 'url' and 'path' were the previous form, and they
// were import-time fatal for a browser: a bundler must resolve a static import
// before any code runs, so three files whose `require()` calls were all LAZY
// turned into three unconditional Node dependencies. dist/esm/mobile.js -- what
// `praisonai/mobile` actually resolves to -- failed with ten unresolved
// builtins while the TypeScript source it was built from passed cleanly.
//
// A guarded top-level await keeps Node byte-identical in behaviour and lets a
// browser bundle load. The dynamic import is lazy, so a bundler defers it
// rather than failing on it; when it does fail at runtime (there is no 'module'
// in a browser) the catch installs a `require` that throws only if a lazy
// provider path is actually taken -- which on a phone it is not.
const CJS_BANNER = [
  'const [__praisonMod, __praisonUrl, __praisonPath] = await Promise.all([',
  "  import('module').catch(() => null),",
  "  import('url').catch(() => null),",
  "  import('path').catch(() => null),",
  ']);',
  'const require = __praisonMod',
  '  ? __praisonMod.createRequire(import.meta.url)',
  "  : (id) => { throw new Error('require(' + id + ') is unavailable outside Node'); };",
  "const __filename = __praisonUrl ? __praisonUrl.fileURLToPath(import.meta.url) : '';",
  "const __dirname = __praisonPath && __filename ? __praisonPath.dirname(__filename) : '';",
  // In ESM there is no CommonJS module object. Provide a stub so patterns like
  // `require.main === module` compile and evaluate to false (this file is not a
  // CLI entry point when imported), and `module.exports = ...` remains harmless.
  'const module = { exports: {} };',
].join('\n');

function stripStringsAndComments(code) {
  // Blank out comments and string/template literals so the CJS-usage detectors
  // below only ever see real code. `/\brequire\b/` on raw text matched the word
  // inside error messages like "Zod schemas require zod-to-json-schema", giving
  // 24/288 ESM files a createRequire banner (and hard imports of module/url/path)
  // they never needed. Every blanked token is replaced with same-length
  // whitespace so surviving offsets stay meaningful and newlines are preserved.
  //
  // Template literals are special: the raw text between backticks is blanked,
  // but each `${...}` interpolation is real, executable code and is recursively
  // stripped and kept — otherwise a genuine `require(...)` (or __dirname) inside
  // an interpolation would be hidden and the file would emit without its banner,
  // failing at runtime with a ReferenceError.
  let out = '';
  let i = 0;
  const n = code.length;
  const blank = (s) => s.replace(/[^\n]/g, ' ');
  while (i < n) {
    const ch = code[i];
    const next = code[i + 1];
    // Line comment
    if (ch === '/' && next === '/') {
      let j = i + 2;
      while (j < n && code[j] !== '\n') j++;
      out += blank(code.slice(i, j));
      i = j;
      continue;
    }
    // Block comment
    if (ch === '/' && next === '*') {
      let j = i + 2;
      while (j < n && !(code[j] === '*' && code[j + 1] === '/')) j++;
      j = Math.min(j + 2, n);
      out += blank(code.slice(i, j));
      i = j;
      continue;
    }
    // Template literal: blank the literal text but preserve and recursively
    // strip each ${...} interpolation (which is executable code).
    if (ch === '`') {
      out += '`';
      let j = i + 1;
      while (j < n && code[j] !== '`') {
        if (code[j] === '\\') {
          out += '  ';
          j += 2;
          continue;
        }
        if (code[j] === '$' && code[j + 1] === '{') {
          // Consume a balanced ${ ... } interpolation, honouring nested braces,
          // strings and templates so we stop at the matching close brace.
          out += '${';
          let k = j + 2;
          let depth = 1;
          // Tracks the last significant (non-space) character consumed so we can
          // tell a regex literal (/.../ in expression position) from a division
          // operator (a / b). A regex may follow (, {, [, comma, operators or the
          // interpolation start; it never follows an identifier/number/), ], }.
          let prevSig = '';
          while (k < n && depth > 0) {
            const c = code[k];
            if (c === '\\') { k += 2; prevSig = ''; continue; }
            // Skip line/block comments so a `}` inside them can't close the
            // interpolation early and hide executable CJS that follows.
            if (c === '/' && code[k + 1] === '/') {
              k += 2;
              while (k < n && code[k] !== '\n') k++;
              continue;
            }
            if (c === '/' && code[k + 1] === '*') {
              k += 2;
              while (k < n && !(code[k] === '*' && code[k + 1] === '/')) k++;
              k = Math.min(k + 2, n);
              continue;
            }
            // Regex literal in expression position: its interior (including a `}`
            // in a character class) must not affect brace depth.
            if (c === '/' && (prevSig === '' || '([{,;:=!&|?+-*%^~<>'.includes(prevSig))) {
              k++;
              let inClass = false;
              while (k < n) {
                const rc = code[k];
                if (rc === '\\') { k += 2; continue; }
                if (rc === '[') { inClass = true; k++; continue; }
                if (rc === ']') { inClass = false; k++; continue; }
                if (rc === '/' && !inClass) { k++; break; }
                if (rc === '\n') break;
                k++;
              }
              prevSig = '/';
              continue;
            }
            if (c === '{') { depth++; k++; prevSig = '{'; continue; }
            if (c === '}') { depth--; k++; prevSig = '}'; continue; }
            if (c === '`' || c === '"' || c === "'") {
              // Skip nested string/template as-is; the recursive strip below
              // handles its interior.
              const q = c;
              k++;
              while (k < n) {
                if (code[k] === '\\') { k += 2; continue; }
                if (code[k] === q) { k++; break; }
                k++;
              }
              prevSig = q;
              continue;
            }
            if (c !== ' ' && c !== '\t' && c !== '\n' && c !== '\r') prevSig = c;
            k++;
          }
          // The interpolation body excludes the trailing '}'.
          const innerStart = j + 2;
          const innerEnd = k - 1;
          out += stripStringsAndComments(code.slice(innerStart, innerEnd)) + '}';
          j = k;
          continue;
        }
        out += code[j] === '\n' ? '\n' : ' ';
        j++;
      }
      if (j < n && code[j] === '`') {
        out += '`';
        j++;
      }
      i = j;
      continue;
    }
    // Ordinary quoted string literal.
    if (ch === '"' || ch === "'") {
      const quote = ch;
      let j = i + 1;
      while (j < n) {
        if (code[j] === '\\') {
          j += 2;
          continue;
        }
        if (code[j] === quote) {
          j++;
          break;
        }
        j++;
      }
      out += quote + blank(code.slice(i + 1, j - 1)) + (code[j - 1] === quote ? quote : '');
      i = j;
      continue;
    }
    out += ch;
    i++;
  }
  return out;
}

function needsCjsBanner(code) {
  // Test against code with strings/comments removed so a literal word like
  // "require" inside an error message never triggers the banner. Match real CJS
  // usage: require(...) call expressions and __dirname/__filename/module in
  // identifier positions (not property accesses like obj.require).
  const stripped = stripStringsAndComments(code);
  return (
    // Real require(...) call expression, not obj.require or a bare word.
    /(?:^|[^.\w$])require\s*\(/.test(stripped) ||
    // __dirname / __filename in identifier position (not a property access).
    /(?:^|[^.\w$])__dirname\b/.test(stripped) ||
    /(?:^|[^.\w$])__filename\b/.test(stripped) ||
    /\bmodule\.exports\b/.test(stripped) ||
    /===\s*module\b/.test(stripped) ||
    /\bmodule\s*===/.test(stripped)
  );
}

function applyBanner(code) {
  if (!needsCjsBanner(code)) return code;
  const shebangMatch = code.match(/^#![^\n]*\n/);
  if (shebangMatch) {
    const shebang = shebangMatch[0];
    return shebang + CJS_BANNER + '\n' + code.slice(shebang.length);
  }
  return CJS_BANNER + '\n' + code;
}

function main() {
  if (!fs.existsSync(ESM_DIR)) {
    throw new Error(`ESM output not found at ${ESM_DIR}. Run the ESM tsc build first.`);
  }

  const files = walk(ESM_DIR);
  for (const file of files) {
    const original = fs.readFileSync(file, 'utf8');
    const fileDir = path.dirname(file);
    let code = rewriteSpecifiers(original, fileDir);
    code = rewriteRelativeRequires(code, fileDir);
    code = applyBanner(code);
    if (code !== original) {
      fs.writeFileSync(file, code);
    }
  }

  fs.writeFileSync(
    path.join(ESM_DIR, 'package.json'),
    JSON.stringify({ type: 'module' }, null, 2) + '\n'
  );

  console.log(`esm-shim: processed ${files.length} files in dist/esm`);
}

// Only run automatically when invoked as a script (node scripts/esm-shim.js).
// When required from a test the helpers are exercised directly without touching
// dist/esm or writing package.json.
if (require.main === module) {
  main();
}

module.exports = {
  needsCjsBanner,
  applyBanner,
  stripStringsAndComments,
  CJS_BANNER,
};
