import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, existsSync } from "node:fs";
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
