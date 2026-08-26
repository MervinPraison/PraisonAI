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

const CJS_BANNER = [
  "import { createRequire as __praisonCreateRequire } from 'module';",
  "import { fileURLToPath as __praisonFileURLToPath } from 'url';",
  "import { dirname as __praisonDirname } from 'path';",
  'const require = __praisonCreateRequire(import.meta.url);',
  'const __filename = __praisonFileURLToPath(import.meta.url);',
  'const __dirname = __praisonDirname(__filename);',
  // In ESM there is no CommonJS module object. Provide a stub so patterns like
  // `require.main === module` compile and evaluate to false (this file is not a
  // CLI entry point when imported), and `module.exports = ...` remains harmless.
  'const module = { exports: {} };',
].join('\n');

function needsCjsBanner(code) {
  return (
    /\brequire\b/.test(code) ||
    /\b__dirname\b/.test(code) ||
    /\b__filename\b/.test(code) ||
    /\bmodule\.exports\b/.test(code) ||
    /===\s*module\b/.test(code) ||
    /\bmodule\s*===/.test(code)
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

main();
