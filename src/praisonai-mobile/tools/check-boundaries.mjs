/**
 * Run the layer rule over the whole tree and exit non-zero on any violation.
 *
 * Separate from depgraph.mjs so the rule's logic stays a library that tests can
 * call, and separate from depgraph.test.mjs so a failure here reads as "your
 * import is illegal" rather than "a test failed".
 *
 * `npm run boundaries`
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, relative, sep } from "node:path";

import { importsOf, sourceFilesUnder, ungovernedRootsIn, violations } from "./depgraph.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const config = JSON.parse(readFileSync(join(here, "boundaries.json"), "utf8"));

const norm = (p) => p.split(sep).join("/");

// A new top-level source directory omitted from both root lists is never
// walked, so it could import across every seam while the run still printed
// "no violations". Extracting the walk turned governedRoots back into a bare
// list of directories to walk, which silently dropped this guard -- the exact
// failure boundaries.json's own comment warns about: a rule that stops
// covering new code while reporting a clean pass is worse than no rule.
const ungoverned = ungovernedRootsIn(root, config);
if (ungoverned.length > 0) {
  for (const { name, count } of ungoverned) {
    console.error(
      `boundaries: [ungoverned-root] ${name}/ holds ${count} source file(s) that no layer rule covers.\n` +
        `    Add "${name}" to governedRoots in tools/boundaries.json (with a matching entry in\n` +
        `    "layers"), or to ungovernedRoots if it is deliberately exempt.`,
    );
  }
  console.error(`\nboundaries: ${ungoverned.length} ungoverned top-level director(y|ies)`);
  process.exit(1);
}

const files = sourceFilesUnder(root, config.governedRoots);

if (files.length === 0) {
  // Not a pass. A checker that reports success over an empty set is the exact
  // failure this package's tests are written to prevent, so say so out loud.
  console.log("boundaries: no source files under the governed roots yet — nothing checked");
  process.exit(0);
}

const found = violations(await importsOf(files, root), config);

if (found.length === 0) {
  console.log(`boundaries: ${files.length} files checked, no violations`);
  process.exit(0);
}

for (const v of found) {
  const where = v.specifier ? `${v.file} -> ${v.specifier}` : v.file;
  console.error(`boundaries: [${v.kind}] ${where}\n    ${v.message}`);
}
console.error(`\nboundaries: ${found.length} violation(s) across ${files.length} files`);
process.exit(1);
