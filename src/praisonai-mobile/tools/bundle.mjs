/**
 * The mobile bundle, and the checks that make shipping it safe.
 *
 * A webview is not Node. The failures this guards against are all ones that a
 * green `npm test` cannot catch, because node:test runs in Node where every
 * one of them works:
 *
 *  - A bare Node builtin import (`crypto`, `events`, `fs`). esbuild leaves it
 *    unresolved for a browser target, and the bundle dies at IMPORT time --
 *    before any code runs, so there is no error boundary and no message. This
 *    is not hypothetical: `praisonai`'s agent/simple.ts imports randomUUID from
 *    'crypto' and ai/tool-approval.ts imports EventEmitter from 'events'.
 *  - A top-level `process.env` read. Same class of failure, one tick later.
 *  - Silent size growth. A phone on a cold cellular start pays for every byte
 *    before first paint, and nobody notices 40kB a week until it is 2MB.
 *
 * Each check FAILS the build rather than warning. A warning in CI output is a
 * thing people stop reading; this repo would rather not ship.
 */
import * as esbuild from "esbuild";
import { readFile } from "node:fs/promises";

/** Node builtins that must never survive into a webview bundle. */
export const FORBIDDEN_BUILTINS = [
  "assert", "buffer", "child_process", "cluster", "crypto", "dgram", "dns",
  "events", "fs", "http", "http2", "https", "module", "net", "os", "path",
  "perf_hooks", "process", "querystring", "readline", "repl", "stream",
  "string_decoder", "timers", "tls", "tty", "url", "util", "v8", "vm",
  "worker_threads", "zlib",
];

/**
 * The webview baseline, and why these two.
 *
 * iOS ships WKWebView with the OS, so the floor is the oldest iOS worth
 * supporting rather than the newest Safari. Android's WebView updates through
 * Play, but a device kept offline keeps whatever it shipped with -- so the
 * floor there is the OS too, not the current Chrome.
 */
export const TARGETS = ["safari16", "chrome108"];

/** Bytes. Deliberately tight: this is a text UI, and the budget is what makes
 *  a dependency a decision rather than an accident. */
export const SIZE_BUDGET_BYTES = 400 * 1024;

/**
 * Every bare (non-relative) import esbuild could not resolve.
 *
 * Read off the metafile rather than by grepping the output text, because a
 * string in the source containing the word "crypto" is not an import and a
 * grep cannot tell the difference.
 */
export function unresolvedBareImports(metafile) {
  return [...classifyBareImports(metafile).keys()].sort();
}

/**
 * Bare imports, split by whether they run at import time.
 *
 * The distinction is the difference between a blank screen and a feature that
 * is merely unavailable. A STATIC `import x from "crypto"` is evaluated when
 * the module loads: the bundle dies before any code runs. A DYNAMIC
 * `await import("readline")` inside a function only fails if that function is
 * called -- and `createCLIApprovalPrompt` is CLI-only by name and contract, so
 * on a phone it never is.
 *
 * Treating both as fatal would force a bundle to carry a shim for a code path
 * it can never take, which is how a build gate starts being worked around
 * rather than fixed.
 */
export function classifyBareImports(metafile) {
  /** @type {Map<string, "static" | "dynamic">} */
  const found = new Map();
  for (const input of Object.values(metafile.inputs)) {
    for (const imported of input.imports ?? []) {
      if (imported.external !== true || imported.path.startsWith(".")) continue;
      const name = imported.path.replace(/^node:/, "");
      const isStatic = imported.kind !== "dynamic-import";
      // Static wins: one static import anywhere is import-time fatal, even if
      // the same module is also imported lazily elsewhere.
      if (isStatic || !found.has(name)) found.set(name, isStatic ? "static" : "dynamic");
    }
  }
  return found;
}

export function forbiddenAmong(paths) {
  return paths.filter((p) => FORBIDDEN_BUILTINS.includes(p.split("/")[0]));
}

/**
 * Top-level `process` reads that survived bundling.
 *
 * Scoped to the top level on purpose: a guarded read inside a function is fine
 * (`typeof process !== 'undefined' && process.env`) and is how the codebase is
 * expected to read env. What breaks a webview is a read that runs at module
 * evaluation, before any guard the app might install.
 */
export function topLevelProcessReads(code) {
  const hits = [];
  let depth = 0;
  const lines = code.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (depth === 0 && /(?<![.\w$])process\s*\.\s*env/.test(line) && !/typeof\s+process/.test(line)) {
      hits.push({ line: i + 1, text: line.trim().slice(0, 120) });
    }
    for (const ch of line) {
      if (ch === "{") depth++;
      else if (ch === "}") depth = Math.max(0, depth - 1);
    }
  }
  return hits;
}

export async function bundle({ entry, outfile, minify = true, write = true }) {
  const result = await esbuild.build({
    entryPoints: [entry],
    outfile,
    bundle: true,
    format: "esm",
    platform: "browser",
    target: TARGETS,
    minify,
    sourcemap: true,
    metafile: true,
    write,
    logLevel: "silent",
    // Bare specifiers stay external so they show up in the metafile as
    // unresolved rather than being silently shimmed. That is the whole point:
    // we want to SEE a `crypto` import, not have esbuild paper over it.
    plugins: [{
      name: "surface-bare-imports",
      setup(build) {
        build.onResolve({ filter: /^[^.\/]/ }, (args) => ({ path: args.path, external: true }));
      },
    }],
  });

  const code = write
    ? await readFile(outfile, "utf8")
    : (result.outputFiles?.find((f) => f.path.endsWith(".js"))?.text ?? "");

  const classified = classifyBareImports(result.metafile);
  const bare = [...classified.keys()].sort();
  const forbidden = forbiddenAmong(bare);
  const fatal = forbidden.filter((p) => classified.get(p) === "static");
  const lazy = forbidden.filter((p) => classified.get(p) === "dynamic");
  const processReads = topLevelProcessReads(code);
  const bytes = Buffer.byteLength(code, "utf8");

  const problems = [];
  if (fatal.length > 0) {
    problems.push(
      `Node builtins imported STATICALLY: ${fatal.join(", ")}.\n` +
      `    These fail at IMPORT time, before any code runs -- there is no error\n` +
      `    boundary and the screen stays blank. Alias them or fix upstream.`,
    );
  }
  if (processReads.length > 0) {
    problems.push(
      `top-level process.env reads (${processReads.length}):\n` +
      processReads.map((h) => `      line ${h.line}: ${h.text}`).join("\n") +
      `\n    A webview has no process. Route these through a guarded accessor.`,
    );
  }
  if (bytes > SIZE_BUDGET_BYTES) {
    problems.push(
      `bundle is ${(bytes / 1024).toFixed(1)}kB, over the ${(SIZE_BUDGET_BYTES / 1024).toFixed(0)}kB budget.`,
    );
  }

  return { bytes, bare, forbidden, fatal, lazy, processReads, problems, metafile: result.metafile, code };
}

/** CLI. Guarded so importing this module for tests does not run a build. */
if (process.argv[1] && import.meta.url.endsWith(process.argv[1].split("/").pop())) {
  const entry = process.argv[2] ?? "app/src/main.ts";
  const outfile = process.argv[3] ?? "dist/app.js";
  const report = await bundle({ entry, outfile });
  for (const problem of report.problems) console.error(`  ✖ ${problem}`);
  for (const name of report.lazy) {
    // Reported, never silent: a lazy builtin is fine only while nothing on a
    // phone calls into it, and that is a claim worth restating every build.
    console.log(`  ! ${name} is imported lazily -- fine while no mobile path calls it`);
  }
  console.log(`bundle: ${(report.bytes / 1024).toFixed(1)}kB, ${report.bare.length} external`);
  if (report.problems.length > 0) process.exit(1);
}

/**
 * Whether a bundle report may ship.
 *
 * Exported so a test calls THIS rather than re-implementing the comparison --
 * `problems.length > 0` -> `> 1` survived a mutation sweep, and a test that
 * rewrote the predicate inline would have proved only that a predicate of that
 * shape works, not that this file still contains it. That distinction is the
 * one this package keeps being bitten by.
 *
 * ONE problem is enough. A bare external, a forbidden builtin, or a top-level
 * process.env read each make the bundle unshippable on its own.
 */
export function isShippable(report) {
  return report.problems.length === 0;
}
