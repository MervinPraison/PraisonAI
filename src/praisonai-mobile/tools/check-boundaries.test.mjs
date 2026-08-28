/**
 * The gate itself, run as a process.
 *
 * `check-boundaries.mjs` had no test of any kind, and it is the mechanism every
 * layering claim in this package rests on. A mutation sweep found TWO
 * independent ways to turn it into a complete no-op with `npm run check` still
 * green:
 *
 *   `files.length === 0` -> `>= 0`   takes the "nothing to check" branch every
 *                                    time, so it reports success having looked
 *                                    at nothing;
 *   `process.exit(1)`    -> `exit(0)` prints every violation it found and then
 *                                    passes anyway.
 *
 * depgraph.test.mjs covers the RULE thoroughly. Nothing covered the CLI that
 * runs it, decides what to walk, and turns the answer into an exit code -- and
 * an exit code is the only part CI actually reads.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

function tree(spec) {
  const root = mkdtempSync(join(tmpdir(), "gate-"));
  for (const [path, body] of Object.entries(spec)) {
    const full = join(root, path);
    mkdirSync(dirname(full), { recursive: true });
    writeFileSync(full, body);
  }
  // The checker reads its config from beside itself, so the fixture only needs
  // the source tree.
  return root;
}

function runGate(root) {
  const run = spawnSync(process.execPath, [join(here, "check-boundaries.mjs"), root], {
    encoding: "utf8",
    timeout: 60_000,
  });
  return { status: run.status, output: `${run.stdout ?? ""}${run.stderr ?? ""}` };
}

test("a clean tree passes", () => {
  const root = tree({
    "core/src/a.ts": 'import { b } from "../../protocol/src/b.ts";\nexport const a = b;',
    "protocol/src/b.ts": "export const b = 1;",
  });
  try {
    const { status, output } = runGate(root);
    assert.equal(status, 0, `a clean tree failed:\n${output}`);
    assert.match(output, /no violations/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("a real violation exits NON-ZERO, which is the only part CI reads", () => {
  // `process.exit(1)` -> `exit(0)` prints the violation and passes anyway. The
  // message is not the gate; the exit code is.
  const root = tree({
    "core/src/leak.ts": 'import { invoke } from "@tauri-apps/api/core";\nexport const x = invoke;',
  });
  try {
    const { status, output } = runGate(root);
    assert.notEqual(status, 0, `a violation exited 0:\n${output}`);
    assert.match(output, /violation/i);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("finding NOTHING to check is a failure, not a pass", () => {
  // The comment on this branch always said "Not a pass"; the exit code said
  // otherwise. That disagreement is what made the gate switchable off by one
  // character -- `files.length === 0` -> `>= 0` takes this branch every time.
  const root = tree({ "docs/readme.md": "no source here" });
  try {
    const { status, output } = runGate(root);
    assert.notEqual(status, 0, `an empty governed set reported success:\n${output}`);
    assert.match(output, /nothing was checked/i);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("an ungoverned top-level directory holding source is a failure", () => {
  // The other half of the same rule, already covered as a library function --
  // this asserts the CLI turns it into a non-zero exit.
  const root = tree({
    "core/src/a.ts": "export const a = 1;",
    "features/src/sneaky.ts": "export const x = 1;",
  });
  try {
    const { status, output } = runGate(root);
    assert.notEqual(status, 0, `an ungoverned directory passed:\n${output}`);
    assert.match(output, /ungoverned/i);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("a violation inside a .mjs file exits non-zero too", () => {
  // tools/ is entirely .mjs. Dropping the extension from the walk made the
  // checker skip all of it and still print a clean pass.
  const root = tree({
    "core/src/a.ts": "export const a = 1;",
    "core/src/leak.mjs": 'import { invoke } from "@tauri-apps/api/core";\nexport const x = invoke;',
  });
  try {
    const { status, output } = runGate(root);
    assert.notEqual(status, 0, `a .mjs violation passed:\n${output}`);
    assert.match(output, /leak\.mjs/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
