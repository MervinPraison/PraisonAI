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

const ESM_DIR = path.join(__dirname, '..', 'dist', 'esm');

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
    let code = rewriteSpecifiers(original, path.dirname(file));
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
