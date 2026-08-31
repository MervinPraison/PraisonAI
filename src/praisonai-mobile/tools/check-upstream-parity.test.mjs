/**
 * The parity checker, checked for the one failure it cannot report on itself.
 *
 * Its own header says "a check that silently stops covering anything is worse
 * than no check". It then did exactly that: the drift filter keeps only lines
 * mentioning `parity.ts`, and a spawn failure's message ("spawn npx ENOENT")
 * mentions no such thing -- so zero drift lines, so a printed success and a
 * zero exit, over a typechecker that never started.
 *
 * Driven as a subprocess because that is the only way to reach the failure:
 * it is a property of how the tool is invoked, not of a function it exports.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const script = join(here, "check-upstream-parity.mjs");

/** node by absolute path, so the child still starts when PATH is emptied. */
const run = (path) =>
  spawnSync(process.execPath, [script], {
    encoding: "utf8",
    timeout: 300_000,
    env: { ...process.env, PATH: path },
  });

test("a typechecker that never ran is a FAILURE, not a clean pass", () => {
  // PATH without npx. Previously: "upstream-parity: the real Agent still
  // satisfies PraisonAgent", exit 0 -- having compiled nothing at all.
  const result = run("/usr/bin:/bin");
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`;

  assert.notEqual(result.status, 0, `reported success without running:\n${output}`);
  assert.match(output, /did not run/i, "the reason must say the check did not run");
  assert.doesNotMatch(
    output,
    /still satisfies PraisonAgent/,
    "it must not also print the success line",
  );
});

test("the checker still passes when it CAN run", () => {
  // The control. Without it, a checker that failed unconditionally would
  // satisfy the test above while breaking every build.
  const result = run(process.env["PATH"] ?? "");
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`;
  assert.equal(result.status, 0, `the real check should pass on a clean tree:\n${output}`);
  assert.match(output, /still satisfies PraisonAgent/);
});

test("real drift makes the checker EXIT non-zero, not merely print", () => {
  // `process.exitCode = 1` -> `= 0` survived: the drift is printed in full and
  // the job passes anyway. The message is not the gate; the exit code is, and
  // CI reads only the latter.
  const dir = mkdtempSync(join(tmpdir(), "parity-drift-"));
  const api = join(dir, "agent-api.ts");
  // A member the real Agent does not have, so the assignment cannot typecheck.
  writeFileSync(api, "export interface PraisonAgent { __definitelyNotOnAgent: number; }\n");
  try {
    const result = spawnSync(process.execPath, [script], {
      encoding: "utf8",
      timeout: 300_000,
      env: { ...process.env, PARITY_AGENT_API: api },
    });
    const output = `${result.stdout ?? ""}${result.stderr ?? ""}`;
    assert.notEqual(result.status, 0, `drift was reported and then passed:\n${output}`);
    assert.doesNotMatch(output, /still satisfies PraisonAgent/, "it must not also claim success");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("the parity typecheck runs in STRICT mode", () => {
  // Dropping `--strict` survived: null-safety drift stops being detected, so
  // an upstream member becoming nullable no longer fails the gate. Provoked
  // with an interface that only differs under strictNullChecks.
  const dir = mkdtempSync(join(tmpdir(), "parity-strict-"));
  const api = join(dir, "agent-api.ts");
  writeFileSync(
    api,
    // `lastStopReason` is nullable upstream; requiring it non-null only fails
    // when strictNullChecks is on.
    "export interface PraisonAgent { lastStopReason: string; }\n",
  );
  try {
    const result = spawnSync(process.execPath, [script], {
      encoding: "utf8",
      timeout: 300_000,
      env: { ...process.env, PARITY_AGENT_API: api },
    });
    const output = `${result.stdout ?? ""}${result.stderr ?? ""}`;
    assert.notEqual(result.status, 0, `strict-only drift went undetected:\n${output}`);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("with no praisonai-ts beside it, the checker SKIPS and exits clean", () => {
  // A standalone clone has no sibling checkout. Three mutations survived here:
  // dropping `process.exit(0)` so the run carries on without the file it is
  // meant to check, and flipping `exists` so a missing path reads as present.
  // Either way the job fails for a reason that has nothing to do with drift,
  // and whoever sees it goes looking for an API change that never happened.
  const empty = mkdtempSync(join(tmpdir(), "parity-absent-"));
  const result = spawnSync(process.execPath, [script], {
    encoding: "utf8",
    env: { ...process.env, PARITY_UPSTREAM: join(empty, "praisonai-ts") },
  });
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`;

  assert.equal(result.status, 0, `a missing sibling must not fail the build:\n${output}`);
  assert.match(output, /SKIPPED/, "and it must say it skipped rather than passing silently");
  assert.doesNotMatch(
    output,
    /still satisfies PraisonAgent/,
    "a skip is not a pass -- it must not claim the check ran",
  );
});

test("with praisonai-ts present, it does NOT skip -- the pair", () => {
  // Without this, an `exists` that always answered false would satisfy the
  // test above and skip on every machine, including CI, forever.
  const result = spawnSync(process.execPath, [script], { encoding: "utf8" });
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`;
  assert.doesNotMatch(output, /SKIPPED/, `the monorepo has the sibling:\n${output}`);
  assert.equal(result.status, 0, output);
});

test("a drift failure NAMES what drifted, not just that something did", () => {
  // `console.error` of the drift lines was removable with a green suite: the
  // job goes red and prints nothing about which member changed, so the next
  // person has a failing gate and no way to act on it. The exit code is the
  // gate; the message is what makes it fixable.
  const dir = mkdtempSync(join(tmpdir(), "parity-named-"));
  const api = join(dir, "agent-api.ts");
  writeFileSync(api, "export interface PraisonAgent { __aMemberUpstreamDoesNotHave: number; }\n");
  const result = spawnSync(process.execPath, [script], {
    encoding: "utf8",
    env: { ...process.env, PARITY_AGENT_API: api },
  });
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`;

  assert.notEqual(result.status, 0, `drift must fail:\n${output}`);
  assert.match(output, /__aMemberUpstreamDoesNotHave/, `it must name the member:\n${output}`);
  assert.match(output, /parity\.ts/, "and where the mismatch was reported");
});
