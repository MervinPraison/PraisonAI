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
// The package root, or one given on the command line. Injectable so the CLI
// itself can be tested: it had no test of any kind, and a mutation sweep found
// two independent ways to turn the whole gate into a no-op with a green build.
const root = process.argv[2] ?? join(here, "..");
const config = JSON.parse(readFileSync(join(here, "boundaries.json"), "utf8"));

const norm = (p) => p.split(sep).join("/");

/** Top-level directories holding source that neither `governedRoots` nor
 *  `ungovernedRoots` accounts for.
 *
 *  Restored: this check was silently deleted when `sourceFiles` was extracted
 *  into depgraph.mjs -- the import survived and the CALL did not, so for six
 *  commits a new top-level directory could import across every seam and the
 *  checker said nothing. Precisely the defect it was written to prevent,
 *  reintroduced by the refactor that was meant to make it testable. Nothing
 *  noticed, because the CLI had no test; the test below is what found it. */
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
  // NOT a pass, and now the exit code agrees with the sentence.
  //
  // This branch used to print "nothing checked" and exit 0. The comment said
  // "Not a pass" and the exit code said otherwise, which is the same defect
  // the rest of this file exists to catch -- and it made the whole gate
  // switchable off by a single character: `files.length === 0` -> `>= 0`
  // takes this branch every time, so the checker reports success having looked
  // at nothing at all, and `npm run check` stays green.
  console.error("boundaries: no source files under the governed roots — nothing was checked");
  process.exit(1);
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
