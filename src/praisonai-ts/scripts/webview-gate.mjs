/**
 * Can praisonai-ts still be loaded in a webview?
 *
 * Issue #4437 was exactly this failing: `crypto` and `events` were static
 * imports on the `Agent` graph, so a browser/webview bundle died at IMPORT
 * time -- before any code ran, with no error boundary and a blank screen. PR
 * #4438 fixed it. Nothing stopped it coming back.
 *
 * That is the gap this closes. The `npm test` suite runs in Node, where every
 * one of these failures works perfectly, so no unit test can catch a
 * regression here. One `import { x } from "fs"` added to a file the Agent
 * happens to reach would silently un-ship the mobile app, and the first signal
 * would be a blank screen on a device.
 *
 * STATIC vs DYNAMIC matters and is not pedantry. A static import is evaluated
 * at module load and kills the bundle outright. A dynamic `await import()`
 * inside a function only fails if that function is called -- `readline` is
 * reached only from `createCLIApprovalPrompt`, which is CLI-only by name and
 * contract, so a phone never calls it. Failing on it would force a shim for a
 * code path that cannot be taken, which is how a gate gets worked around
 * instead of fixed.
 */
import * as esbuild from "esbuild";

/** Node builtins that must never be reachable at import time from an entry a
 *  webview loads. */
const FORBIDDEN = new Set([
  "assert", "buffer", "child_process", "cluster", "crypto", "dgram", "dns",
  "events", "fs", "http", "http2", "https", "module", "net", "os", "path",
  "perf_hooks", "process", "querystring", "readline", "repl", "stream",
  "string_decoder", "timers", "tls", "tty", "url", "util", "v8", "vm",
  "worker_threads", "zlib",
]);

/**
 * The entries a mobile or browser consumer actually imports.
 *
 * Deliberately not the package root: `index.ts` re-exports the CLI, the MCP
 * server and the tool registry, none of which a phone loads, and gating on it
 * would report failures nobody can act on.
 */
export const WEBVIEW_ENTRIES = ["src/mobile.ts", "src/agent/simple.ts"];

/** The webview baseline. iOS ships WKWebView with the OS, so the floor is the
 *  oldest iOS worth supporting rather than the newest Safari. */
export const TARGETS = ["safari16", "chrome108"];

export async function inspect(entry) {
  const result = await esbuild.build({
    entryPoints: [entry],
    bundle: true,
    write: false,
    metafile: true,
    platform: "browser",
    format: "esm",
    target: TARGETS,
    logLevel: "silent",
    plugins: [{
      name: "surface-bare",
      setup(build) {
        // Bare specifiers stay external so they appear in the metafile rather
        // than being silently shimmed. Seeing the import is the whole point.
        build.onResolve({ filter: /^[^.\/]/ }, (args) => ({ path: args.path, external: true }));
      },
    }],
  });

  const fatal = new Set();
  const lazy = new Set();
  for (const input of Object.values(result.metafile.inputs)) {
    for (const imported of input.imports ?? []) {
      if (imported.external !== true || imported.path.startsWith(".")) continue;
      const name = imported.path.replace(/^node:/, "").split("/")[0];
      if (!FORBIDDEN.has(name)) continue;
      // Static wins: one static import anywhere is import-time fatal, whatever
      // else is true of the same module elsewhere.
      if (imported.kind !== "dynamic-import") {
        fatal.add(name);
        lazy.delete(name);
      } else if (!fatal.has(name)) {
        lazy.add(name);
      }
    }
  }
  return { entry, fatal: [...fatal].sort(), lazy: [...lazy].sort() };
}

const invokedDirectly =
  process.argv[1] !== undefined && import.meta.url.endsWith(process.argv[1].split("/").pop());

if (invokedDirectly) {
  let failed = false;
  for (const entry of WEBVIEW_ENTRIES) {
    const { fatal, lazy } = await inspect(entry);
    for (const name of lazy) {
      console.log(`  ~ ${entry}: ${name} imported lazily, fine while no webview path calls it`);
    }
    if (fatal.length > 0) {
      failed = true;
      console.error(`  FAIL ${entry}: Node builtins imported STATICALLY: ${fatal.join(", ")}`);
      console.error(`       These fail at IMPORT time in a webview: no error boundary, blank screen.`);
      console.error(`       Route them through globalThis equivalents, or move the module`);
      console.error(`       behind a Node-only entry point.`);
    } else {
      console.log(`  OK   ${entry}: loadable in a webview`);
    }
  }
  if (failed) {
    console.error("\npraisonai-ts is not webview-consumable. This is issue #4437 regressing.");
    process.exit(1);
  }
}
