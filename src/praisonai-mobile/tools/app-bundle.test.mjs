/**
 * The REAL app graph, through the gate.
 *
 * tools/bundle.test.mjs proves each check can fail, against fixtures written
 * into a temp directory. That is necessary and it is not sufficient: an audit
 * found the gate had never once run against `app/src/main.ts`, because that
 * file did not exist -- so the checks were all in a known state about code
 * nobody shipped, and in an unknown state about the code that would be.
 *
 * This file closes that. It is slower than the fixture suite because it
 * bundles the whole application, which is exactly the point.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { dirname, join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { mkdtemp } from "node:fs/promises";

import { bundle, SIZE_BUDGET_BYTES } from "./bundle.mjs";

const pkg = resolve(dirname(new URL(import.meta.url).pathname), "..");
const out = join(await mkdtemp(join(tmpdir(), "praison-app-")), "app.js");
const report = await bundle({ entry: join(pkg, "app/src/main.ts"), outfile: out, minify: false });

test("the real app bundles with no problems at all", () => {
  assert.deepEqual(report.problems, [], report.problems.join("\n"));
});

test("no Node builtin is statically imported by the app", () => {
  // The import-time killer: the bundle dies before any code runs, so there is
  // no error boundary, no message, and a blank screen.
  assert.deepEqual(report.fatal, []);
});

test("no top-level process.env read survives into the app", () => {
  assert.deepEqual(report.processReads, []);
});

test("the app is within the size budget", () => {
  assert.ok(
    report.bytes < SIZE_BUDGET_BYTES,
    `${(report.bytes / 1024).toFixed(1)}kB of ${(SIZE_BUDGET_BYTES / 1024).toFixed(0)}kB`,
  );
});

test("the bundle actually contains every layer, not just an entry stub", () => {
  // A bundle that tree-shook the app away would pass every check above. These
  // are one real symbol per layer, from the unminified output.
  for (const symbol of [
    "buildTranscript",      // ui/transcript
    "reconcile",            // ui/render
    "createRunController",  // core/run
    "createSession",        // core/chat
    "intentFrom",           // app
    "applyOps",             // app/dom
    "installCrashHandler",  // app/crash
  ]) {
    assert.ok(report.code.includes(symbol), `${symbol} is missing from the bundle`);
  }
});

test("the app does not pull in a test fake", () => {
  // testing/ is testImports-only. A fake reaching a shipped bundle would mean
  // the app runs against a scripted engine on a real device.
  for (const fake of ["createScriptedEngine", "createFakeStorage", "createFakeShell", "createFakeWindow"]) {
    assert.ok(!report.code.includes(fake), `${fake} reached the app bundle`);
  }
});
