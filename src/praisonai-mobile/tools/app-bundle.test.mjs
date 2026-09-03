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
 *
 * Built SPLIT, because that is the shape index.html loads: `app.js` plus the
 * chunks behind its one `import()`. Built TWICE, because two questions need
 * two builds: the gate and the budgets are asked of the bytes that ship,
 * which are minified; the symbol checks need names to look for, which
 * minification removes. Asking the budget of an unminified build measured
 * 2.9MB of lazy chunks against a 1.5MB allowance -- a failure about a build
 * nobody ships.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { dirname, join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { mkdtemp } from "node:fs/promises";

import {
  bundle,
  classifyBareImports,
  praisonaiRoot,
  CLI_ONLY_PACKAGES,
  SHELL_BUDGET_BYTES,
  LAZY_BUDGET_BYTES,
} from "./bundle.mjs";

const pkg = resolve(dirname(new URL(import.meta.url).pathname), "..");
const entry = join(pkg, "app/src/main.ts");
/** What ships: minified, split. Every gate and budget check reads this. */
const report = await bundle({ entry, outdir: await mkdtemp(join(tmpdir(), "praison-app-")) });
/** The same graph with its names intact, for the symbol checks only. */
const readable = await bundle({ entry, outdir: await mkdtemp(join(tmpdir(), "praison-app-")), minify: false });

/** The metafile's inputs for an emitted chunk, by the chunk's basename. */
const inputsOf = (name) => {
  const out = Object.entries(report.metafile.outputs).find(([p]) => p.split("/").pop() === name)?.[1];
  return Object.keys(out?.inputs ?? {});
};
// Through the `file:` link, so the real ../praisonai-ts directory: esbuild
// records inputs by real path, and a node_modules/ pattern would match nothing.
const upstream = praisonaiRoot();
const isUpstream = (input) => upstream !== null && resolve(process.cwd(), input).startsWith(upstream + "/");

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

test("the shell is within the SHELL budget", () => {
  assert.ok(
    report.shellBytes < SHELL_BUDGET_BYTES,
    `shell ${(report.shellBytes / 1024).toFixed(1)}kB of ${(SHELL_BUDGET_BYTES / 1024).toFixed(0)}kB`,
  );
});

test("the engine's chunks are within the LAZY allowance", () => {
  // Both halves: that there IS something lazy -- otherwise the allowance is
  // asserting nothing -- and that it fits.
  assert.ok(report.lazyBytes > 0, "the engine must be in the bundle, behind an import()");
  assert.ok(
    report.lazyBytes < LAZY_BUDGET_BYTES,
    `lazy ${(report.lazyBytes / 1024).toFixed(1)}kB of ${(LAZY_BUDGET_BYTES / 1024).toFixed(0)}kB`,
  );
});

test("praisonai reaches no eager chunk -- the split is real", () => {
  // The claim both budgets rest on. If a static path to praisonai ever
  // appears, every one of its bytes moves into the shell. The shell budget
  // would catch that eventually, at 400kB; this catches it at one byte, and
  // names the chunk.
  for (const name of report.eager) {
    const upstream = inputsOf(name).filter(isUpstream);
    assert.deepEqual(upstream, [], `${name} loads at first paint and contains praisonai: ${upstream.slice(0, 3).join(", ")}`);
  }
  const lazyWithEngine = report.chunks.filter((c) => !report.eager.has(c.name) && inputsOf(c.name).some(isUpstream));
  assert.ok(lazyWithEngine.length > 0, "and praisonai IS in the bundle, in a lazy chunk");
});

test("the CLI-only packages are reached lazily, and only lazily", () => {
  // They are external (bundle.mjs says why), and external is safe only behind
  // an import(). This pins the upstream fact that makes that true: no static
  // import of chalk & co. anywhere on praisonai/mobile's graph. `readline` is
  // the same story for a builtin, and `fatal` above already covers it.
  const kinds = classifyBareImports(report.metafile);
  for (const name of CLI_ONLY_PACKAGES) {
    assert.equal(kinds.get(name), "dynamic", `${name} must be reached through import() only (saw ${kinds.get(name)})`);
  }
  assert.deepEqual(report.cliStatic, []);
});

test("the shell actually contains every layer, not just an entry stub", () => {
  // A bundle that tree-shook the app away would pass every check above. These
  // are one real symbol per layer, from the unminified entry chunk.
  for (const symbol of [
    "buildTranscript",      // ui/transcript
    "reconcile",            // ui/render
    "createRunController",  // core/run
    "createSession",        // core/chat
    "intentFrom",           // app
    "applyOps",             // app/dom
    "installCrashHandler",  // app/crash
  ]) {
    assert.ok(readable.code.includes(symbol), `${symbol} is missing from the shell`);
  }
});

test("the app does not pull in a test fake", () => {
  // testing/ is testImports-only. A fake reaching a shipped bundle would mean
  // the app runs against a scripted engine on a real device.
  for (const fake of ["createScriptedEngine", "createFakeStorage", "createFakeShell", "createFakeWindow"]) {
    assert.ok(!readable.code.includes(fake), `${fake} reached the app bundle`);
  }
});
