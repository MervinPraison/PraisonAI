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

/**
 * The BUILT entries, which are what a consumer actually resolves.
 *
 * Checking the TypeScript sources alone is not enough, and this gate shipped
 * with exactly that hole. `scripts/esm-shim.js` prepends a CJS banner --
 * `import { createRequire } from "module"`, plus `url` and `path` -- to any
 * emitted file whose source uses a bare synchronous `require()`. Three
 * first-party files on the mobile graph do.
 *
 * That banner does not exist until `build:esm` has run. So the source check
 * passed while `dist/esm/mobile.js` -- what `package.json` resolves
 * `praisonai/mobile` to -- failed with ten unresolved builtins, because the
 * banner had turned three LAZY requires into three STATIC Node imports. That
 * is precisely the failure this gate was written to prevent, arriving through
 * the one input it was not looking at.
 *
 * Checked only when `dist/` exists, so the gate still runs on a fresh clone;
 * CI builds first.
 */
export const BUILT_ENTRIES = ["dist/esm/mobile.js", "dist/esm/agent/simple.js"];

/** The webview baseline. iOS ships WKWebView with the OS, so the floor is the
 *  oldest iOS worth supporting rather than the newest Safari. */
export const TARGETS = ["safari16", "chrome108"];

/**
 * The SYNTAX floor, which is lower than the baseline above and checked
 * separately because it fails differently.
 *
 * The mobile app declares Android minSdkVersion 26 (8.0), whose system WebView
 * shipped as Chrome 58. Most modern syntax esbuild can lower for that target;
 * top-level await it cannot, and refuses. That is not academic: the
 * createRequire banner scripts/esm-shim.js prepended to three files on the
 * mobile graph was a top-level await, so the published entry bundled fine at
 * chrome108 -- the metafile check above passed -- and was unbuildable at the
 * floor the app actually ships with. Laziness does not help here: esbuild
 * rejects a top-level await anywhere on the graph, dynamically imported or not.
 */
export const FLOOR_TARGET = "chrome58";

function buildOptions(entry, target) {
  return {
    entryPoints: [entry],
    bundle: true,
    write: false,
    platform: "browser",
    format: "esm",
    target,
    logLevel: "silent",
    plugins: [{
      name: "surface-bare",
      setup(build) {
        // Bare specifiers stay external so they appear in the metafile rather
        // than being silently shimmed. Seeing the import is the whole point.
        build.onResolve({ filter: /^[^.\/]/ }, (args) => ({ path: args.path, external: true }));
      },
    }],
  };
}

/** Does the entry bundle at all for FLOOR_TARGET? esbuild's own errors are the
 *  diagnosis (each names the file and line, e.g. the top-level await). */
export async function bundlesAtFloor(entry) {
  try {
    await esbuild.build(buildOptions(entry, [FLOOR_TARGET]));
    return { entry, ok: true, errors: [] };
  } catch (e) {
    const errors = (e.errors ?? [{ text: String(e) }]).map((m) =>
      m.location ? `${m.text} (${m.location.file}:${m.location.line})` : m.text
    );
    return { entry, ok: false, errors };
  }
}

export async function inspect(entry) {
  const result = await esbuild.build({ ...buildOptions(entry, TARGETS), metafile: true });

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
  const { existsSync } = await import("node:fs");
  const built = BUILT_ENTRIES.filter((e) => existsSync(e));
  if (built.length === 0) {
    console.log("  note: dist/ is not built, so only sources were checked.");
    console.log("        Run `npm run build` first to check what actually ships.");
  }

  let failed = false;
  for (const entry of [...WEBVIEW_ENTRIES, ...built]) {
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

    const floor = await bundlesAtFloor(entry);
    if (!floor.ok) {
      failed = true;
      console.error(`  FAIL ${entry}: does not bundle for ${FLOOR_TARGET} (the Android 8 WebView floor):`);
      for (const err of floor.errors) console.error(`       - ${err}`);
      console.error(`       A top-level await here usually means a file on the graph still uses`);
      console.error(`       require()/__dirname and got the esm-shim createRequire banner.`);
    } else {
      console.log(`  OK   ${entry}: bundles for ${FLOOR_TARGET}`);
    }
  }
  if (failed) {
    console.error("\npraisonai-ts is not webview-consumable. This is issue #4437 regressing.");
    process.exit(1);
  }
}
