/**
 * The Rust and TypeScript sides of the STORAGE seam must agree on five command
 * names and on four namespaces.
 *
 * A rename on either side alone is silent in the worst possible way: Tauri
 * rejects the unknown command, `createTauriStorage` propagates the rejection,
 * `repository.load` reports `unreadable`, and the app keeps running while
 * every conversation the user has fails to save. Nothing crashes and nothing
 * in either language's own test suite fails -- the Rust tests pin the Rust
 * constants to literals, the TypeScript tests pin the TypeScript ones, and
 * both stay green while the two drift apart.
 *
 * The same argument as tools/shell-seam.test.mjs, one seam over, written at
 * the same time as the seam rather than after the first device bug.
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
const pkg = join(here, ".."); // tools/ -> the package root

const rust = readFileSync(join(pkg, "src-tauri/src/store.rs"), "utf8");
const ts = readFileSync(join(pkg, "adapters/src/tauri/storage.ts"), "utf8");
const port = readFileSync(join(pkg, "core/src/ports/storage.ts"), "utf8");

/**
 * Rust source with its comment lines removed.
 *
 * Not a nicety -- a measured false green. The `app_data_dir` check below was
 * written against the raw source, and this file's own mutation sweep caught it:
 * swapping the real `.app_data_dir()` call for `.app_cache_dir()` left the test
 * PASSING, because `lib.rs`'s doc comment explains what `app_data_dir()` is and
 * the regex was happily matching the explanation. A gate that reads prose is a
 * gate that passes when the prose is right and the code is wrong, which is the
 * precise failure mode this package keeps a file of notes about.
 */
function code(source) {
  return source
    .split("\n")
    .filter((line) => !line.trim().startsWith("//"))
    .join("\n");
}

/**
 * The SHIPPING half of store.rs -- everything before `#[cfg(test)]`.
 *
 * The test module deliberately calls `fs::write` to simulate a write
 * interrupted before its rename, so a check for "no fs::write anywhere" would
 * be red on correct code. Cutting at the cfg(test) line keeps the check aimed
 * at the code that runs on a phone.
 */
const rustCode = code(rust).split("#[cfg(test)]")[0];

/** `pub const NAME: &str = "value";` */
function rustConst(name) {
  const m = new RegExp(`pub const ${name}: &str = "([^"]+)"`).exec(rust);
  assert.ok(m, `${name} not found in the Rust store module`);
  return m[1];
}

/** A key in the TypeScript `STORAGE_COMMANDS` table. */
function tsCommand(key) {
  const m = new RegExp(`${key}: "([^"]+)"`).exec(ts);
  assert.ok(m, `${key} not found in adapters/src/tauri/storage.ts`);
  return m[1];
}

test("the five storage command names agree across the seam", () => {
  assert.equal(rustConst("CMD_READ"), tsCommand("read"));
  assert.equal(rustConst("CMD_WRITE"), tsCommand("write"));
  assert.equal(rustConst("CMD_REMOVE"), tsCommand("remove"));
  assert.equal(rustConst("CMD_LIST_IDS"), tsCommand("listIds"));
  assert.equal(rustConst("CMD_CLEAR"), tsCommand("clear"));
});

test("every command the adapter can send is registered with Tauri", () => {
  // A command that exists in `store.rs` but is missing from
  // `generate_handler!` is not reachable AT ALL -- the invoke rejects with
  // "command not found" and, again, only that one operation silently stops
  // working. `clear` would be the one nobody notices for months.
  const lib = readFileSync(join(pkg, "src-tauri/src/lib.rs"), "utf8");
  const handler = /generate_handler!\[([\s\S]*?)\]/.exec(lib);
  assert.ok(handler, "no generate_handler! block in lib.rs");
  for (const key of ["read", "write", "remove", "listIds", "clear"]) {
    const command = tsCommand(key);
    assert.ok(
      handler[1].includes(command),
      `${command} is not in generate_handler!; the webview cannot reach it`,
    );
  }
});

test("the store resolves its root under the app data directory", () => {
  // `app_data_dir()` -> `temp_dir()` or `cache_dir()` compiles, passes every
  // Rust test (they all run against a scratch root), and ships a store the OS
  // is free to delete -- which is the exact bug this whole change exists to
  // fix, reintroduced one directory down.
  const lib = code(readFileSync(join(pkg, "src-tauri/src/lib.rs"), "utf8"));
  assert.match(lib, /\.app_data_dir\(\)/, "the store must live in the app's data directory");
  assert.doesNotMatch(lib, /cache_dir\(\)/, "a cache directory is evictable by the OS");
  assert.doesNotMatch(lib, /temp_dir\(\)/, "a temp directory is not a place to keep chat history");
});

/**
 * The body of `FileStore::write`, and nothing else.
 *
 * Scoped, because a whole-file search is not a gate. Measured, by this file's
 * own mutation sweep: deleting the directory flush from `write` left the check
 * GREEN, because `indexOf` happily found the identical call in `clear` further
 * down the file and it was, of course, after the rename. The first version of
 * this test could not fail for the defect it was written for.
 */
function writeBody() {
  const at = rustCode.indexOf("pub fn write(");
  assert.notEqual(at, -1, "FileStore::write not found");
  const rest = rustCode.slice(at);
  const next = rest.indexOf("\n    pub fn ", 1);
  return next === -1 ? rest : rest.slice(0, next);
}

test("the write path is write-temp-then-rename, with the data flushed first", () => {
  // The port's atomicity clause is behaviourally tested in store.rs (a reader
  // thread against ten concurrent writers). The two FLUSHES are the part of it
  // no in-process test can reach: `sync_all` only matters across a power loss
  // or a kernel panic, and dropping either leaves every test green while
  // shipping a store that can come back with a correctly-named file full of
  // zeroes -- which is worse than a missing file, because it reads as
  // corruption rather than as absence. Measured: removing each of those two
  // lines survived the entire suite, Rust and TypeScript alike.
  //
  // So they are pinned at the only level available, on the CODE of the one
  // function that performs the write.
  const body = writeBody();

  assert.doesNotMatch(
    body,
    /fs::write\(/,
    "fs::write truncates in place: a kill mid-write loses the whole conversation",
  );

  // Order, not just presence. A flush after the rename guarantees nothing, and
  // a rename of something never written guarantees less.
  const steps = ["File::create(&temp)", "file.sync_all()", "fs::rename(&temp, &path)", "sync_dir(&dir)"];
  const at = steps.map((step) => body.indexOf(step));
  for (const [n, step] of steps.entries()) {
    assert.notEqual(at[n], -1, `FileStore::write no longer does: ${step}`);
  }
  assert.deepEqual(
    at,
    [...at].sort((a, b) => a - b),
    `the write path is out of order: ${steps.join(" -> ")}`,
  );
});

test("the namespaces Rust accepts are the ones the port declares", () => {
  // The Rust allowlist is the path-traversal defence AND the list of what can
  // be stored at all. A namespace added to the port and not to the allowlist
  // fails every write in that namespace, at runtime, on a device.
  const declared = [...port.matchAll(/"(chats|settings|drafts|cache)"/g)].map((m) => m[1]);
  const unique = [...new Set(declared)].sort();
  const m = /pub const NAMESPACES: \[&str; \d+\] = \[([^\]]+)\]/.exec(rustCode);
  assert.ok(m, "NAMESPACES not found in the Rust store module");
  const allowed = [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]).sort();
  assert.deepEqual(allowed, unique, "the Rust allowlist and the Namespace union disagree");
});

test("the comparison is real, not three lookups of the same file", () => {
  // The way this test could quietly stop working: if the helpers read the same
  // source, every assertion above passes forever.
  assert.notEqual(rust, ts);
  assert.notEqual(ts, port);
  assert.ok(rust.includes("pub const"), "the Rust source was not read");
  assert.ok(ts.includes("STORAGE_COMMANDS"), "the TypeScript adapter was not read");
  assert.ok(port.includes("export type Namespace"), "the port was not read");
});
