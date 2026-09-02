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
import { readFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";

/** Node builtins that must never survive into a webview bundle. */
/** esbuild's own metafile markers, which are not packages. */
const RUNTIME_MARKERS = new Set(["<runtime>"]);

/** Every Node builtin, not only the forbidden ones. A builtin is already
 *  classified as fatal-or-lazy above; this list exists so the unresolved check
 *  does not report one twice under a different heading. */
const NODE_BUILTINS = [
  "assert", "async_hooks", "buffer", "child_process", "cluster", "console",
  "constants", "crypto", "dgram", "diagnostics_channel", "dns", "domain",
  "events", "fs", "http", "http2", "https", "inspector", "module", "net",
  "os", "path", "perf_hooks", "process", "punycode", "querystring",
  "readline", "repl", "stream", "string_decoder", "sys", "timers", "tls",
  "trace_events", "tty", "url", "util", "v8", "vm", "wasi", "worker_threads",
  "zlib",
];

export const FORBIDDEN_BUILTINS = [
  "assert", "buffer", "child_process", "cluster", "crypto", "dgram", "dns",
  "events", "fs", "http", "http2", "https", "module", "net", "os", "path",
  "perf_hooks", "process", "querystring", "readline", "repl", "stream",
  "string_decoder", "timers", "tls", "tty", "url", "util", "v8", "vm",
  "worker_threads", "zlib",
];

/**
 * Packages that exist only to make a TERMINAL pretty, and are reached only
 * through `await import()` on a CLI path -- praisonai's `utils/pretty-logger`,
 * which no mobile code calls, the same way its `createCLIApprovalPrompt` is the
 * only thing that reaches `readline`.
 *
 * They stay external on purpose. Bundling them drags `assert`, `buffer`,
 * `events`, `os`, `process`, `readline`, `string_decoder` and `util` in
 * STATICALLY -- measured -- which is the import-time blank screen this file
 * exists to prevent. External, they are a rejected dynamic import on a path a
 * phone never takes. That holds only while the import STAYS dynamic: an
 * external reached by a static import is import-time fatal, exactly like a
 * builtin, so `bundle()` fails on one below.
 */
export const CLI_ONLY_PACKAGES = ["chalk", "boxen", "ora", "cli-table3", "figlet"];

/**
 * The oldest engines the bundle must PARSE on -- DERIVED, in three steps, and
 * remembered by nobody.
 *
 * iOS ships WKWebView with the OS, so the floor is the oldest iOS worth
 * supporting rather than the newest Safari. Android's WebView updates through
 * Play, but a device kept offline keeps whatever it shipped with -- so the
 * floor there is the OS too, not the current Chrome. ANDROID_WEBVIEW_FLOOR is
 * that table, keyed by `minSdkVersion`, and the Chrome floor is read THROUGH
 * it from `tauri.conf.json` rather than restated here. It has to be:
 * `chrome108` sat here while the config said `minSdkVersion: 26` (Android
 * 8.0, WebView ~Chrome 58), and nothing noticed. `index.html` loads the bundle
 * as `<script type="module">`, so post-58 syntax is a PARSE error: the module
 * body never runs, `installCrashHandler` never installs, and the AOSP,
 * Play-less and long-offline devices a floor exists to protect get a blank
 * white screen with no error surface and no telemetry.
 *
 * Step two is the SPLIT. The in-process engine reaches the page as a chunk
 * behind an `import()`, and `import()` is Chrome 63. Below that esbuild does
 * not fail, it LOWERS: the dynamic import becomes a static one wrapped in a
 * promise, every chunk becomes eager, and the whole engine lands in the shell
 * -- measured at chrome58 with the shim removed: 1486.8kB of shell against a
 * 400kB budget, 0 lazy. So a lazily-loaded engine has a floor of its own,
 * above the declared one, and no upstream release moves it. (`<script
 * type="module">` is Chrome 61 besides, so nothing on chrome58 ever ran this
 * page at all.) Raising the target to SPLIT_MIN_CHROME is the honest minimum
 * for the shape this build ships; whether the declared minSdkVersion follows
 * is the maintainer's decision, and `bundle-target.test.mjs` is red until it
 * is made.
 *
 * Step three is the ENGINE, and this one clears itself. `praisonai/mobile`
 * ships at praisonai@1.7.4 with top-level await on line 1 of three of its
 * dist files: the `__praisonMod` shim that upstream's `scripts/esm-shim.js`
 * injects wherever a module used `require()`. esbuild cannot lower top-level
 * await, so below chrome89 there is not a worse bundle, there is NO bundle:
 * "Top-level await is not available in the configured target environment".
 * Upstream has already removed the shim from those modules (praisonai-ts PR
 * #4720); what is missing is a release. The target follows the release rather
 * than a person's memory of it: `engineFloorBlockers` transforms the three
 * files at the split floor, and the target is raised to ENGINE_MIN_CHROME only
 * while one of them still refuses. Bump `praisonai` to a release containing
 * #4720 and the target drops to SPLIT_MIN_CHROME on its own.
 */
export const ANDROID_WEBVIEW_FLOOR = { 26: "chrome58", 30: "chrome87", 33: "chrome108" };
const tauriConf = JSON.parse(
  readFileSync(new URL("../src-tauri/tauri.conf.json", import.meta.url), "utf8"),
);
/** The Chrome the declared `minSdkVersion` ships. `undefined` when the table
 *  has no entry, and `bundle-target.test.mjs` says so rather than guessing. */
export const DECLARED_CHROME_FLOOR = ANDROID_WEBVIEW_FLOOR[tauriConf.bundle.android.minSdkVersion];
/** `chrome89` -> 89, so two floors can be compared rather than eyeballed. */
export function chromeMajor(target) {
  const m = /^chrome(\d+)$/.exec(target ?? "");
  return m ? Number(m[1]) : NaN;
}
/** The highest of several Chrome targets; `undefined` if none is one. */
export function maxChrome(...targets) {
  return targets
    .filter((t) => !Number.isNaN(chromeMajor(t)))
    .sort((a, b) => chromeMajor(b) - chromeMajor(a))[0];
}
/** The first Chrome whose `import()` esbuild leaves as an `import()`; measured
 *  in bundle-target.test.mjs, one below and at. Below it there is no split. */
export const SPLIT_MIN_CHROME = "chrome63";
/** What the shipped SHAPE needs before the engine is even considered. */
export const SPLIT_CHROME_FLOOR = maxChrome(DECLARED_CHROME_FLOOR, SPLIT_MIN_CHROME);
/** Where the target is raised to while the engine carries top-level await:
 *  the first Chrome that parses it. */
export const ENGINE_MIN_CHROME = "chrome89";
/** The files on praisonai/mobile's graph that carried the shim at 1.7.4 -- the
 *  three, and only three, esbuild named at chrome58. A new one would not slip
 *  past this list: the build itself fails with esbuild's own message, and the
 *  probe-agrees-with-the-bundler test names the file. */
export const ENGINE_FLOOR_PROBE_FILES = [
  "llm/backend-resolver.js",
  "llm/providers/ai-sdk/index.js",
  "llm/providers/registry.js",
];

/** The installed praisonai's root, or null when it is not installed. */
export function praisonaiRoot() {
  try {
    return dirname(createRequire(import.meta.url).resolve("praisonai/package.json"));
  } catch {
    return null;
  }
}

/**
 * Which of ENGINE_FLOOR_PROBE_FILES cannot be parsed at `floor`, by asking
 * esbuild -- `transformSync` on each file alone, a few milliseconds and no
 * bundling, which is what makes it affordable at module load. Not installed,
 * or no floor recorded: nothing blocks, and the build fails loudly on the
 * unresolved import or the invalid target instead of quietly here.
 */
export function engineFloorBlockers(floor = SPLIT_CHROME_FLOOR) {
  const root = praisonaiRoot();
  if (root === null || floor === undefined) return [];
  return ENGINE_FLOOR_PROBE_FILES.filter((file) => {
    try {
      esbuild.transformSync(readFileSync(join(root, "dist/esm", file), "utf8"), {
        target: [floor], format: "esm", loader: "js",
      });
      return false;
    } catch (error) {
      if (/Top-level await is not available/.test(error.message)) return true;
      throw error;
    }
  });
}
export const ENGINE_FLOOR_BLOCKERS = engineFloorBlockers();
/** The Chrome target, derived: the declared floor, raised to what the split
 *  needs, raised again to what the installed engine needs -- for as long as
 *  it needs it. */
export const CHROME_TARGET = ENGINE_FLOOR_BLOCKERS.length > 0
  ? maxChrome(SPLIT_CHROME_FLOOR, ENGINE_MIN_CHROME)
  : SPLIT_CHROME_FLOOR;
export const TARGETS = ["safari16", CHROME_TARGET];

/**
 * The budgets. TWO numbers, because the build emits two populations of chunk
 * and they are paid for at different moments.
 *
 * SHELL_BUDGET_BYTES covers the entry chunk plus every chunk in its STATIC
 * import graph -- what a browser fetches and parses before the first frame, on
 * every cold start. This is the number that must stay tight, and it is the
 * 400kB the single-file budget always was: a single output file's total and
 * its shell cost were the same number. Measured after the split: 66.6kB, being
 * app.js at 65.9kB plus esbuild's 0.6kB CommonJS-interop helper chunk.
 *
 * LAZY_BUDGET_BYTES covers everything reachable only through `import()` --
 * today the in-process engine and the provider stack under it. It is NOT
 * free: whoever picks that engine waits for it, over whatever connection they
 * have. But it is paid once, after a deliberate choice, with the app already
 * on screen -- so it gets its own ceiling rather than being folded into the
 * shell's, which would either let the shell grow behind the engine's
 * allowance or refuse the engine for being an engine. Measured: 1361kB across
 * 19 chunks, of which zod is 426kB, `ai` 276kB, @ai-sdk/openai 166kB,
 * @ai-sdk/google 142kB, openai 102kB, and praisonai itself 79kB. The ceiling
 * sits ~10% above that on purpose: one more provider is 100-170kB (measured),
 * so adding one is a decision, not a drift.
 *
 * `tools/depgraph.test.mjs` pins both values; `bundle.test.mjs` proves each
 * can fail, and that neither is the other in disguise.
 */
export const SHELL_BUDGET_BYTES = 400 * 1024;
export const LAZY_BUDGET_BYTES = 1500 * 1024;

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

/**
 * Every emitted JS chunk with its byte count, keyed by basename.
 *
 * Read off the metafile rather than by stat-ing the directory, so it works
 * with `write: false` and so a stale file left by an earlier build cannot be
 * counted as part of this one.
 */
export function chunkSizes(metafile) {
  return Object.entries(metafile.outputs)
    .filter(([path]) => path.endsWith(".js"))
    .map(([path, out]) => ({ name: path.split("/").pop(), bytes: out.bytes, entry: out.entryPoint !== undefined }))
    .sort((a, b) => b.bytes - a.bytes || a.name.localeCompare(b.name));
}

/**
 * The chunks a browser fetches BEFORE the entry's body runs: the entry itself
 * plus the transitive closure of its STATIC imports.
 *
 * This is the distinction the whole split rests on. A chunk reached only
 * through `import()` is fetched when someone picks the feature; a chunk in the
 * static graph is paid for at first paint whether or not it is ever used. If
 * an engine chunk ever lands in here, splitting has silently stopped working
 * and the only visible symptom is a slower cold start.
 */
export function eagerChunks(metafile, entryPath) {
  const byName = new Map();
  for (const [path, out] of Object.entries(metafile.outputs)) {
    if (path.endsWith(".js")) byName.set(path.split("/").pop(), out);
  }
  // The entry is named, never guessed. esbuild marks EVERY chunk that is the
  // target of a dynamic import with an `entryPoint` too, so "the output with
  // an entryPoint" picks an arbitrary lazy chunk -- measured: it reported a
  // 672kB shell for a 66kB one, which is a gate that fails for the wrong
  // reason and would be "fixed" by raising the budget.
  const start = entryPath?.split("/").pop()
    ?? [...byName.keys()].find((n) => n === "app.js");
  if (start === undefined || !byName.has(start)) return new Set();
  const seen = new Set([start]);
  const queue = [start];
  while (queue.length > 0) {
    const name = queue.pop();
    for (const imported of byName.get(name)?.imports ?? []) {
      // `dynamic-import` is the edge that makes a chunk lazy. Everything else
      // -- import-statement, require-call -- runs before the importer's body.
      if (imported.kind === "dynamic-import") continue;
      const next = imported.path.split("/").pop();
      if (byName.has(next) && !seen.has(next)) {
        seen.add(next);
        queue.push(next);
      }
    }
  }
  return seen;
}

/** Marks a resolution the plugin below started itself, so it lets it through. */
const PROBE = Symbol("resolve-probe");

/**
 * @param options
 *   `outdir` turns on code splitting: the entry is written as `app.js` and
 *   everything behind an `import()` becomes a `chunk-*.js` beside it, which
 *   is the shape `index.html` loads. `outfile` is the single-file form, kept
 *   for the fixture tests and for a caller that wants one artefact.
 *   `targets` and `external` exist for `bundle-target.test.mjs`, which needs
 *   to build the shell at the DECLARED floor with the engine left out to show
 *   which of the two is the one that cannot parse there.
 */
export async function bundle({
  entry, outfile, outdir, minify = true, write = true, targets = TARGETS, external = [],
}) {
  const splitting = outdir !== undefined;
  const result = await esbuild.build({
    entryPoints: [entry],
    ...(splitting
      ? { outdir, splitting: true, entryNames: "app", chunkNames: "chunk-[hash]" }
      : { outfile }),
    bundle: true,
    format: "esm",
    platform: "browser",
    target: targets,
    minify,
    sourcemap: true,
    metafile: true,
    write,
    logLevel: "silent",
    // Node builtins and the CLI-only pretty-printers stay external, so they
    // show up in the metafile as unresolved rather than being silently
    // shimmed. That is the point: we want to SEE a `crypto` import, not have
    // esbuild paper over it.
    //
    // Everything else bare is left to esbuild to RESOLVE AND BUNDLE. It used
    // to be externalised too, which quietly made splitting impossible: an
    // external `import("praisonai/mobile")` survives verbatim into the output,
    // a webview has no resolver for it, and the gate passed because the
    // specifier resolves on the build machine. Bundling it is what turns it
    // into a chunk.
    plugins: [{
      name: "surface-bare-imports",
      setup(build) {
        build.onResolve({ filter: /^[^.\/]/ }, async (args) => {
          // The probe below re-enters this hook; hand that one to esbuild.
          if (args.pluginData === PROBE) return null;
          const head = args.path.replace(/^node:/, "").split("/")[0];
          if (NODE_BUILTINS.includes(head)) return { path: args.path, external: true };
          if (CLI_ONLY_PACKAGES.includes(head)) return { path: args.path, external: true };
          if (external.includes(args.path) || external.includes(head)) {
            return { path: args.path, external: true };
          }
          // A specifier esbuild cannot resolve must not abort the build with
          // esbuild's own error: it is left external so it reaches the
          // metafile, where the `unresolved` check below names it in the
          // gate's words, alongside every other reason a bundle cannot ship.
          const probe = await build.resolve(args.path, {
            kind: args.kind, importer: args.importer, resolveDir: args.resolveDir, pluginData: PROBE,
          });
          return probe.errors.length > 0 ? { path: args.path, external: true } : null;
        });
      },
    }],
  });

  // Chunk accounting. `outputs` in the metafile is keyed by path and carries
  // both the byte count and, crucially, the IMPORTS of each chunk with their
  // kind -- so eager and lazy are read off the real graph rather than guessed
  // from a filename.
  const chunks = chunkSizes(result.metafile);
  // The entry chunk's own path, named rather than guessed (see eagerChunks).
  // Under `outdir` that is always app.js -- `entryNames: "app"` above -- and
  // under `outfile` it is the file itself.
  const outPath = splitting
    ? Object.keys(result.metafile.outputs).find((o) => /(^|\/)app\.js$/.test(o))
    : outfile;
  const eagerNames = eagerChunks(result.metafile, outPath);
  const shellBytes = chunks
    .filter((c) => eagerNames.has(c.name))
    .reduce((a, c) => a + c.bytes, 0);
  const lazyBytes = chunks
    .filter((c) => !eagerNames.has(c.name))
    .reduce((a, c) => a + c.bytes, 0);

  // The ENTRY chunk's text, for the source-level checks: a top-level
  // process.env read is only import-time fatal in a chunk that loads at
  // import time.
  const code = write
    ? await readFile(outPath, "utf8")
    : (result.outputFiles?.find((f) => f.path.endsWith(".js"))?.text ?? "");

  const classified = classifyBareImports(result.metafile);
  const bare = [...classified.keys()].sort();
  const forbidden = forbiddenAmong(bare);
  const fatal = forbidden.filter((p) => classified.get(p) === "static");
  const lazy = forbidden.filter((p) => classified.get(p) === "dynamic");
  // A CLI-only package is external by design, and an EXTERNAL that is imported
  // statically dies at import time exactly like a builtin. Neither check above
  // sees it: it is not a builtin, and it resolves fine on the build machine.
  const cliStatic = bare.filter(
    (p) => CLI_ONLY_PACKAGES.includes(p.split("/")[0]) && classified.get(p) === "static",
  );
  // A bare import that is NOT a Node builtin and still left the build as an
  // external is one esbuild could not resolve -- the package is not installed.
  //
  // A webview has no module resolver. `import "openai"` in the shipped file is
  // a hard failure at import time, before any code runs, with the same blank
  // screen as a Node builtin -- and until now the gate said `shippable: true`
  // for it, because `problems` was built only from forbidden BUILTINS, top
  // level process.env, and size.
  //
  // Measured: bundling praisonai-ts's webview entry through this gate reported
  // 80.5kB, 0 problems and `shippable: true` while silently leaving out
  // openai, ai, @ai-sdk/cohere, @ai-sdk/google, @ai-sdk/openai,
  // @ai-sdk/provider-utils, chalk, ora, boxen, figlet and cli-table3. That
  // bundle loads on a laptop with node_modules beside it and dies on a phone.
  //
  // CORRECTED. The first version of this asked "did it stay external?", which
  // is true of EVERY bare import here -- the plugin below externalises them all
  // on purpose, so builtins surface in the metafile instead of being shimmed.
  // So it flagged installed, perfectly resolvable packages as unresolvable, and
  // only passed because the shipped bundle happens to have no bare imports at
  // all. Confirmed against a real install: `praisonai/mobile` resolves to
  // node_modules/praisonai/dist/mobile.js and was reported unresolved anyway.
  //
  // The question that actually matters is whether the specifier can be
  // RESOLVED from the entry, so it is asked directly.
  const resolver = createRequire(resolve(entry));
  const unresolved = bare.filter((name) => {
    if (RUNTIME_MARKERS.has(name)) return false;
    // Redundant in practice and kept for intent: `createRequire` resolves
    // builtins too, so removing this line changes nothing (verified). A
    // builtin is already classified as fatal-or-lazy above and must not be
    // reported twice under a different heading -- that is what this says.
    if (NODE_BUILTINS.includes(name.split("/")[0])) return false;
    try {
      resolver.resolve(name);
      return false;
    } catch {
      return true;
    }
  });
  const processReads = topLevelProcessReads(code);
  // `bytes` is the SHELL cost. For a single-file build that is the whole file,
  // which is what the name always meant; for a split build it is what the
  // page pays before first paint, which is what the name should have meant.
  const bytes = shellBytes;

  const problems = [];
  if (fatal.length > 0) {
    problems.push(
      `Node builtins imported STATICALLY: ${fatal.join(", ")}.\n` +
      `    These fail at IMPORT time, before any code runs -- there is no error\n` +
      `    boundary and the screen stays blank. Alias them or fix upstream.`,
    );
  }
  if (cliStatic.length > 0) {
    problems.push(
      `CLI-only packages imported STATICALLY: ${cliStatic.join(", ")}.\n` +
      `    They are left external on purpose (CLI_ONLY_PACKAGES), which is safe\n` +
      `    only behind an import() on a path a phone never takes. A static import\n` +
      `    of an external fails at IMPORT time like a builtin does.`,
    );
  }
  if (processReads.length > 0) {
    problems.push(
      `top-level process.env reads (${processReads.length}):\n` +
      processReads.map((h) => `      line ${h.line}: ${h.text}`).join("\n") +
      `\n    A webview has no process. Route these through a guarded accessor.`,
    );
  }
  if (unresolved.length > 0) {
    problems.push(
      `bare imports the build could not resolve: ${unresolved.join(", ")}.\n` +
      `    A webview has no module resolver, so these fail at IMPORT time and the\n` +
      `    screen stays blank -- exactly like a static Node builtin. Add them as\n` +
      `    dependencies so they are bundled, or stop importing them.`,
    );
  }
  // TWO budgets, because the two populations are paid at different moments.
  // Folding them into one number would either let the shell grow behind a
  // lazy allowance or refuse a lazily-loaded engine for being big, and both
  // of those are the wrong answer.
  if (shellBytes > SHELL_BUDGET_BYTES) {
    problems.push(
      `the SHELL is ${(shellBytes / 1024).toFixed(1)}kB, over the ${(SHELL_BUDGET_BYTES / 1024).toFixed(0)}kB shell budget.\n` +
      `    That is the entry chunk plus everything statically imported from it --\n` +
      `    fetched and parsed before the first frame, on every cold start.`,
    );
  }
  if (lazyBytes > LAZY_BUDGET_BYTES) {
    problems.push(
      `chunks behind an import() total ${(lazyBytes / 1024).toFixed(1)}kB, over the ` +
      `${(LAZY_BUDGET_BYTES / 1024).toFixed(0)}kB lazy budget.`,
    );
  }

  return {
    bytes, shellBytes, lazyBytes, chunks, eager: eagerNames,
    bare, forbidden, fatal, lazy, cliStatic, unresolved, processReads,
    problems, metafile: result.metafile, code,
  };
}

/** CLI. Guarded so importing this module for tests does not run a build. */
if (process.argv[1] && import.meta.url.endsWith(process.argv[1].split("/").pop())) {
  const entry = process.argv[2] ?? "app/src/main.ts";
  const outdir = process.argv[3] ?? "dist";
  const report = await bundle({ entry, outdir });
  for (const problem of report.problems) console.error(`  ✖ ${problem}`);
  for (const name of report.lazy) {
    // Reported, never silent: a lazy builtin is fine only while nothing on a
    // phone calls into it, and that is a claim worth restating every build.
    console.log(`  ! ${name} is imported lazily -- fine while no mobile path calls it`);
  }
  console.log(
    `bundle: shell ${(report.shellBytes / 1024).toFixed(1)}kB of ` +
    `${(SHELL_BUDGET_BYTES / 1024).toFixed(0)}kB, lazy ${(report.lazyBytes / 1024).toFixed(1)}kB of ` +
    `${(LAZY_BUDGET_BYTES / 1024).toFixed(0)}kB, ${report.chunks.length} chunks, ` +
    `${report.bare.length} external`,
  );
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
