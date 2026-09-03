/**
 * The web build's Content-Security-Policy, as written in app/index.html.
 *
 * tauri.conf.json's csp reaches only the Tauri shell; a browser loading dist/
 * from GitHub Pages sees the meta tag and nothing else. And because Tauri
 * appends its own tag rather than replacing this one, the shell enforces
 * BOTH -- so this one must not be tighter than Tauri's anywhere the shell
 * needs room (the IPC origins), or the Android app breaks with a console line.
 *
 * tools/web-boot.test.mjs proves the policy is enforced by a real browser;
 * this file pins its text so a loosening is a visible diff.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const html = readFileSync(join(import.meta.dirname, "../app/index.html"), "utf8");
const tauri = JSON.parse(readFileSync(join(import.meta.dirname, "../src-tauri/tauri.conf.json"), "utf8"));

/** The meta tag's policy, or null when there is none. */
function metaCsp(page) {
  const m = /<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]*)"/i.exec(page);
  return m ? m[1] : null;
}
const directives = (csp) =>
  Object.fromEntries(
    csp
      .split(";")
      .map((d) => d.trim())
      .filter(Boolean)
      .map((d) => {
        const [name, ...sources] = d.split(/\s+/);
        return [name, sources];
      }),
  );

const csp = metaCsp(html);
const web = csp === null ? null : directives(csp);
const shell = directives(tauri.app.security.csp);

test("the page carries a CSP meta tag, placed before anything it must govern", () => {
  assert.ok(csp !== null, "app/index.html must carry a <meta http-equiv=\"Content-Security-Policy\">");
  const at = html.indexOf('http-equiv="Content-Security-Policy"');
  for (const tag of ["<link", "<script", "<style"]) {
    const first = html.indexOf(tag);
    if (first !== -1) assert.ok(at < first, `the CSP must precede the first ${tag}, or that element loads ungoverned`);
  }
});

test("script-src is 'self' and nothing else", () => {
  assert.deepEqual(web["script-src"], ["'self'"], "no 'unsafe-inline', no 'unsafe-eval', no host, no nonce, no hash");
  assert.deepEqual(web["default-src"], ["'self'"]);
});

test("there is no inline script for that policy to silently block", () => {
  // A `<script>` with a body would be dropped by script-src 'self' with only
  // a console line to say so -- the page would boot without it and nobody
  // would know. Every script is an external file.
  const inline = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)].filter(
    ([, attrs, body]) => !/\bsrc=/.test(attrs) || body.trim() !== "",
  );
  assert.deepEqual(inline.map((m) => m[0]), [], "an inline <script> would be blocked by the CSP");
  assert.match(html, /<script\s+src="\.\/register-sw\.js"><\/script>/, "the registration is an external file");
});

test("connect-src reaches the engines the settings allow", () => {
  const connect = web["connect-src"];
  for (const source of ["'self'", "http://127.0.0.1:*", "http://localhost:*", "https:"]) {
    assert.ok(connect.includes(source), `connect-src must include ${source}`);
  }
  assert.ok(!connect.includes("*"), "and must not be a wildcard");
  assert.ok(!connect.includes("http:"), "nor allow every plain-http host");
});

test("the web CSP is never tighter than the shell's where the shell needs room", () => {
  // Both tags apply inside Tauri. Every source the shell's connect-src allows
  // must be allowed here too, or the shell's own IPC is blocked.
  for (const source of shell["connect-src"]) {
    assert.ok(web["connect-src"].includes(source), `tauri.conf.json allows ${source}; the web CSP must too`);
  }
  for (const name of Object.keys(shell)) {
    assert.ok(name in web, `the shell sets ${name}; the web CSP must set it too rather than fall back to default-src`);
  }
});

test("the manifest and the worker are permitted, and <base> cannot be injected", () => {
  assert.deepEqual(web["manifest-src"], ["'self'"]);
  assert.deepEqual(web["worker-src"], ["'self'"]);
  assert.deepEqual(web["base-uri"], ["'self'"], "a <base> injection would redirect every relative URL");
  // Chrome ignores these when delivered via <meta> and logs a console error
  // for each -- which the boot proof counts as a failure. They belong in a
  // response header, which GitHub Pages does not let us set.
  for (const headerOnly of ["frame-ancestors", "report-uri", "sandbox"]) {
    assert.ok(!(headerOnly in web), `${headerOnly} is ignored in a <meta> CSP`);
  }
});

test("every asset URL in the page is relative, so a subpath deployment works", () => {
  for (const [, url] of html.matchAll(/\b(?:href|src)="([^"]+)"/g)) {
    assert.match(url, /^\.\//, `${url} must be relative: GitHub Pages serves this from /PraisonAI/`);
  }
});
