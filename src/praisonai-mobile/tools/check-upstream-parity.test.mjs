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
