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
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { SIZE_BUDGET_BYTES, TARGETS } from "./bundle.mjs";
import { importsOf, layerOf, targetOf, matchesAllowlist, ungovernedRootsIn, violations, sourceFilesUnder } from "./depgraph.mjs";

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

// ---- the hole above the layer rule -----------------------------------------
//
// Every test above asks "is this import legal from where it sits?". None asks
// whether the checker LOOKS at where a file sits. governedRoots was only a
// list of directories to walk, so a new top-level directory was never visited
// -- it could import across both seams and the run still printed "no
// violations". boundaries.json asserted this was enforced from the day it was
// written, which made it the same failure the fixtures above exist to prevent,
// one level up: a clean pass over code nothing checked.

function tree(spec) {
  const root = mkdtempSync(join(tmpdir(), "boundaries-"));
  for (const [path, body] of Object.entries(spec)) {
    const full = join(root, path);
    mkdirSync(dirname(full), { recursive: true });
    writeFileSync(full, body);
  }
  return root;
}

const CONFIG = { governedRoots: ["core"], ungovernedRoots: ["tools"] };

test("a new top-level directory holding source is reported, not walked past", () => {
  const root = tree({
    "core/src/a.ts": "export const a = 1;",
    "features/src/sneaky.ts": 'import { invoke } from "@tauri-apps/api/core";\nexport const x = invoke;',
  });
  try {
    const found = ungovernedRootsIn(root, CONFIG);
    assert.deepEqual(found, [{ name: "features", count: 1 }]);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("a governed root is not reported as ungoverned", () => {
  // The positive control. Without it a function returning every directory
  // passes the test above and fails every real run.
  const root = tree({ "core/src/a.ts": "export const a = 1;" });
  try {
    assert.deepEqual(ungovernedRootsIn(root, CONFIG), []);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("a directory declared ungoverned is exempt, because someone decided it", () => {
  const root = tree({ "tools/build.mjs": "export const b = 1;" });
  try {
    assert.deepEqual(ungovernedRootsIn(root, CONFIG), []);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("a directory with no source files is not reported", () => {
  // docs/ and fixture folders would otherwise fail every build, and a checker
  // that cries wolf gets its list padded until it stops meaning anything.
  const root = tree({ "assets/logo.png": "not source", "core/src/a.ts": "export const a = 1;" });
  try {
    assert.deepEqual(ungovernedRootsIn(root, CONFIG), []);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("source nested deep inside a new directory still counts", () => {
  // The shallow version of this check passes on features/src/deep/x.ts.
  const root = tree({ "features/a/b/c/x.ts": "export const x = 1;" });
  try {
    assert.deepEqual(ungovernedRootsIn(root, CONFIG), [{ name: "features", count: 1 }]);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("node_modules and dist are never reported", () => {
  const root = tree({
    "node_modules/pkg/index.mjs": "export const x = 1;",
    "dist/out.ts": "export const x = 1;",
    "core/src/a.ts": "export const a = 1;",
  });
  try {
    assert.deepEqual(ungovernedRootsIn(root, CONFIG), []);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("the real boundaries.json accounts for every directory actually on disk", () => {
  // The one that will fail on somebody's future branch, which is the point.
  const real = JSON.parse(readFileSync(join(here, "boundaries.json"), "utf8"));
  assert.deepEqual(ungovernedRootsIn(join(here, ".."), real), []);
});

// ---- the checker must keep checking every kind of file it claims to --------

test("a violation in a .mjs file is reported, not skipped", async () => {
  // `entry.endsWith(".ts") || entry.endsWith(".mjs")` -> dropping the .mjs half
  // survived: the checker silently stops walking every .mjs in the package and
  // still prints "136 files checked, no violations". That is verbatim the
  // failure boundaries.json's own comment warns about -- "a rule that stops
  // covering new code while still reporting a clean pass is worse than no
  // rule" -- and tools/ is entirely .mjs.
  const root = tree({
    "core/src/a.ts": "export const a = 1;",
    "core/src/sneaky.mjs": 'import { invoke } from "@tauri-apps/api/core";\nexport const x = invoke;',
  });
  try {
    const files = await importsOf(
      [join(root, "core/src/a.ts"), join(root, "core/src/sneaky.mjs")],
      root,
    );
    const found = violations(files, {
      layers: { core: { path: "core/src", mayImport: [] } },
      externals: { "@tauri-apps/api": ["adapters/src/tauri"] },
      governedRoots: ["core"],
    });
    assert.ok(
      found.some((v) => v.file.endsWith(".mjs")),
      "a .mjs file that crosses a seam must be reported",
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("the walk collects .mjs files as well as .ts", () => {
  // The narrower form, so the failure names the cause rather than a symptom.
  const root = tree({
    "core/src/a.ts": "export const a = 1;",
    "core/src/b.mjs": "export const b = 2;",
    "core/src/notes.md": "not source",
  });
  try {
    const found = sourceFilesUnder(root, ["core"]).map((f) => f.slice(root.length + 1));
    assert.deepEqual(
      found.map((f) => f.split("/").pop()).sort(),
      ["a.ts", "b.mjs"].sort(),
      "the walk must pick up both extensions, and nothing else",
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("an ungoverned directory holding only .mjs is still reported", () => {
  // The file-count walk inside `ungovernedRootsIn` had its own `.mjs` test,
  // separate from the one in `sourceFilesUnder`. Dropping it makes a new
  // all-.mjs top-level directory report ZERO files, so it is not flagged and
  // passes ungoverned -- verbatim the failure boundaries.json's comment warns
  // about, and `tools/` itself is entirely .mjs.
  const root = tree({
    "core/src/a.ts": "export const a = 1;",
    "scripts/build.mjs": "export const b = 1;",
  });
  try {
    assert.deepEqual(
      ungovernedRootsIn(root, { governedRoots: ["core"], ungovernedRoots: [] }),
      [{ name: "scripts", count: 1 }],
      "an all-.mjs directory must be counted, not skipped",
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("the size budget and the webview targets are the values the gate claims", () => {
  // `SIZE_BUDGET_BYTES` and `TARGETS` are the entire contract of the bundle
  // gate, and both could be changed silently -- 400kB to 4MB, or the baseline
  // moved from safari16/chrome108 to a browser no target device runs. A gate
  // whose threshold can be edited without a failing test is a gate that can be
  // turned off.
  assert.equal(SIZE_BUDGET_BYTES, 400 * 1024, "the budget is what makes a dependency a decision");
  assert.deepEqual(TARGETS, ["safari16", "chrome108"], "the WebView floor is the OS, not the current Chrome");
});

// ---- the allowlist glob is part of the gate, not a convenience -------------

test("a single * does not cross a directory boundary", () => {
  // `[^/]*` -> `.*` survived. `ui/*.ts` would then match `ui/sub/a.ts`, so
  // every allowlist entry silently widens to cover subdirectories it was
  // written to exclude -- and an allowlist that is broader than written is a
  // rule that stopped applying.
  assert.equal(matchesAllowlist("ui/*.ts", "ui/a.ts"), true);
  assert.equal(matchesAllowlist("ui/*.ts", "ui/sub/a.ts"), false, "a single * must not cross /");
  assert.equal(matchesAllowlist("ui/**/*.ts", "ui/sub/a.ts"), true, "** is the one that crosses");
});

test("a package named by a GLOB key is still constrained", () => {
  // `externalAllowed` dropping `matchesAllowlist(name, pkg)` survived: a glob
  // key like `@tauri-apps/plugin-*` stops matching, so the package falls
  // through to "no rule" and is allowed from anywhere. The plugin imports the
  // Tauri seam exists to contain become invisible.
  const config = {
    layers: { ui: { path: "ui/src", mayImport: [] }, adapters: { path: "adapters/src", mayImport: [] } },
    externals: { "@tauri-apps/plugin-*": ["adapters/src/tauri"] },
    governedRoots: ["ui", "adapters"],
  };
  const found = violations(
    new Map([["ui/src/z.ts", ["@tauri-apps/plugin-haptics"]]]),
    config,
  );
  assert.ok(
    found.some((v) => v.specifier === "@tauri-apps/plugin-haptics"),
    "a plugin imported from ui/ must be a violation",
  );
});

test("the same package IS allowed from the path its rule names", () => {
  // The pair: a rule that refused everywhere would pass the test above and
  // make the real adapter unbuildable.
  const config = {
    layers: { adapters: { path: "adapters/src", mayImport: [] } },
    externals: { "@tauri-apps/plugin-*": ["adapters/src/tauri"] },
    governedRoots: ["adapters"],
  };
  const found = violations(
    new Map([["adapters/src/tauri/haptics.ts", ["@tauri-apps/plugin-haptics"]]]),
    config,
  );
  assert.deepEqual(found, []);
});
