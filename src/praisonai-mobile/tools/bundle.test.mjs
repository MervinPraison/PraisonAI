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
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  bundle,
  forbiddenAmong,
  topLevelProcessReads,
  unresolvedBareImports,
  classifyBareImports,
  FORBIDDEN_BUILTINS,
  SIZE_BUDGET_BYTES, isShippable } from "./bundle.mjs";

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

// ---- the size budget -------------------------------------------------------

test("a bundle over budget fails the build", async () => {
  // Generated, not committed: a real 400kB fixture in the repo would itself be
  // the thing the budget exists to prevent.
  const filler = `export const blob = "${"x".repeat(SIZE_BUDGET_BYTES + 1024)}";\n`;
  const { run } = await fixture({ "main.js": filler });
  const report = await run();
  assert.ok(report.bytes > SIZE_BUDGET_BYTES);
  assert.ok(report.problems.some((p) => /budget/.test(p)));
});

test("a small bundle is within budget", async () => {
  const { run } = await fixture({ "main.js": "export const a = 1;\n" });
  const report = await run();
  assert.ok(report.bytes < SIZE_BUDGET_BYTES);
  assert.deepEqual(report.problems, []);
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
