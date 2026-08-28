/**
 * The Rust and TypeScript sides of the shell seam must agree on four strings.
 *
 * They are how the webview subscribes, and a rename on either side is SILENT:
 * the webview simply stops receiving that event, and the app lays out as
 * though the phone had no notch, no keyboard, and no lifecycle. Nothing
 * throws, so nothing is reported and no test elsewhere fails.
 *
 * The Rust crate has its own test pinning each constant to a literal. That
 * catches a rename WITHIN Rust. This is the other half: it reads both sources
 * and compares them, so a rename in either language fails CI instead of a
 * device.
 *
 * Deliberately reads the files rather than importing: the Rust cannot be
 * imported, and parsing it is the only way to compare the two.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const pkg = join(here, "..");   // tools/ -> the package root

const rust = readFileSync(join(pkg, "src-tauri/src/shell/mod.rs"), "utf8");
const ts = readFileSync(join(pkg, "adapters/src/tauri/shell.ts"), "utf8");

/** `pub const NAME: &str = "value";` */
function rustConst(name) {
  const m = new RegExp(`pub const ${name}: &str = "([^"]+)"`).exec(rust);
  assert.ok(m, `${name} not found in the Rust shell module`);
  return m[1];
}

/** A key in the TypeScript `EVENTS` table, or a bare const. */
function tsValue(key) {
  const m = new RegExp(`${key}: "([^"]+)"`).exec(ts);
  assert.ok(m, `${key} not found in the TypeScript adapter`);
  return m[1];
}

test("the four event names agree across the seam", () => {
  assert.equal(rustConst("EVT_SAFE_AREA"), tsValue("safeArea"));
  assert.equal(rustConst("EVT_KEYBOARD"), tsValue("keyboard"));
  assert.equal(rustConst("EVT_LIFECYCLE"), tsValue("lifecycle"));
  assert.equal(rustConst("EVT_BACK"), tsValue("back"));
});

test("the back-result command name agrees", () => {
  const m = /BACK_RESULT_COMMAND = "([^"]+)"/.exec(ts);
  assert.ok(m, "BACK_RESULT_COMMAND not found in the TypeScript adapter");
  assert.equal(rustConst("CMD_BACK_RESULT"), m[1]);
});

test("the comparison is real, not two lookups of the same file", () => {
  // The way this test could quietly stop working: if both helpers read the
  // same source, every assertion above passes forever. Assert the two files
  // are actually different documents.
  assert.notEqual(rust, ts);
  assert.ok(rust.includes("pub const"), "the Rust source was not read");
  assert.ok(ts.includes("const EVENTS"), "the TypeScript source was not read");
});
