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
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { bundle, TARGETS, ANDROID_WEBVIEW_FLOOR } from "./bundle.mjs";

const conf = JSON.parse(
  readFileSync(join(import.meta.dirname, "../src-tauri/tauri.conf.json"), "utf8"),
);
const target = (prefix) => TARGETS.find((t) => t.startsWith(prefix));

test("the Chrome target matches the Android minSdkVersion the app declares", () => {
  const minSdk = conf.bundle.android.minSdkVersion;
  const required = ANDROID_WEBVIEW_FLOOR[minSdk];
  assert.ok(
    required !== undefined,
    `minSdkVersion ${minSdk} has no WebView floor recorded in bundle.mjs -- add one rather than guessing`,
  );
  assert.equal(
    target("chrome"),
    required,
    `minSdkVersion ${minSdk} ships a WebView at ${required}; the bundle targets ${target("chrome")}`,
  );
});

test("the Safari target matches the iOS minimum the app declares", () => {
  // This pair already agreed. Asserted so it keeps agreeing, and so the test
  // above is not the only thing holding the relationship.
  const major = Number(String(conf.bundle.iOS.minimumSystemVersion).split(".")[0]);
  assert.equal(target("safari"), `safari${major}`, "iOS 16 ships Safari 16");
});

test("the shipped bundle contains no syntax the floor cannot parse", async () => {
  // The assertion that would actually have caught it. Optional chaining and
  // nullish coalescing are Chrome 80; logical assignment is Chrome 85. Any of
  // them at a chrome58 floor is a blank screen.
  //
  // Built here through the same bundle() at the same TARGETS the ship path
  // uses, rather than read from a pre-built dist/app.js: the `check` job runs
  // `npm test` without a prior `npm run build`, so a disk read would be a test
  // that can only pass by accident of build order. Same entry, same targets,
  // same output -- with no ordering dependency.
  const out = join(mkdtempSync(join(tmpdir(), "floor-")), "app.js");
  const { code } = await bundle({
    entry: join(import.meta.dirname, "../app/src/main.ts"),
    outfile: out,
    write: false,
  });
  for (const [name, pattern] of [
    ["optional chaining", /\?\./],
    ["nullish coalescing", /\?\?[^=]/],
    ["logical assignment", /\?\?=|\|\|=|&&=/],
  ]) {
    assert.doesNotMatch(code, pattern, `${name} is post-Chrome-58 and will not parse on the floor`);
  }
});
