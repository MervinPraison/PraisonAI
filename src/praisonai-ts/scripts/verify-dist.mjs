// Smoke-checks that both published entry points load and export Agent:
//   - CJS: require('../dist/index.js')
//   - ESM: await import('../dist/esm/index.js')
// Exits non-zero if either entry fails to load or Agent is missing.

import { createRequire } from 'module';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const require = createRequire(import.meta.url);
const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, '..');

let failed = false;

function check(label, mod) {
  if (mod && typeof mod.Agent === 'function') {
    console.log(`verify:dist ${label} OK — Agent is a function`);
  } else {
    console.error(`verify:dist ${label} FAILED — Agent not exported as a function`);
    failed = true;
  }
}

const cjs = require(join(root, 'dist', 'index.js'));
check('cjs (require)', cjs);

const esm = await import(join(root, 'dist', 'esm', 'index.js'));
check('esm (import)', esm);

if (failed) {
  process.exit(1);
}
console.log('verify:dist all OK');
