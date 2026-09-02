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
 * TODAY THE TWO NUMBERS DISAGREE AGAIN, ON PURPOSE, AND THE FIRST TEST IS RED.
 * Two things hold the target above the declared floor, and they are not the
 * same kind of thing:
 *
 *  - The ENGINE. `praisonai/mobile` (now a lazily-fetched chunk) carries
 *    top-level await at praisonai@1.7.4 -- an esm shim, since removed upstream
 *    by praisonai-ts PR #4720 but not yet in a release -- which no esbuild
 *    target below chrome89 takes at all. bundle.mjs probes the installed
 *    package for it and raises the target only while it is there, so this
 *    layer clears itself on the version bump. Nobody has to remember.
 *  - The SPLIT. `import()` is Chrome 63; below it esbuild lowers the dynamic
 *    import to a static one and the entire engine lands in the shell
 *    (measured: 1486.8kB against a 400kB budget). No release moves this. A
 *    lazily-loaded engine on a chrome58 floor is not a thing, so this layer
 *    is a minSdkVersion decision, and the first test stays red until it is
 *    made -- one way or the other.
 *
 * Code splitting solved the engine's SIZE (the shell is unchanged at 66kB); it
 * cannot solve either FLOOR. The tests after the first settle what can be
 * settled now: the shell's own syntax is clean at chrome58, the split floor is
 * measured rather than recalled, and the probe agrees with the bundler about
 * exactly which files are in the way.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  bundle,
  chromeMajor,
  maxChrome,
  praisonaiRoot,
  ANDROID_WEBVIEW_FLOOR,
  DECLARED_CHROME_FLOOR,
  ENGINE_FLOOR_BLOCKERS,
  ENGINE_MIN_CHROME,
  SPLIT_MIN_CHROME,
  SPLIT_CHROME_FLOOR,
  TARGETS,
} from "./bundle.mjs";

const conf = JSON.parse(
  readFileSync(join(import.meta.dirname, "../src-tauri/tauri.conf.json"), "utf8"),
);
const target = (prefix) => TARGETS.find((t) => t.startsWith(prefix));
const praisonaiVersion = (() => {
  const root = praisonaiRoot();
  return root === null ? "(not installed)" : JSON.parse(readFileSync(join(root, "package.json"), "utf8")).version;
})();
const appEntry = join(import.meta.dirname, "../app/src/main.ts");
// The seam file itself is the honest entry for "does the engine build": it is
// the one literal `import("praisonai/mobile")` the app makes.
const engineEntry = join(import.meta.dirname, "../engines/src/praisonai-ts/load-agent.ts");
const scratch = () => mkdtempSync(join(tmpdir(), "floor-"));

test("the Chrome target matches the Android minSdkVersion the app declares", () => {
  const minSdk = conf.bundle.android.minSdkVersion;
  const floor = ANDROID_WEBVIEW_FLOOR[minSdk];
  assert.ok(
    floor !== undefined,
    `minSdkVersion ${minSdk} has no WebView floor recorded in bundle.mjs -- add one rather than guessing`,
  );
  assert.equal(DECLARED_CHROME_FLOOR, floor, "bundle.mjs derives the floor from the same config this test reads");
  const actual = target("chrome");
  if (actual === floor) return;

  // They disagree. Say what holds the target up, in terms of what resolves
  // each thing -- so the fix is recognised by the test, not remembered by a
  // person, and so nobody expects the version bump to finish the job alone.
  const reasons = [];
  if (ENGINE_FLOOR_BLOCKERS.length > 0) {
    reasons.push(
      `[clears itself] engine needs ${ENGINE_MIN_CHROME}: top-level await in praisonai/mobile at ` +
      `${SPLIT_CHROME_FLOOR} (${ENGINE_FLOOR_BLOCKERS.join(", ")} -- the esm shim in ` +
      `praisonai@${praisonaiVersion}). Resolved upstream by praisonai-ts PR #4720; needs a praisonai ` +
      `release containing it, then a bump of the pin. Nothing else: bundle.mjs transforms those ` +
      `three files on load and lowers the target itself the moment none carries top-level await.`,
    );
  }
  if (chromeMajor(SPLIT_CHROME_FLOOR) > chromeMajor(floor)) {
    reasons.push(
      `[a decision] the split needs ${SPLIT_MIN_CHROME}: import() is Chrome 63 (measured below -- ` +
      `under it esbuild lowers import() to a static import and the whole engine lands in the shell, ` +
      `~1.4MB against a 400kB budget). No release moves this. Raise minSdkVersion to a level whose ` +
      `WebView has import() -- ANDROID_WEBVIEW_FLOOR records nothing between 26 (${floor}) and ` +
      `30 (${ANDROID_WEBVIEW_FLOOR[30]}); add the level, with evidence -- or give up the split. ` +
      `<script type="module"> is Chrome 61 besides, so nothing on ${floor} ever ran this page.`,
    );
  }
  assert.fail(
    `the Chrome target is ${actual}; tauri.conf.json declares minSdkVersion ${minSdk} (${floor}).\n` +
    reasons.map((r, i) => `  ${i + 1}. ${r}`).join("\n") +
    `\nThis test is red on purpose until the target equals the declared floor, and green by itself the moment it does.`,
  );
});

test("SPLIT_MIN_CHROME is where import() survives -- measured, one below and at", async () => {
  // The split's own floor, pinned to esbuild's behaviour rather than to a
  // browser table someone read once. Below it the same source produces no
  // lazy chunk at all: the dynamic import is lowered to a static one, and
  // everything the page would have fetched later, it fetches first.
  const dir = mkdtempSync(join(tmpdir(), "split-floor-"));
  writeFileSync(join(dir, "main.js"), 'export const load = () => import("./lazy.js");\n');
  writeFileSync(join(dir, "lazy.js"), 'export const lazy = "x".repeat(2000);\n');
  const at = (t) => bundle({ entry: join(dir, "main.js"), outdir: join(dir, "out-" + t), write: false, targets: [t] });

  const below = await at(`chrome${chromeMajor(SPLIT_MIN_CHROME) - 1}`);
  assert.equal(below.lazyBytes, 0, "one below: import() is lowered and nothing is lazy");
  assert.ok(below.eager.size > 1, "and what would have been a lazy chunk is eager");

  const here = await at(SPLIT_MIN_CHROME);
  assert.ok(here.lazyBytes > 0, "at it: the chunk stays behind the import()");
  assert.deepEqual([...here.eager], ["app.js"]);

  assert.equal(SPLIT_CHROME_FLOOR, maxChrome(DECLARED_CHROME_FLOOR, SPLIT_MIN_CHROME), "and the split floor is the higher of the two");
});

test("the Safari target matches the iOS minimum the app declares", () => {
  // This pair already agreed. Asserted so it keeps agreeing, and so the test
  // above is not the only thing holding the relationship.
  const major = Number(String(conf.bundle.iOS.minimumSystemVersion).split(".")[0]);
  assert.equal(target("safari"), `safari${major}`, "iOS 16 ships Safari 16");
});

test("the app SHELL still parses on the declared floor -- only the engine needs more", async () => {
  // Built at the floor tauri.conf.json implies, NOT at TARGETS, with the
  // engine left external -- the one bare import the shell makes. This is the
  // settled half of the conflict above: every byte fetched before first paint
  // is chrome58-clean, so whichever way that decision goes the shell does not
  // move. It is also what keeps the shell honest while TARGETS sits at
  // chrome89, because esbuild would otherwise happily leave `?.` in it.
  //
  // Built here rather than read from dist/: the `check` job runs `npm test`
  // without a prior `npm run build`, so a disk read could only pass by
  // accident of build order.
  const floor = ANDROID_WEBVIEW_FLOOR[conf.bundle.android.minSdkVersion];
  const report = await bundle({
    entry: appEntry,
    outdir: scratch(),
    write: false,
    targets: [target("safari"), floor],
    external: ["praisonai/mobile"],
  });
  assert.deepEqual(report.problems, [], report.problems.join("\n"));
  assert.deepEqual([...report.eager], ["app.js"], "with the engine external, the shell is one file");
  for (const [name, pattern] of [
    ["optional chaining", /\?\./],
    ["nullish coalescing", /\?\?[^=]/],
    ["logical assignment", /\?\?=|\|\|=|&&=/],
  ]) {
    assert.doesNotMatch(report.code, pattern, `${name} is post-Chrome-58 and will not parse on the floor`);
  }
});

test("the floor probe says what the bundler says, in both directions", async () => {
  // ENGINE_FLOOR_BLOCKERS is a cheap per-file transform; this is the real
  // bundle of the real engine entry, and the two must agree. While the shim is
  // present, the floor must refuse the engine for exactly the files the probe
  // named -- a fourth would be a new upstream regression, and it shows up here
  // as a named mismatch rather than a mystery -- and the raised target must
  // take it, at a number that is a minimum and not a round one. Once the shim
  // is gone, the engine builds at the floor and the target is back on it.
  // Either way, nothing about the target is remembered.
  //
  // Probed at the SPLIT floor, not the declared one: that is the lowest target
  // the shipped shape can take at all, so it is the honest question to ask
  // the engine.
  const floor = SPLIT_CHROME_FLOOR;
  const build = (targets) => bundle({ entry: engineEntry, outdir: scratch(), write: false, targets });

  if (ENGINE_FLOOR_BLOCKERS.length === 0) {
    const at = await build([floor]);
    assert.deepEqual(at.problems, [], at.problems.join("\n"));
    assert.ok(at.lazyBytes > 0, "and the engine really is behind the import()");
    assert.equal(target("chrome"), floor, "with nothing blocking, the target is the split floor");
    return;
  }

  let refused;
  try {
    await build([floor]);
    assert.fail(`the probe says ${ENGINE_FLOOR_BLOCKERS.join(", ")} block ${floor}, but the engine built there`);
  } catch (error) {
    if (!Array.isArray(error.errors)) throw error;
    refused = error.errors;
  }
  const named = refused
    .filter((e) => /Top-level await is not available/.test(e.text))
    .map((e) => e.location.file.replace(/^.*\/dist\/esm\//, ""))
    .sort();
  assert.deepEqual(named, [...ENGINE_FLOOR_BLOCKERS].sort(), "the probe and the bundler must name the same files");
  assert.equal(target("chrome"), ENGINE_MIN_CHROME, "and the target is raised to the engine's minimum");

  const below = `chrome${chromeMajor(ENGINE_MIN_CHROME) - 1}`;
  await assert.rejects(
    build([below]),
    /Top-level await is not available/,
    `${below} must still refuse it -- ENGINE_MIN_CHROME is a minimum, not a round number`,
  );
  const at = await build([ENGINE_MIN_CHROME]);
  assert.deepEqual(at.problems, [], at.problems.join("\n"));
  assert.ok(at.lazyBytes > 0, "and the engine really is behind the import()");
});
