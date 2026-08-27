/**
 * The layer rule, tested by running it.
 *
 * The house rule in this repo is "assert on behaviour, never on source text" --
 * an audit once ran 16 mutations against a 408-test suite and 8 survived, every
 * one of them covered only by a test asserting that a string appeared in the
 * source rather than calling the code.
 *
 * A dependency checker is the awkward case, because reading source IS its job.
 * So the rule is applied one level up: the reading is a named function, these
 * tests CALL it, and fixtures that genuinely violate the rule prove it reports
 * them. Without those fixtures a checker that returns [] for everything passes
 * this file completely -- the same failure mode, one layer removed.
 *
 * Fixtures live under tools/fixtures/ so a deliberate violation can never break
 * the real build. They are then RELOCATED onto a layer path before checking,
 * because where a file lives is the whole input to the rule: the identical
 * import is legal from adapters/src/tauri/bridge.ts and illegal from core/.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { importsOf, layerOf, targetOf, matchesAllowlist, violations } from "./depgraph.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const config = JSON.parse(readFileSync(join(here, "boundaries.json"), "utf8"));

/**
 * Parse a fixture, then pretend it lives at `asPath` and check it there.
 * Returns the violations reported for that hypothetical location.
 */
async function checkAs(fixture, asPath) {
  const parsed = await importsOf([join(here, "fixtures", fixture)], root);
  const specifiers = [...parsed.values()][0] ?? [];
  return violations(new Map([[asPath, specifiers]]), config);
}

test("core may not import a tauri api", async () => {
  // The UI-shell seam. If core can reach Tauri, swapping to React Native means
  // auditing every file by hand instead of replacing one directory.
  const found = await checkAs("violating-core.ts", "core/src/run/controller.ts");
  assert.ok(
    found.some((v) => v.kind === "external" && v.specifier.startsWith("@tauri-apps/")),
    `expected a @tauri-apps violation, got ${JSON.stringify(found)}`,
  );
});

test("ui may not import praisonai", async () => {
  // The agent-framework seam. If ui/ reaches praisonai directly, replacing the
  // framework stops being "one directory plus a conformance run".
  const found = await checkAs("violating-ui.ts", "ui/src/views/thread-view.ts");
  assert.ok(
    found.some((v) => v.kind === "external" && v.specifier === "praisonai"),
    `expected a praisonai violation, got ${JSON.stringify(found)}`,
  );
});

test("the tauri bridge may import a tauri api", async () => {
  // The mirror of the first test: the SAME specifier, from the one place it is
  // allowed. Asserted separately because a checker that flags everything would
  // pass every violation test above and still be worthless.
  const found = await checkAs("allowed-tauri-adapter.ts", "adapters/src/tauri/bridge.ts");
  assert.deepEqual(found, [], `expected no violations, got ${JSON.stringify(found)}`);
});

test("only bridge.ts may import a tauri api directly", async () => {
  // Every other tauri file goes through the bridge, so a React Native port has
  // exactly one file to replace rather than a directory to audit.
  const found = await checkAs("allowed-tauri-adapter.ts", "adapters/src/tauri/shell.ts");
  assert.ok(
    found.some((v) => v.specifier === "@tauri-apps/api/core"),
    `expected a violation from a non-bridge file, got ${JSON.stringify(found)}`,
  );
});

test("an import specifier inside a string literal is not a violation", async () => {
  // This is why imports come from a real parse and not a regex. An
  // over-reporting checker gets switched off, at which point it protects
  // nothing at all.
  const found = await checkAs("string-not-import.ts", "core/src/settings/validate.ts");
  assert.deepEqual(found, [], `expected no violations, got ${JSON.stringify(found)}`);
});

test("a file in no declared layer is reported rather than silently allowed", async () => {
  // The day someone adds a new top-level directory the rule must notice.
  // Otherwise it keeps reporting a clean pass while covering less and less.
  const found = await checkAs("ungoverned/orphan.ts", "newthing/src/orphan.ts");
  assert.ok(
    found.some((v) => v.kind === "ungoverned"),
    `expected an ungoverned finding, got ${JSON.stringify(found)}`,
  );
});

test("layerOf attributes a path to the layer that owns it", () => {
  assert.equal(layerOf("core/src/run/controller.ts", config), "core");
  assert.equal(layerOf("engines/src/praisonai-ts/engine.ts", config), "engines");
  assert.equal(layerOf("protocol/src/events.ts", config), "protocol");
  assert.equal(layerOf("tools/depgraph.mjs", config), null);
});

test("matchesAllowlist honours a directory prefix, a glob and an exact file", () => {
  assert.equal(matchesAllowlist("adapters/src/tauri", "adapters/src/tauri/shell.ts"), true);
  assert.equal(matchesAllowlist("adapters/src/tauri", "adapters/src/web/shell.ts"), false);
  // A prefix must stop at a path boundary, or "adapters/src/tau" would match.
  assert.equal(matchesAllowlist("adapters/src/tau", "adapters/src/tauri/shell.ts"), false);
  assert.equal(matchesAllowlist("**/*.test.ts", "core/src/run/queue.test.ts"), true);
  assert.equal(matchesAllowlist("**/*.test.ts", "core/src/run/queue.ts"), false);
  assert.equal(matchesAllowlist("adapters/src/tauri/bridge.ts", "adapters/src/tauri/bridge.ts"), true);
  assert.equal(matchesAllowlist("adapters/src/tauri/bridge.ts", "adapters/src/tauri/shell.ts"), false);
});

test("targetOf resolves a relative import to the layer that owns the target", () => {
  assert.equal(
    targetOf("../../../protocol/src/events.ts", "core/src/run/controller.ts", config),
    "protocol",
  );
  assert.equal(
    targetOf("./transcript.ts", "core/src/run/controller.ts", config),
    "core",
  );
});

test("targetOf reduces a bare specifier to its package name", () => {
  assert.equal(targetOf("@tauri-apps/api/core", "core/src/x.ts", config), "@tauri-apps/api");
  assert.equal(targetOf("praisonai/mobile", "ui/src/x.ts", config), "praisonai");
  assert.equal(targetOf("node:test", "core/src/x.ts", config), "node:test");
});

test("a layer may import a layer it declares, and may not import one it does not", async () => {
  // core -> protocol is declared and legal. protocol -> core is not: protocol
  // is layer 0 and imports nothing, which is what lets it be reviewed alone.
  const legal = violations(
    new Map([["core/src/run/controller.ts", ["../../../protocol/src/events.ts"]]]),
    config,
  );
  assert.deepEqual(legal, [], `core -> protocol should be legal, got ${JSON.stringify(legal)}`);

  const illegal = violations(
    new Map([["protocol/src/events.ts", ["../../core/src/run/transcript.ts"]]]),
    config,
  );
  assert.ok(
    illegal.some((v) => v.kind === "cross-layer" && v.from === "protocol" && v.to === "core"),
    `protocol -> core should be reported, got ${JSON.stringify(illegal)}`,
  );
});

test("node builtins and relative imports within a layer are never violations", () => {
  const found = violations(
    new Map([["core/src/run/queue.ts", ["node:assert", "./transcript.ts"]]]),
    config,
  );
  assert.deepEqual(found, [], `expected no violations, got ${JSON.stringify(found)}`);
});

test("a test file may import the shared fakes but production code may not", () => {
  // The fakes live in their own layer so both adapter sets and every core test
  // can share them. Granting that to the whole layer instead of to test files
  // would make a fake reachable from a shipped module -- and a fake that can be
  // shipped eventually is.
  const inTest = violations(
    new Map([["core/src/run/controller.test.ts", ["../../../testing/src/fake-scheduler.ts"]]]),
    config,
  );
  assert.deepEqual(inTest, [], `a test importing a fake should be legal, got ${JSON.stringify(inTest)}`);

  const inProd = violations(
    new Map([["core/src/run/controller.ts", ["../../../testing/src/fake-scheduler.ts"]]]),
    config,
  );
  assert.ok(
    inProd.some((v) => v.kind === "cross-layer" && v.to === "testing"),
    `production code importing a fake should be reported, got ${JSON.stringify(inProd)}`,
  );
});
