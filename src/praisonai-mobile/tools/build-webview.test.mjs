import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const SCRIPT = join(import.meta.dirname, "build-webview.mjs");

/** A minimal package tree the real build script can be pointed at. */
function fixture(main) {
  const dir = mkdtempSync(join(tmpdir(), "webview-build-"));
  mkdirSync(join(dir, "app/src"), { recursive: true });
  writeFileSync(join(dir, "app/index.html"), "<!doctype html><div id=root></div>\n");
  writeFileSync(join(dir, "app/app.css"), ":root { color: red }\n");
  writeFileSync(join(dir, "app/src/main.ts"), main);
  return dir;
}

const build = (dir) => spawnSync(process.execPath, [SCRIPT, dir], { encoding: "utf8" });

test("a shippable app builds, and dist carries the page and the stylesheet", () => {
  const dir = fixture("export const hi: string = 'hi';\ndocument.title = hi;\n");
  const r = build(dir);
  assert.equal(r.status, 0, `a clean app must build:\n${r.stdout}${r.stderr}`);
  for (const f of ["index.html", "app.css", "app.js"]) {
    assert.ok(existsSync(join(dir, "dist", f)), `dist/${f} must exist`);
  }
});

test("a stale file from a previous build does not survive into dist", () => {
  // `await rm(dist, ...)` was removable with a green suite, because every test
  // built into a fresh temp directory where dist did not exist yet. On a real
  // machine dist DOES exist -- that is the whole point of a build directory --
  // so a renamed or deleted asset stays in the shipped output forever, and the
  // page keeps loading a file nobody can find in the source any more.
  const dir = fixture("export const hi: string = 'hi';\ndocument.title = hi;\n");
  mkdirSync(join(dir, "dist"), { recursive: true });
  writeFileSync(join(dir, "dist/left-over.js"), "// from a build two versions ago\n");
  writeFileSync(join(dir, "dist/app.css"), "/* a stale stylesheet */\n");

  const r = build(dir);
  assert.equal(r.status, 0, `${r.stdout}${r.stderr}`);

  assert.equal(
    existsSync(join(dir, "dist/left-over.js")),
    false,
    "a file the build no longer produces must not be shipped",
  );
  assert.match(
    readFileSync(join(dir, "dist/app.css"), "utf8"),
    /color: red/,
    "and a file it DOES produce must be the fresh one, not the stale one",
  );
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
});
