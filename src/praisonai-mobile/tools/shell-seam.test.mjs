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
const kotlin = readFileSync(
  join(pkg, "src-tauri/gen/android/app/src/main/java/ai/praison/mobile/MainActivity.kt"),
  "utf8",
);

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

/**
 * The Android insets bridge is a FIFTH string across the same seam, and it
 * fails the same silent way: MainActivity's `evaluateJavascript` calls
 * `window.<name> && window.<name>(...)`, so a name the shell does not install
 * is not an error, it is a no-op -- and the app lays out as though the phone
 * had no status bar, no navigation bar and no keyboard, which is precisely the
 * state it was measured in on an Android 15 emulator before this existed.
 */
test("the Android insets global agrees across the Kotlin/TypeScript seam", () => {
  const tsName = /NATIVE_INSETS_GLOBAL = "([^"]+)"/.exec(ts);
  assert.ok(tsName, "NATIVE_INSETS_GLOBAL not found in the TypeScript adapter");
  const ktName = /INSETS_GLOBAL = "([^"]+)"/.exec(kotlin);
  assert.ok(ktName, "INSETS_GLOBAL not found in MainActivity.kt");
  assert.equal(ktName[1], tsName[1]);
  assert.notEqual(kotlin, ts, "two lookups of the same file would assert nothing");
});

test("MainActivity sends every edge, and the keyboard separately from them", () => {
  // The payload is built as a string literal, so a dropped edge is a missing
  // key the TypeScript reads as 0 -- silently flush against that edge.
  const call = /INSETS_GLOBAL\(\{" \+([\s\S]*?)\}\)/.exec(kotlin);
  assert.ok(call, "the insets payload literal was not found in MainActivity.kt");
  for (const key of ["top", "right", "bottom", "left", "keyboard"]) {
    assert.match(call[1], new RegExp(`\\b${key}:`), `MainActivity must send ${key}`);
  }
  // `bottom` must come from the system bars, not from the IME: the page
  // composes the two with max(), so sending the keyboard on both channels is
  // the double-count ui/src/layout/insets.ts warns about.
  assert.match(call[1], /bottom:\$\{css\(bars\.bottom\)\}/, "bottom is the system bars");
  assert.match(call[1], /keyboard:\$\{css\(ime\.bottom\)\}/, "keyboard is the IME inset");
});
