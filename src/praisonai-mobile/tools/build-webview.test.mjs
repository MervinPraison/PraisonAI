import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const SCRIPT = join(import.meta.dirname, "build-webview.mjs");
const REAL_SW = readFileSync(join(import.meta.dirname, "../app/sw.js"), "utf8");

/** Everything a build emits, relative to dist/. */
const SHIPPED = [
  "index.html",
  "app.css",
  "app.js",
  "manifest.webmanifest",
  "register-sw.js",
  "boot-guard.js",
  "sw.js",
  "icons/a.png",
  "icons/b.png",
];

/** A minimal package tree the real build script can be pointed at. The
 * manifest and sw.js are the real shapes (two icons, both tokens) so the
 * build's handling of them is exercised, not a stand-in's. */
function fixture(main) {
  const dir = mkdtempSync(join(tmpdir(), "webview-build-"));
  mkdirSync(join(dir, "app/src"), { recursive: true });
  mkdirSync(join(dir, "src-tauri/icons"), { recursive: true });
  writeFileSync(join(dir, "app/index.html"), "<!doctype html><div id=root></div>\n");
  writeFileSync(join(dir, "app/app.css"), ":root { color: red }\n");
  writeFileSync(join(dir, "app/register-sw.js"), "// register\n");
  writeFileSync(join(dir, "app/boot-guard.js"), "// boot guard\n");
  writeFileSync(join(dir, "app/sw.js"), REAL_SW);
  writeFileSync(
    join(dir, "app/manifest.webmanifest"),
    JSON.stringify({ icons: [{ src: "./icons/a.png" }, { src: "./icons/b.png" }] }),
  );
  writeFileSync(join(dir, "src-tauri/icons/a.png"), "PNG-A");
  writeFileSync(join(dir, "src-tauri/icons/b.png"), "PNG-B");
  writeFileSync(join(dir, "app/src/main.ts"), main);
  return dir;
}

const build = (dir) => spawnSync(process.execPath, [SCRIPT, dir], { encoding: "utf8" });
const CLEAN = "export const hi: string = 'hi';\ndocument.title = hi;\n";

test("a shippable app builds, and dist carries every file the web page needs", () => {
  const dir = fixture(CLEAN);
  const r = build(dir);
  assert.equal(r.status, 0, `a clean app must build:\n${r.stdout}${r.stderr}`);
  for (const f of SHIPPED) {
    assert.ok(existsSync(join(dir, "dist", f)), `dist/${f} must exist`);
  }
  assert.equal(readFileSync(join(dir, "dist/icons/a.png"), "utf8"), "PNG-A", "icons come from src-tauri/icons");
});

test("the service worker precaches exactly what was built, under a build-derived cache name", () => {
  const dir = fixture(CLEAN);
  assert.equal(build(dir).status, 0);
  const sw = readFileSync(join(dir, "dist/sw.js"), "utf8");
  assert.doesNotMatch(sw, /__BUILD_ID__|__PRECACHE__/, "no template token may survive into dist");

  const precache = JSON.parse(/const PRECACHE = (\[.*?\]);/s.exec(sw)[1]);
  const shippedExceptSelf = SHIPPED.filter((f) => f !== "sw.js").map((f) => `./${f}`);
  assert.deepEqual([...precache].sort(), [...shippedExceptSelf].sort(), "precache = built files, minus the worker");

  const name = /const CACHE = "praisonai-mobile-([0-9a-f]{16})";/.exec(sw)?.[1];
  assert.ok(name, "the cache name carries a 16-hex-digit build id");

  // Change one byte of one asset: the cache name must change, or a new build
  // serves the old bytes from the old cache until the user clears site data.
  writeFileSync(join(dir, "app/app.css"), ":root { color: blue }\n");
  assert.equal(build(dir).status, 0);
  const again = /const CACHE = "praisonai-mobile-([0-9a-f]{16})";/.exec(readFileSync(join(dir, "dist/sw.js"), "utf8"))[1];
  assert.notEqual(again, name, "a different asset must yield a different cache name");
});

test("an icon the manifest names but the shell does not have fails the build", () => {
  const dir = fixture(CLEAN);
  writeFileSync(
    join(dir, "app/manifest.webmanifest"),
    JSON.stringify({ icons: [{ src: "./icons/a.png" }, { src: "./icons/missing.png" }] }),
  );
  const r = build(dir);
  assert.notEqual(r.status, 0, "a manifest pointing at a missing icon must not build");
  assert.match(r.stdout + r.stderr, /missing\.png/, "and it must say which icon");
});

test("a stale file from a previous build does not survive into dist", () => {
  // `await rm(dist, ...)` was removable with a green suite, because every test
  // built into a fresh temp directory where dist did not exist yet. On a real
  // machine dist DOES exist -- that is the whole point of a build directory --
  // so a renamed or deleted asset stays in the shipped output forever, and the
  // page keeps loading a file nobody can find in the source any more.
  const dir = fixture(CLEAN);
  mkdirSync(join(dir, "dist/icons"), { recursive: true });
  writeFileSync(join(dir, "dist/left-over.js"), "// from a build two versions ago\n");
  writeFileSync(join(dir, "dist/app.css"), "/* a stale stylesheet */\n");
  writeFileSync(join(dir, "dist/icons/renamed-away.png"), "PNG-OLD");
  writeFileSync(join(dir, "dist/sw.js"), 'const CACHE = "praisonai-mobile-stale";\n');
  writeFileSync(join(dir, "dist/manifest.webmanifest"), '{"name":"stale"}\n');

  const r = build(dir);
  assert.equal(r.status, 0, `${r.stdout}${r.stderr}`);

  assert.equal(existsSync(join(dir, "dist/left-over.js")), false, "a file the build no longer produces must not be shipped");
  assert.equal(existsSync(join(dir, "dist/icons/renamed-away.png")), false, "nor an icon the manifest no longer names");
  assert.match(readFileSync(join(dir, "dist/app.css"), "utf8"), /color: red/, "a file it DOES produce must be the fresh one");
  assert.doesNotMatch(readFileSync(join(dir, "dist/sw.js"), "utf8"), /stale/, "the worker is regenerated, never left over");
  assert.match(readFileSync(join(dir, "dist/manifest.webmanifest"), "utf8"), /icons/, "so is the manifest");
  assert.deepEqual(readdirSync(join(dir, "dist/icons")).sort(), ["a.png", "b.png"], "dist/icons holds the manifest's icons and nothing else");
});

test("an unshippable bundle FAILS the build, it does not merely print", () => {
  // Dropping `process.exit(1)` survived. The problems are reported in full and
  // the process exits 0, so CI publishes a dist/ that throws on the first line
  // a browser evaluates. The message is not the gate; the exit code is.
  const dir = fixture("import { createHash } from 'node:crypto';\ndocument.title = createHash('sha1').digest('hex');\n");
  const r = build(dir);
  const out = r.stdout + r.stderr;
  assert.notEqual(r.status, 0, `an unshippable bundle was reported and then shipped:\n${out}`);
  assert.match(out, /crypto/, "and it must say which module made it unshippable");
  assert.equal(existsSync(join(dir, "dist/sw.js")), false, "and no worker is written to precache a broken bundle");
});

test("a chunk behind an import() is written beside app.js, where the page can reach it", () => {
  // Splitting emits `import("./chunk-XXXX.js")` inside app.js, and a browser
  // resolves that against app.js's own URL. index.html sits in the same
  // directory and loads `./app.js`, so "beside app.js" is "beside the page".
  // A build that put the chunks anywhere else -- an outdir of their own, say
  // -- would pass every gate and 404 on the first lazy feature.
  const dir = fixture("export const load = () => import('./lazy.ts');\ndocument.title = 'x';\n");
  writeFileSync(join(dir, "app/src/lazy.ts"), "export const lazy: string = 'lazy'.repeat(10);\n");

  const r = build(dir);
  assert.equal(r.status, 0, `${r.stdout}${r.stderr}`);

  const app = readFileSync(join(dir, "dist/app.js"), "utf8");
  const refs = [...app.matchAll(/import\("\.\/(chunk-[A-Z0-9]+\.js)"\)/g)].map((m) => m[1]);
  assert.ok(refs.length > 0, "the lazy module must have become a chunk, referenced relatively");
  for (const ref of refs) {
    assert.ok(existsSync(join(dir, "dist", ref)), `${ref} must be written beside app.js`);
  }
  assert.ok(existsSync(join(dir, "dist/index.html")), "and the page is in that same directory");
});

test("the worker precaches the EAGER chunks and leaves the lazy ones to be fetched", () => {
  // The regression this pins, in full: code splitting gives app.js a chunk it
  // imports STATICALLY whenever a module is shared between the entry and a
  // lazy branch. The precache list was hand-written -- index.html, app.css,
  // app.js and the assets -- so that sibling was not in it. The app rendered
  // perfectly online, and an offline reload got a cache miss on a file app.js
  // cannot start without. Nothing in Node noticed; only a browser did.
  //
  // The other half matters just as much: the LAZY chunks must stay OUT. They
  // are why `splitting` is on at all, and precaching them would make install
  // download the whole engine on first paint.
  const dir = fixture(
    "import { shared } from './shared.ts';\nexport const load = () => import('./lazy.ts');\ndocument.title = shared;\n",
  );
  writeFileSync(join(dir, "app/src/shared.ts"), "export const shared: string = 'shared'.repeat(40);\n");
  writeFileSync(
    join(dir, "app/src/lazy.ts"),
    "import { shared } from './shared.ts';\nexport const lazy: string = shared + 'lazy'.repeat(40);\n",
  );

  const r = build(dir);
  assert.equal(r.status, 0, `${r.stdout}${r.stderr}`);

  const sw = readFileSync(join(dir, "dist/sw.js"), "utf8");
  const precache = JSON.parse(/const PRECACHE = (\[.*?\]);/s.exec(sw)[1]);
  const app = readFileSync(join(dir, "dist/app.js"), "utf8");

  // Read eager and lazy off app.js itself rather than trusting the build's
  // own report: a static `from "./chunk-X.js"` is needed to boot, a
  // `import("./chunk-X.js")` is not.
  const eager = [...app.matchAll(/(?:from|import)\s*"\.\/(chunk-[A-Z0-9]+\.js)"/g)].map((m) => m[1]);
  const lazy = [...app.matchAll(/import\("\.\/(chunk-[A-Z0-9]+\.js)"\)/g)].map((m) => m[1]);
  assert.ok(eager.length > 0, "this fixture must produce a statically imported chunk, or it proves nothing");
  assert.ok(lazy.length > 0, "and a lazily imported one");

  for (const name of eager) {
    assert.ok(precache.includes(`./${name}`), `${name} is imported statically by app.js, so it must be precached`);
  }
  for (const name of lazy) {
    assert.ok(!precache.includes(`./${name}`), `${name} is only behind import(); precaching it defeats the split`);
  }
  assert.ok(precache.includes("./app.js"), "and the entry itself is precached");
});
