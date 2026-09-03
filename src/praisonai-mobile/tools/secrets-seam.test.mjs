/**
 * The Rust and TypeScript sides of the SECRETS seam must agree on four command
 * names and on five slots — and the store must be a keychain rather than a
 * file.
 *
 * A rename on either side alone is silent in the worst possible way: Tauri
 * rejects the unknown command, `createTauriSecrets` propagates the rejection,
 * the settings row falls back to "Not set", and the user retypes a key that is
 * already stored — into a call that also fails. Nothing crashes and neither
 * language's own test suite fails, because the Rust tests pin the Rust
 * constants to literals and the TypeScript tests pin the TypeScript ones.
 *
 * The same argument as tools/storage-seam.test.mjs and tools/shell-seam.test.mjs,
 * one seam over, written at the same time as the seam rather than after the
 * first device bug.
 *
 * Deliberately reads the files rather than importing: the Rust and the Kotlin
 * cannot be imported, and parsing them is the only way to compare the three.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const pkg = join(here, ".."); // tools/ -> the package root

const rust = readFileSync(join(pkg, "src-tauri/src/secrets.rs"), "utf8");
const plugin = readFileSync(join(pkg, "src-tauri/plugins/secrets/src/lib.rs"), "utf8");
const kotlin = readFileSync(
  join(
    pkg,
    "src-tauri/plugins/secrets/android/src/main/java/ai/praison/mobile/secrets/SecretsPlugin.kt",
  ),
  "utf8",
);
const ts = readFileSync(join(pkg, "adapters/src/tauri/secrets.ts"), "utf8");
const port = readFileSync(join(pkg, "core/src/ports/secrets.ts"), "utf8");

/**
 * Source with its comment lines removed.
 *
 * Not a nicety — a measured false green in the storage seam next door: a check
 * written against raw source passed because a doc comment happened to explain
 * what the code was supposed to do. Every prose paragraph in these files names
 * the very APIs the assertions below look for, so without this every one of
 * them would pass on a file whose code had been gutted.
 */
function code(source, lineComment = "//") {
  return source
    .split("\n")
    .filter((line) => !line.trim().startsWith(lineComment))
    .join("\n");
}

const rustCode = code(rust).split("#[cfg(test)]")[0];
const pluginCode = code(plugin).split("#[cfg(test)]")[0];
const kotlinCode = code(kotlin)
  // Kotlin's KDoc blocks are `/** ... */`, so the line filter alone leaves the
  // prose in. Strip block comments too, for the same reason.
  .replace(/\/\*[\s\S]*?\*\//g, "");

/** `[pub ]const NAME: &str = "value";` — PLUGIN_IDENTIFIER is crate-private. */
function rustConst(source, name) {
  const m = new RegExp(`(?:pub )?const ${name}: &str = "([^"]+)"`).exec(source);
  assert.ok(m, `${name} not found`);
  return m[1];
}

/** A key in the TypeScript `SECRET_COMMANDS` table. */
function tsCommand(key) {
  const m = new RegExp(`${key}: "([^"]+)"`).exec(ts);
  assert.ok(m, `${key} not found in adapters/src/tauri/secrets.ts`);
  return m[1];
}

test("the four secret command names agree across the seam", () => {
  assert.equal(rustConst(rust, "CMD_READ"), tsCommand("read"));
  assert.equal(rustConst(rust, "CMD_WRITE"), tsCommand("write"));
  assert.equal(rustConst(rust, "CMD_REMOVE"), tsCommand("remove"));
  assert.equal(rustConst(rust, "CMD_HAS"), tsCommand("has"));
});

test("every command the adapter can send is registered with Tauri", () => {
  // A command that exists in `secrets.rs` but is missing from
  // `generate_handler!` is not reachable AT ALL — the invoke rejects with
  // "command not found" and only that one operation silently stops working.
  // `has` would be the one nobody notices: the key is stored, the key works,
  // and the settings row says "Not set" forever.
  const lib = readFileSync(join(pkg, "src-tauri/src/lib.rs"), "utf8");
  const handler = /generate_handler!\[([\s\S]*?)\]/.exec(lib);
  assert.ok(handler, "no generate_handler! block in lib.rs");
  for (const key of ["read", "write", "remove", "has"]) {
    const command = tsCommand(key);
    assert.ok(
      handler[1].includes(command),
      `${command} is not in generate_handler!; the webview cannot reach it`,
    );
  }
});

test("the store plugin is installed, not merely written", () => {
  // Every command compiles, registers and then PANICS on the first
  // `state::<SecretStore>()` if this line is missing — and it is one line in a
  // builder chain that nothing else reads. Same class of silent deletion
  // `tests/wiring.rs` exists for.
  const lib = code(readFileSync(join(pkg, "src-tauri/src/lib.rs"), "utf8"));
  assert.match(
    lib,
    /\.plugin\(tauri_plugin_secrets::init\(\)\)/,
    "tauri_plugin_secrets::init() is not in the builder chain; every secret call panics",
  );
});

test("the Rust slot allowlist and the port's closed union are the same five", () => {
  // Rule 3 of core/src/ports/secrets.ts: the slot becomes a keychain SERVICE
  // name, so a slot the union declares and Rust refuses is a credential that
  // can never be stored, and a slot Rust accepts and the union does not is the
  // free-form namespace the rule exists to forbid.
  const union = /export type SecretSlot =([^;]+);/.exec(port);
  assert.ok(union, "SecretSlot union not found in the port");
  const declared = [...union[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]).sort();
  const m = /pub const SLOTS: \[&str; \d+\] = \[([^\]]+)\]/.exec(rustCode);
  assert.ok(m, "SLOTS not found in src-tauri/src/secrets.rs");
  const allowed = [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]).sort();
  assert.deepEqual(allowed, declared, "the Rust allowlist and the SecretSlot union disagree");
});

test("the Kotlin command names are the ones the Rust plugin calls", () => {
  // Rust -> Kotlin, the other half of the same seam. A rename here is a
  // `run_mobile_plugin` rejection at runtime on Android only: it builds, it
  // ships, and every secret operation fails on a phone and nowhere else.
  for (const name of ["READ", "WRITE", "REMOVE", "HAS"]) {
    const command = rustConst(plugin, name);
    assert.match(
      kotlinCode,
      new RegExp(`fun ${command}\\(invoke: Invoke\\)`),
      `SecretsPlugin.kt has no @Command named ${command}`,
    );
  }
});

test("the Kotlin class is where the Rust says it is", () => {
  // A mismatch is a ClassNotFoundException at plugin registration — on the
  // device, at startup, not at build time.
  const identifier = rustConst(plugin, "PLUGIN_IDENTIFIER");
  assert.match(
    kotlinCode,
    new RegExp(`^package ${identifier.replace(/\./g, "\\.")}$`, "m"),
    `SecretsPlugin.kt is not in package ${identifier}`,
  );
  assert.match(kotlinCode, /class SecretsPlugin\(/, "the class Rust registers by name is gone");
});

test("the Android store is the Keystore-backed one, not plain preferences", () => {
  // THE point of the Android half. `EncryptedSharedPreferences` ->
  // `getSharedPreferences` is a two-word edit that compiles, passes every
  // behavioural test (it round-trips fine, it survives a relaunch fine) and
  // writes the user's API key into /data/data as plaintext XML. The only thing
  // that can catch it before a device does is the name of the call.
  assert.match(
    kotlinCode,
    /EncryptedSharedPreferences\.create\(/,
    "the Android secret store must be EncryptedSharedPreferences",
  );
  assert.match(
    kotlinCode,
    /MasterKeys\.getOrCreate\(MasterKeys\.AES256_GCM_SPEC\)/,
    "the master key must be generated in the AndroidKeyStore",
  );
  assert.doesNotMatch(
    kotlinCode,
    /getSharedPreferences\(/,
    "plain SharedPreferences is a plaintext XML file in /data/data",
  );
  const gradle = readFileSync(
    join(pkg, "src-tauri/plugins/secrets/android/build.gradle.kts"),
    "utf8",
  );
  assert.match(
    gradle,
    /androidx\.security:security-crypto:/,
    "the security-crypto dependency is what EncryptedSharedPreferences comes from",
  );
});

test("the Android write is committed rather than applied", () => {
  // `commit()` -> `apply()` is a one-word edit that keeps every test green and
  // loses the key when Android kills the process inside the async write window
  // — which is the exact "gone after a relaunch" failure this change exists to
  // remove, reintroduced one layer down.
  assert.match(kotlinCode, /\.commit\(\)/, "the secret write must be committed synchronously");
  assert.doesNotMatch(kotlinCode, /\.apply\(\)/, "apply() can lose the write on a process kill");
});

test("the Apple store is the Keychain, not a file", () => {
  // Same argument, other platform. Anything that writes bytes the app itself
  // can read back without the OS is not a keychain.
  assert.match(
    pluginCode,
    /use security_framework::passwords::/,
    "the Apple half must go through the Security framework",
  );
  assert.doesNotMatch(
    pluginCode,
    /fs::write|File::create/,
    "a secret is never written to a file by this plugin",
  );
});

test("presence has its own command on every side of the seam", () => {
  // Rule 2 of the port: `has()` "must not fault the value into memory". The
  // behaviour is asserted by the adapter contract (a read counter that must not
  // move); what is pinned HERE is that each layer still has a separate presence
  // path at all, because collapsing one into a read is the edit that breaks the
  // rule while every boolean stays correct.
  assert.match(kotlinCode, /\.contains\(keyFor\(/, "Kotlin presence must use contains()");
  assert.doesNotMatch(
    /fun hasSecret[\s\S]*?\n  \}/.exec(kotlinCode)?.[0] ?? "",
    /getString\(/,
    "hasSecret must not read the value out",
  );
  assert.match(ts, /SECRET_COMMANDS\.has/, "the adapter must send the presence command");
});

test("a secret never travels over the storage seam", () => {
  // Rule 1 of the port, at the layer where breaking it would be invisible: the
  // Rust store's namespace allowlist is what a "secrets" namespace would have
  // to be added to, and adding it is how a credential ends up in a plain file
  // in the app's data directory next to the chats.
  const store = code(readFileSync(join(pkg, "src-tauri/src/store.rs"), "utf8")).split(
    "#[cfg(test)]",
  )[0];
  const m = /pub const NAMESPACES: \[&str; \d+\] = \[([^\]]+)\]/.exec(store);
  assert.ok(m, "NAMESPACES not found in the Rust store module");
  const allowed = [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
  for (const forbidden of ["secrets", "keychain", "keys", "credentials"]) {
    assert.ok(
      !allowed.includes(forbidden),
      `${forbidden} is a StoragePort namespace; a secret must never pass through it`,
    );
  }
});

test("the comparison is real, not five lookups of the same file", () => {
  // The way this test could quietly stop working: if the helpers read the same
  // source, every assertion above passes forever.
  assert.notEqual(rust, ts);
  assert.notEqual(rust, plugin);
  assert.notEqual(kotlin, ts);
  assert.ok(rust.includes("pub const CMD_READ"), "the Rust command module was not read");
  assert.ok(plugin.includes("SERVICE_PREFIX"), "the Rust plugin was not read");
  assert.ok(kotlin.includes("class SecretsPlugin"), "the Kotlin plugin was not read");
  assert.ok(ts.includes("SECRET_COMMANDS"), "the TypeScript adapter was not read");
  assert.ok(port.includes("export type SecretSlot"), "the port was not read");
});
