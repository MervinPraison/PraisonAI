/**
 * The Tauri config, checked against what the app actually does.
 *
 * `tauri.conf.json` is not covered by the TypeScript suite and is not compiled
 * by `cargo test`, so every value in it was unasserted. Two of them decide
 * whether the app can function on a device at all.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const conf = JSON.parse(
  readFileSync(join(import.meta.dirname, "../src-tauri/tauri.conf.json"), "utf8"),
);
const directive = (name) =>
  (conf.app.security.csp.split(";").find((d) => d.trim().startsWith(name)) ?? "").trim();

test("the CSP permits the engine addresses the settings allow", () => {
  // `connect-src 'self' ipc: http://ipc.localhost` permitted NO engine at all.
  // `baseUrl` is user-settable to any host (app/src/registry.ts:58), the HTTP
  // adapter under Tauri is still browser `fetch` (app/src/platform.ts), and a
  // webview enforces connect-src on fetch -- so every remote engine was
  // blocked before it reached the network, including the shipped default of
  // http://127.0.0.1:8765.
  //
  // The desktop app already had the loopback entries; mobile did not, and
  // mobile additionally needs https:, because on a phone the engine is across
  // a network rather than on the same machine.
  const connect = directive("connect-src");
  assert.match(connect, /https:/, "an https engine address must be reachable");
  assert.match(connect, /http:\/\/127\.0\.0\.1:\*/, "and the shipped loopback default");
  assert.match(connect, /\bipc:/, "and Tauri's own IPC");
});

test("the CSP still refuses remote SCRIPTS -- the pair", () => {
  // Widening connect-src must not widen the thing that matters. A model can
  // return arbitrary text and a tool result is attacker-shaped in the ordinary
  // case; script-src is what stops that becoming code in the app's origin.
  const script = directive("script-src");
  assert.equal(script, "script-src 'self'", `script-src must stay closed: ${script}`);
  assert.doesNotMatch(script, /unsafe-inline|unsafe-eval|https:/);
  assert.match(directive("default-src"), /^default-src 'self'$/);
});

test("the mobile platform minimums are declared", () => {
  // Tauri needs these to generate the platform projects; a missing value is a
  // default that may be below what the code assumes.
  assert.equal(conf.bundle.iOS.minimumSystemVersion, "16.0");
  assert.equal(conf.bundle.android.minSdkVersion, 26);
});

test("the identifier is a real reverse-DNS id, not the Tauri placeholder", () => {
  // Both stores key the app on this forever, and Tauri's own template value
  // ships as `com.tauri.dev`, which cannot be uploaded.
  assert.match(conf.identifier, /^[a-z][a-z0-9]*(\.[a-z][a-z0-9-]*)+$/, conf.identifier);
  assert.doesNotMatch(conf.identifier, /tauri\.dev|example|todo/i);
});
