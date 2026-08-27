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

import { importsOf, violations } from "./depgraph.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const config = JSON.parse(readFileSync(join(here, "boundaries.json"), "utf8"));

const norm = (p) => p.split(sep).join("/");

/** Every .ts file under the governed roots. Fixtures are deliberately excluded:
 *  they violate the rule on purpose and are exercised by depgraph.test.mjs. */
function sourceFiles() {
  const out = [];
  const walk = (dir) => {
    let entries;
    try {
      entries = readdirSync(dir);
    } catch {
      return; // a governed root that does not exist yet is not an error
    }
    for (const entry of entries) {
      if (entry === "node_modules" || entry === "dist" || entry.startsWith(".")) continue;
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (entry.endsWith(".ts") || entry.endsWith(".mjs")) out.push(full);
    }
  };
  for (const rootName of config.governedRoots) walk(join(root, rootName));
  return out;
}

const files = sourceFiles();

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
