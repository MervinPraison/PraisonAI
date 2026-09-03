/**
 * The esbuild target, checked against the platform minimums the app declares.
 *
 * These are two numbers in two files that must agree, and nothing linked them.
 * `tools/bundle.mjs` said `chrome108` while `tauri.conf.json` declared
 * `minSdkVersion: 26` -- Android 8.0, whose factory WebView is Chrome ~58.
 *
 * The failure is silent and total: `index.html` loads the bundle as
 * `<script type="module">`, so post-Chrome-58 syntax is a PARSE error and the
 * module body never runs. `installCrashHandler` is imported by that same
 * module, so it never installs -- a blank white screen, no error surface, no
 * telemetry, on exactly the devices (AOSP, Play-less, long-offline) that a
 * WebView floor exists to protect.
 *
 * The in-process engine is a chunk on this graph now, and it took the floor
 * only once praisonai-ts stopped putting top-level await on it (praisonai-ts
 * #4720) -- esbuild cannot lower that, so below chrome89 there was no bundle
 * at all. `praisonai` is a `file:` link to ../praisonai-ts, so the build
 * measured here is the one with that fix in it. One construct is kept above
 * the floor on purpose, `import()` (Chrome 63), because lowering it undoes
 * the split; the last two tests measure exactly that and pin the override
 * that prevents it.
 */
import test from "node:test";
import * as esbuild from "esbuild";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import {
  bundle,
  chromeMajor,
  praisonaiRoot,
  ANDROID_WEBVIEW_FLOOR,
  DECLARED_CHROME_FLOOR,
  SHELL_BUDGET_BYTES,
  SPLIT_MIN_CHROME,
  TARGETS,
} from "./bundle.mjs";

const conf = JSON.parse(
  readFileSync(join(import.meta.dirname, "../src-tauri/tauri.conf.json"), "utf8"),
);
const target = (prefix) => TARGETS.find((t) => t.startsWith(prefix));
const appEntry = join(import.meta.dirname, "../app/src/main.ts");
const scratch = () => mkdtempSync(join(tmpdir(), "floor-"));

test("the Chrome target matches the Android minSdkVersion the app declares", () => {
  const minSdk = conf.bundle.android.minSdkVersion;
  const floor = ANDROID_WEBVIEW_FLOOR[minSdk];
  assert.ok(
    floor !== undefined,
    `minSdkVersion ${minSdk} has no WebView floor recorded in bundle.mjs -- add one rather than guessing`,
  );
  assert.equal(DECLARED_CHROME_FLOOR, floor, "bundle.mjs derives the floor from the same config this test reads");
  assert.equal(
    target("chrome"),
    floor,
    `minSdkVersion ${minSdk} ships a WebView at ${floor}; the bundle targets ${target("chrome")}`,
  );
});

test("the Safari target matches the iOS minimum the app declares", () => {
  // This pair already agreed. Asserted so it keeps agreeing, and so the test
  // above is not the only thing holding the relationship.
  const major = Number(String(conf.bundle.iOS.minimumSystemVersion).split(".")[0]);
  assert.equal(target("safari"), `safari${major}`, "iOS 16 ships Safari 16");
});

test("the shipped bundle -- every chunk, engine included -- has no syntax the floor cannot parse", async () => {
  // The assertion that would actually have caught it. Optional chaining and
  // nullish coalescing are Chrome 80, logical assignment 85, async functions
  // 55, class fields 72: any of them at a chrome58 floor is a blank screen.
  //
  // Checked with a PARSER, not a regex: a `?.` inside a string or a regex
  // literal is not optional chaining, and zod has both. esbuild lowers what a
  // target lacks, so transforming a chunk AT the floor is a no-op exactly
  // when the chunk is already floor-clean -- and a transform at `esnext` is
  // the control that says what "no-op" prints as. One printer quirk has to be
  // held still for that: at a target with template literals esbuild prints
  // a string containing both quote characters with backticks, which is not
  // syntax in the chunk but a choice in the printer (measured: 12 lines, all
  // of them strings). The one construct the build keeps above the floor on
  // purpose, `import()`, is kept here too.
  //
  // Built here through the same bundle() at the same TARGETS the ship path
  // uses, rather than read from a pre-built dist/: the `check` job runs
  // `npm test` without a prior `npm run build`, so a disk read would be a test
  // that can only pass by accident of build order. WRITTEN, so every chunk
  // can be read back -- the engine's chunks are the ones that only recently
  // became buildable at this floor, and the check must include them.
  const outdir = scratch();
  const report = await bundle({ entry: appEntry, outdir });
  assert.deepEqual(report.problems, [], report.problems.join("\n"));
  assert.ok(report.lazyBytes > 0, "the engine must be in this build for the check to mean anything");

  const upstream = praisonaiRoot();
  const engineChunks = Object.entries(report.metafile.outputs)
    .filter(([, out]) => Object.keys(out.inputs ?? {}).some((i) => resolve(process.cwd(), i).startsWith(upstream + "/")))
    .map(([p]) => p.split("/").pop());
  assert.ok(engineChunks.length > 0, "and praisonai must be among the chunks checked");

  const chunks = readdirSync(outdir).filter((f) => f.endsWith(".js"));
  assert.ok(chunks.length > 1, "a split build writes more than the entry");
  const print = (code, target) => esbuild.transformSync(code, {
    target: [target], format: "esm", supported: { "dynamic-import": true, "template-literal": false },
  }).code;
  for (const name of chunks) {
    const code = readFileSync(join(outdir, name), "utf8");
    assert.equal(
      print(code, target("chrome")),
      print(code, "esnext"),
      `${name}: lowering it to ${target("chrome")} changed it, so it carries syntax the floor cannot parse`,
    );
  }
});

test("import() survives at the floor, by an override that is load-bearing", async () => {
  // What ships: the entry keeps its `import("./chunk-…")`, and the engine is
  // behind it. Then the same build with esbuild left to its own table at the
  // same target: the import is lowered, nothing is lazy, and the shell budget
  // fails -- which is what the override in bundle.mjs exists to prevent, and
  // the reason removing it cannot be silent.
  const kept = await bundle({ entry: appEntry, outdir: scratch(), write: false });
  assert.match(kept.code, /import\("\.\/chunk-[A-Z0-9]+\.js"\)/, "the entry must fetch the engine lazily");
  assert.ok(kept.lazyBytes > 0);
  assert.deepEqual(kept.problems, [], kept.problems.join("\n"));

  const lowered = await bundle({ entry: appEntry, outdir: scratch(), write: false, keepDynamicImport: false });
  assert.doesNotMatch(lowered.code, /import\("\.\/chunk-/, "without the override the floor lowers import()");
  assert.equal(lowered.lazyBytes, 0, "and nothing is lazy any more");
  assert.ok(lowered.shellBytes > SHELL_BUDGET_BYTES, "so the whole engine is in the shell");
  assert.ok(lowered.problems.some((p) => /shell budget/.test(p)), "which the gate names");
});

test("SPLIT_MIN_CHROME is where esbuild leaves import() alone -- measured, one below and at", async () => {
  // The number behind the override, pinned to esbuild's behaviour rather than
  // to a browser table someone read once. Below it the same source produces
  // no lazy chunk at all; at it, the chunk stays behind the import().
  const dir = mkdtempSync(join(tmpdir(), "split-floor-"));
  writeFileSync(join(dir, "main.js"), 'export const load = () => import("./lazy.js");\n');
  writeFileSync(join(dir, "lazy.js"), 'export const lazy = "x".repeat(2000);\n');
  const at = (t) => bundle({
    entry: join(dir, "main.js"), outdir: join(dir, "out-" + t), write: false, targets: [t], keepDynamicImport: false,
  });

  const below = await at(`chrome${chromeMajor(SPLIT_MIN_CHROME) - 1}`);
  assert.equal(below.lazyBytes, 0, "one below: import() is lowered and nothing is lazy");
  assert.ok(below.eager.size > 1, "and what would have been a lazy chunk is eager");

  const here = await at(SPLIT_MIN_CHROME);
  assert.ok(here.lazyBytes > 0, "at it: the chunk stays behind the import()");
  assert.deepEqual([...here.eager], ["app.js"]);
  assert.ok(chromeMajor(SPLIT_MIN_CHROME) > chromeMajor(DECLARED_CHROME_FLOOR), "which is above the declared floor -- the override is not decorative");
});
