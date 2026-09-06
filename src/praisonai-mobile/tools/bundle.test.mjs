/**
 * The bundle checks, proven non-vacuous.
 *
 * Every check here is run against a fixture that VIOLATES it and asserted to
 * fail, and against one that satisfies it and asserted to pass. A build check
 * that has only ever seen clean input is a check nobody knows the state of --
 * and this repo has paid for that once already: an audit ran 16 mutations
 * against a 408-test suite and 8 survived.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile, mkdir } from "node:fs/promises";
import { mkdirSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  bundle,
  bundledPackages,
  bundledHostLoadedProviders,
  isHostLoadedAISDKProvider,
  AI_INTERNAL_AI_SDK_PACKAGES,
  forbiddenAmong,
  topLevelProcessReads,
  unresolvedBareImports,
  classifyBareImports,
  FORBIDDEN_BUILTINS,
  SHELL_BUDGET_BYTES,
  LAZY_BUDGET_BYTES,
  isShippable,
} from "./bundle.mjs";

/** Write a throwaway package and bundle it. */
async function fixture(files) {
  const dir = await mkdtemp(join(tmpdir(), "praison-bundle-"));
  for (const [name, contents] of Object.entries(files)) {
    const path = join(dir, name);
    await mkdir(join(path, ".."), { recursive: true });
    await writeFile(path, contents);
  }
  return {
    dir,
    run: (entry = "main.js") =>
      bundle({ entry: join(dir, entry), outfile: join(dir, "out.js"), minify: false }),
    // The split form, which is what ships: `outdir` turns on chunking.
    runSplit: (entry = "main.js") =>
      bundle({ entry: join(dir, entry), outdir: join(dir, "out"), minify: false }),
  };
}

// ---- the Node-builtin check ------------------------------------------------

test("a bundle importing a Node builtin fails the build", async () => {
  // The real case: praisonai's agent/simple.ts does `import { randomUUID } from
  // 'crypto'`. In a webview that is an IMPORT-time failure -- the screen stays
  // blank with no error boundary and no message.
  const { run } = await fixture({
    "main.js": "import { randomUUID } from 'crypto';\nexport const id = randomUUID();\n",
  });
  const report = await run();

  assert.ok(report.forbidden.includes("crypto"), "crypto must be reported");
  assert.equal(report.problems.length > 0, true, "the build must fail");
  assert.match(report.problems[0], /IMPORT time/, "the reason must say why it is severe");
});

test("the node: prefix does not smuggle a builtin past the check", async () => {
  // `node:crypto` and `crypto` are the same import with different spellings.
  const { run } = await fixture({
    "main.js": "import { randomUUID } from 'node:crypto';\nexport const id = randomUUID();\n",
  });
  assert.ok((await run()).forbidden.includes("crypto"));
});

test("a clean bundle passes", async () => {
  // The pair: without it, "always fail" would satisfy both tests above.
  const { run } = await fixture({
    "main.js": "export const id = globalThis.crypto.randomUUID();\n",
  });
  const report = await run();
  assert.deepEqual(report.forbidden, []);
  assert.deepEqual(report.problems, []);
});

test("a non-builtin bare import is allowed through", async () => {
  // Only BUILTINS are forbidden. A real dependency is a packaging question,
  // not a webview-compatibility one, and failing on it would block every dep.
  const { run } = await fixture({
    "main.js": "import x from 'some-real-package';\nexport default x;\n",
  });
  const report = await run();
  assert.ok(report.bare.includes("some-real-package"));
  assert.deepEqual(report.forbidden, [], "a normal dependency is not a builtin");
});

test("the word crypto in a string is not an import", async () => {
  // Why this reads the metafile instead of grepping the output text. A grep
  // cannot tell an import from a string and would fail an innocent build.
  const { run } = await fixture({
    "main.js": "export const note = 'we do not import crypto here';\n",
  });
  assert.deepEqual((await run()).forbidden, []);
});

// ---- the top-level process check -------------------------------------------

test("a top-level process.env read fails the build", async () => {
  const { run } = await fixture({
    "main.js": "export const model = process.env.MODEL ?? 'gpt-4o-mini';\n",
  });
  const report = await run();
  assert.equal(report.processReads.length > 0, true);
  assert.ok(report.problems.some((p) => /process\.env/.test(p)));
});

test("a guarded read inside a function is allowed", async () => {
  // The pair, and the important one: this is exactly how the codebase is
  // EXPECTED to read env. A check that failed here would be unusable.
  const { run } = await fixture({
    "main.js":
      "export function getEnv(n) {\n" +
      "  return typeof process !== 'undefined' && process.env ? process.env[n] : undefined;\n" +
      "}\n",
  });
  assert.deepEqual((await run()).processReads, []);
});

test("topLevelProcessReads ignores a read nested in a block", () => {
  const code = "function f() {\n  const x = process.env.A;\n}\n";
  assert.deepEqual(topLevelProcessReads(code), []);
});

test("topLevelProcessReads catches one at depth zero", () => {
  // The pair for the test above -- "always return []" must not pass both.
  const hits = topLevelProcessReads("const x = process.env.A;\n");
  assert.equal(hits.length, 1);
  assert.equal(hits[0].line, 1);
});

test("a property named env on another object is not a process read", () => {
  // `config.process.env` and `this.process.env` are not the global.
  assert.deepEqual(topLevelProcessReads("const x = config.process.env;\n"), []);
});

// ---- the size budgets ------------------------------------------------------
//
// Two of them, and the tests are shaped to prove they are two: a chunk that
// is over one and under the other must pass or fail according to WHICH graph
// it sits in, never according to its size alone.

/** Generated, not committed: a real 400kB fixture in the repo would itself be
 *  the thing the budget exists to prevent. */
const blob = (bytes) => `export const blob = "${"x".repeat(bytes)}";\n`;

test("a bundle over the shell budget fails the build", async () => {
  const { run } = await fixture({ "main.js": blob(SHELL_BUDGET_BYTES + 1024) });
  const report = await run();
  assert.ok(report.shellBytes > SHELL_BUDGET_BYTES);
  assert.ok(report.problems.some((p) => /shell budget/.test(p)), report.problems.join("\n"));
});

test("a small bundle is within budget", async () => {
  const { run } = await fixture({ "main.js": "export const a = 1;\n" });
  const report = await run();
  assert.ok(report.shellBytes < SHELL_BUDGET_BYTES);
  assert.deepEqual(report.problems, []);
});

test("a chunk behind an import() is charged to the LAZY budget, not the shell", async () => {
  // Over the shell budget, under the lazy one, reached only through import():
  // this must PASS. It is the whole point of splitting -- the engine is far
  // larger than the shell is allowed to be, and that is fine because nobody
  // pays for it before first paint. One budget could not say this.
  const { runSplit } = await fixture({
    "main.js": "export const load = () => import('./big.js');\n",
    "big.js": blob(SHELL_BUDGET_BYTES + 100 * 1024),
  });
  const report = await runSplit();
  assert.ok(report.shellBytes < SHELL_BUDGET_BYTES, `shell is ${report.shellBytes}`);
  assert.ok(report.lazyBytes > SHELL_BUDGET_BYTES, "the lazy side really is over the shell budget");
  assert.ok(report.lazyBytes < LAZY_BUDGET_BYTES);
  assert.deepEqual(report.problems, [], report.problems.join("\n"));
});

test("the same chunk imported STATICALLY lands in the shell and fails", async () => {
  // The pair, and the regression splitting is most likely to suffer: someone
  // turns an `import()` into an `import`, every byte moves to first paint, and
  // the only visible symptom is a slower cold start. The gate is the symptom.
  const { runSplit } = await fixture({
    "main.js": "import { blob } from './big.js';\nexport const n = blob.length;\n",
    "big.js": blob(SHELL_BUDGET_BYTES + 100 * 1024),
  });
  const report = await runSplit();
  assert.ok(report.shellBytes > SHELL_BUDGET_BYTES);
  assert.equal(report.lazyBytes, 0, "nothing is lazy when nothing is behind an import()");
  assert.ok(report.problems.some((p) => /shell budget/.test(p)), report.problems.join("\n"));
});

test("lazy chunks over the LAZY allowance fail the build", async () => {
  // Lazy is deferred, not free: whoever picks the engine pays for all of it.
  // So it has a ceiling of its own, and this is the test that says the ceiling
  // exists -- as opposed to "lazy bytes are simply not counted".
  const { runSplit } = await fixture({
    "main.js": "export const load = () => import('./huge.js');\n",
    "huge.js": blob(LAZY_BUDGET_BYTES + 1024),
  });
  const report = await runSplit();
  assert.ok(report.shellBytes < SHELL_BUDGET_BYTES, "the shell is still tiny");
  assert.ok(report.lazyBytes > LAZY_BUDGET_BYTES);
  assert.ok(report.problems.some((p) => /lazy budget/.test(p)), report.problems.join("\n"));
  assert.ok(!report.problems.some((p) => /shell budget/.test(p)), "and it is the LAZY budget that named it");
});

// ---- the helpers ------------------------------------------------------------

test("forbiddenAmong matches a builtin submodule path", () => {
  // `fs/promises` is `fs`. Splitting on the slash is what catches it.
  assert.deepEqual(forbiddenAmong(["fs/promises"]), ["fs/promises"]);
  assert.deepEqual(forbiddenAmong(["lodash/merge"]), []);
});

test("the forbidden list covers what praisonai-ts actually imports", () => {
  // Anchored to the real finding rather than to a general list: these two are
  // on the Agent import graph today.
  assert.ok(FORBIDDEN_BUILTINS.includes("crypto"));
  assert.ok(FORBIDDEN_BUILTINS.includes("events"));
});

test("unresolvedBareImports ignores relative imports", () => {
  const metafile = {
    inputs: {
      "a.js": { imports: [{ path: "./b.js", external: false }, { path: "crypto", external: true }] },
    },
  };
  assert.deepEqual(unresolvedBareImports(metafile), ["crypto"]);
});

// ---- static vs dynamic -----------------------------------------------------

test("a STATIC builtin import is fatal", async () => {
  const { run } = await fixture({
    "main.js": "import { randomUUID } from 'crypto';\nexport const id = randomUUID();\n",
  });
  const report = await run();
  assert.deepEqual(report.fatal, ["crypto"]);
  assert.deepEqual(report.lazy, []);
  assert.ok(report.problems.length > 0);
});

test("a DYNAMIC builtin import is reported but not fatal", async () => {
  // The real case this exists for: praisonai-ts's createCLIApprovalPrompt does
  // `await import('readline')` inside the handler. It is CLI-only by name and
  // contract, so on a phone that function is never called. Failing the build
  // would force a shim for a code path that cannot be taken -- which is how a
  // gate starts getting worked around instead of fixed.
  const { run } = await fixture({
    "main.js": "export async function prompt() {\n  const rl = await import('readline');\n  return rl;\n}\n",
  });
  const report = await run();
  assert.deepEqual(report.fatal, []);
  assert.deepEqual(report.lazy, ["readline"]);
  assert.deepEqual(report.problems, [], "a lazy builtin must not fail the build");
});

test("a builtin imported both ways is fatal", async () => {
  // One static import anywhere is import-time fatal, whatever else is true.
  const { run } = await fixture({
    "main.js": "import 'crypto';\nexport const f = async () => import('crypto');\n",
  });
  const report = await run();
  assert.deepEqual(report.fatal, ["crypto"]);
});

test("classifyBareImports labels each kind", () => {
  const metafile = {
    inputs: {
      "a.js": {
        imports: [
          { path: "crypto", external: true, kind: "import-statement" },
          { path: "readline", external: true, kind: "dynamic-import" },
          { path: "./local.js", external: false, kind: "import-statement" },
        ],
      },
    },
  };
  const found = classifyBareImports(metafile);
  assert.equal(found.get("crypto"), "static");
  assert.equal(found.get("readline"), "dynamic");
  assert.equal(found.has("./local.js"), false);
});

test("a single fatal problem makes a bundle unshippable", () => {
  // `problems.length > 0` -> `> 1` in build-webview.mjs survived: ONE fatal
  // problem -- a bare external, a forbidden builtin, a top-level process.env
  // read -- no longer failed the build. It took two to be noticed, and the
  // whole point of the gate is that one is enough.
  //
  // This calls the REAL predicate. Re-implementing the comparison inline would
  // prove only that a predicate of that shape works, not that the CLI still
  // contains it -- which is the distinction this package keeps being bitten by.
  assert.equal(isShippable({ problems: [] }), true, "a clean bundle ships");
  assert.equal(isShippable({ problems: ["one fatal problem"] }), false, "one problem is enough");
  assert.equal(isShippable({ problems: ["a", "b"] }), false);
});

test("a relative import that is external is not reported as a bare module", () => {
  // Dropping `imported.path.startsWith(".")` survived. A relative path marked
  // external then enters the bare map under the name "./chunk", and the gate
  // starts reporting a module that does not exist -- or, worse, one whose
  // first path segment collides with a forbidden builtin name.
  const bare = classifyBareImports({
    inputs: {
      "app/src/main.ts": {
        imports: [
          { path: "./chunk.js", external: true, kind: "import-statement" },
          { path: "node:crypto", external: true, kind: "import-statement" },
        ],
      },
    },
  });
  assert.deepEqual([...bare.keys()], ["crypto"], "only the bare specifier is bare");
});

test("the shipping bundle resolves everything it imports", async () => {
  // The positive control, and the one that would actually catch a regression:
  // the real app entry, through the real gate, in the real split shape.
  const outdir = mkdtempSync(join(tmpdir(), "ship-"));
  const report = await bundle({ entry: "app/src/main.ts", outdir, write: false });

  assert.deepEqual(report.unresolved, [], `the shipped bundle must resolve everything: ${report.unresolved}`);
  assert.equal(isShippable(report), true, report.problems.join("\n"));
});

// ---- provider packages are the HOST's, not the bundle's ---------------------

test("no AI SDK provider package is bundled into the shipping app", async () => {
  // The headroom this asserts was reclaimed, not granted. `llm/embeddings.ts`
  // named `@ai-sdk/openai`, `@ai-sdk/google` and `@ai-sdk/cohere` in three
  // LITERAL `import()` calls, so esbuild emitted all three as chunks: 326.7kB
  // of the 1600kB lazy budget, for an embedding path no mobile screen calls and
  // that could not have loaded a provider anyway -- every OTHER provider goes
  // through provider-map.ts's computed `import(providerInfo.package)`, which a
  // webview has no resolver for.
  //
  // Without this test the next literal `import('@ai-sdk/anything')` upstream
  // costs 100-170kB in silence until the budget trips, at which point the
  // cheapest-looking fix is to raise the budget rather than find the import.
  const outdir = mkdtempSync(join(tmpdir(), "providers-"));
  const report = await bundle({ entry: "app/src/main.ts", outdir, write: false });
  const shipped = bundledPackages(report.metafile);

  // The whole `@ai-sdk/*` namespace minus `ai`'s own internals, so a new
  // provider upstream is covered without a second edit here -- not a four-name
  // allowlist that `@ai-sdk/mistral` and friends would walk straight past.
  const smuggled = bundledHostLoadedProviders(report.metafile);
  assert.deepEqual(
    smuggled,
    [],
    `these are loaded by the HOST through provider-map.ts's registry and cannot resolve in a ` +
    `webview, so bundling them is pure weight: ${smuggled.join(", ")}. ` +
    `Look for a LITERAL await import('<the package>') on praisonai-ts's Agent graph.`,
  );

  // The pair, so "nothing was found" cannot mean "nothing was looked at": the
  // packages `ai` itself is built from ARE expected, and their presence proves
  // bundledPackages reads a graph that really contains @ai-sdk scopes.
  assert.ok(
    shipped.includes("@ai-sdk/provider-utils"),
    `expected ai's own @ai-sdk/* internals in the bundle; got ${shipped.join(", ")}`,
  );
});

test("a literal import of a provider package IS reported -- the pair", async () => {
  // Non-vacuity for the test above, driven through the real bundler. A
  // `bundledPackages` that returned [] for everything, or a filter that never
  // matched, would pass it forever; here the identical check must FAIL.
  //
  // The fixture names `@ai-sdk/mistral` ON PURPOSE: it was never in the old
  // four-name allowlist, so this test is also the proof that the namespace rule
  // catches a provider the hand-kept list would have missed.
  const dir = mkdtempSync(join(tmpdir(), "smuggle-"));
  mkdirSync(join(dir, "node_modules/@ai-sdk/mistral"), { recursive: true });
  writeFileSync(
    join(dir, "node_modules/@ai-sdk/mistral/package.json"),
    JSON.stringify({ name: "@ai-sdk/mistral", version: "0.0.0", main: "index.js" }),
  );
  writeFileSync(join(dir, "node_modules/@ai-sdk/mistral/index.js"), "export const createMistral = () => ({});");
  writeFileSync(join(dir, "main.js"), "export const go = async () => (await import('@ai-sdk/mistral')).createMistral();");
  try {
    const report = await bundle({ entry: join(dir, "main.js"), outdir: join(dir, "out"), write: false });
    const smuggled = bundledHostLoadedProviders(report.metafile);
    assert.ok(
      smuggled.includes("@ai-sdk/mistral"),
      `a literal import() of a provider must be seen in the bundle; got ${smuggled.join(", ")}`,
    );
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("the provider gate is the @ai-sdk namespace minus ai's own internals", () => {
  // The rule in one place, so a future edit to either side is caught here
  // rather than in a bundle run. Providers -- named and unnamed -- are
  // host-loaded; the three packages `ai` is built from are not.
  assert.ok(isHostLoadedAISDKProvider("@ai-sdk/openai"));
  assert.ok(isHostLoadedAISDKProvider("@ai-sdk/mistral"), "a provider absent from any hand list is still covered");
  assert.ok(isHostLoadedAISDKProvider("@ai-sdk/groq"));
  for (const internal of AI_INTERNAL_AI_SDK_PACKAGES) {
    assert.equal(isHostLoadedAISDKProvider(internal), false, `${internal} is part of ai, not a provider`);
  }
  assert.equal(isHostLoadedAISDKProvider("ai"), false, "ai itself is the adapter, not a provider");
  assert.equal(isHostLoadedAISDKProvider("zod"), false, "a non-@ai-sdk package is not a provider");
});

test("an unresolvable import fails the gate, with the package named", async () => {
  // Driven through the REAL bundler against a real unresolvable specifier,
  // rather than a hand-built report -- the check has to survive esbuild's
  // actual externals behaviour, not my model of it.
  const dir = mkdtempSync(join(tmpdir(), "unres-"));
  const entry = join(dir, "probe.ts");
  writeFileSync(entry, 'import x from "a-package-that-is-not-installed";\nexport const y = x;\n');

  const report = await bundle({ entry, outfile: join(dir, "o.js"), write: false });

  assert.equal(isShippable(report), false, "an unresolvable import must not be shippable");
  assert.ok(
    report.unresolved.includes("a-package-that-is-not-installed"),
    `it must be listed: ${JSON.stringify(report.unresolved)}`,
  );
  assert.match(report.problems.join("\n"), /could not resolve/);
  assert.match(report.problems.join("\n"), /a-package-that-is-not-installed/, "and named in the message");
});

test("a bare import that IS installed is not reported unresolvable", async () => {
  // The correction. The first version of this check asked "did it stay
  // external?" -- which is true of every bare import, because the plugin
  // externalises them all on purpose so builtins surface in the metafile. So
  // it flagged installed, resolvable packages, and only passed because the
  // shipped bundle happens to have no bare imports at all.
  //
  // The probe is `@ai-sdk/provider`: on praisonai/mobile's graph, 6kB, and
  // browser-clean, so the gate's other checks stay out of the way. It used to
  // be `esbuild`, which is now BUNDLED rather than left external -- and
  // bundling esbuild's Node-only lib drags in `fs`, `child_process` and an
  // optional `pnpapi`, so the probe failed the gate for reasons that had
  // nothing to do with resolution. The declared deps all drag in zod's 426kB,
  // which trips the shell budget instead: same wrong reason, other side.
  //
  // The probe lives INSIDE the package, because resolution is relative to the
  // entry: a temp-directory entry has no node_modules above it, so everything
  // would look missing and the test would pass for the wrong reason. The real
  // app entry is inside the package too.
  const entry = join(import.meta.dirname, ".resolvable-probe.ts");
  writeFileSync(entry, 'import * as p from "@ai-sdk/provider";\nexport const x = p;\n');
  try {
    const report = await bundle({
      entry,
      outfile: join(mkdtempSync(join(tmpdir(), "installed-")), "o.js"),
      write: false,
    });
    assert.deepEqual(report.unresolved, [], "an installed package resolves");
    assert.equal(isShippable(report), true, report.problems.join("\n"));
  } finally {
    rmSync(entry, { force: true });
  }
});

test("a LAZY Node builtin is still allowed -- the pair", async () => {
  // The unresolved check must not swallow the static-vs-dynamic distinction
  // this file's header is built on: a dynamic `await import("readline")` in a
  // CLI-only path is unavailable on a phone, not fatal.
  const dir = mkdtempSync(join(tmpdir(), "lazy-"));
  const entry = join(dir, "probe.ts");
  writeFileSync(entry, 'export async function cli() { return await import("readline"); }\n');

  const report = await bundle({ entry, outfile: join(dir, "o.js"), write: false });

  assert.deepEqual(report.unresolved, [], "a builtin is classified as a builtin, not as unresolved");
  assert.deepEqual(report.fatal, [], "and a dynamic one is not fatal");
});

// ---- the CLI-only externals ------------------------------------------------

test("a CLI-only package imported STATICALLY fails the gate", async () => {
  // chalk, boxen, ora, cli-table3 and figlet are left external on purpose,
  // and an external reached by a static import is import-time fatal -- the
  // same blank screen as a builtin, with neither of the checks above able to
  // see it: it is not a builtin, and on the build machine it resolves.
  //
  // Inside the package, for the same reason as the resolvable probe: chalk
  // has to actually resolve for this to be about the static/dynamic line.
  const entry = join(import.meta.dirname, ".cli-static-probe.ts");
  writeFileSync(entry, 'import chalk from "chalk";\nexport const x = chalk;\n');
  try {
    const report = await bundle({
      entry,
      outfile: join(mkdtempSync(join(tmpdir(), "cli-")), "o.js"),
      write: false,
    });
    assert.deepEqual(report.cliStatic, ["chalk"]);
    assert.equal(isShippable(report), false, "a static external must not ship");
    assert.match(report.problems.join("\n"), /CLI-only[^\n]*STATICALLY[^\n]*chalk/);
  } finally {
    rmSync(entry, { force: true });
  }
});

test("a CLI-only package behind an import() is allowed -- the pair", async () => {
  // This is how praisonai's pretty-logger reaches them, and why they can be
  // external at all: a rejected dynamic import on a path a phone never takes.
  const entry = join(import.meta.dirname, ".cli-dynamic-probe.ts");
  writeFileSync(entry, 'export const pretty = async () => import("chalk");\n');
  try {
    const report = await bundle({
      entry,
      outfile: join(mkdtempSync(join(tmpdir(), "cli-")), "o.js"),
      write: false,
    });
    assert.ok(report.bare.includes("chalk"), "it is still external, and still visible");
    assert.deepEqual(report.cliStatic, []);
    assert.equal(isShippable(report), true, report.problems.join("\n"));
  } finally {
    rmSync(entry, { force: true });
  }
});
