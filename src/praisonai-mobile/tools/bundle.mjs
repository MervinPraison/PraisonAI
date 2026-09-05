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
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

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
 * The oldest engines the bundle must PARSE on -- DERIVED from what the app
 * declares, not restated here.
 *
 * iOS ships WKWebView with the OS, so the floor is the oldest iOS worth
 * supporting rather than the newest Safari. Android's WebView updates through
 * Play, but a device kept offline keeps whatever it shipped with -- so the
 * floor there is the OS too, not the current Chrome. ANDROID_WEBVIEW_FLOOR is
 * that table, keyed by `minSdkVersion`, and the Chrome target is read THROUGH
 * it from `tauri.conf.json`. It has to be: `chrome108` sat here while the
 * config said `minSdkVersion: 26` (Android 8.0, WebView ~Chrome 58), and
 * nothing noticed. `index.html` loads the bundle as `<script type="module">`,
 * so post-58 syntax is a PARSE error: the module body never runs,
 * `installCrashHandler` never installs, and the AOSP, Play-less and
 * long-offline devices a floor exists to protect get a blank white screen with
 * no error surface and no telemetry. `bundle-target.test.mjs` builds the real
 * app at this target and scans every chunk.
 *
 * The in-process engine (`praisonai/mobile`, a lazily-fetched chunk) builds at
 * this floor because praisonai-ts's esm shim no longer puts top-level await on
 * its graph (praisonai-ts #4720) -- esbuild cannot lower that, so any target
 * below chrome89 produced no bundle at all. `praisonai` is a `file:` link to
 * ../praisonai-ts so the build that ships is the one with that fix in it, and
 * `bundle-target.test.mjs` asserts the built engine takes the floor.
 *
 * ONE construct is deliberately kept above the floor: `import()` itself, which
 * is Chrome 63. Left to esbuild, a target below that LOWERS the dynamic import
 * to a static one wrapped in a promise -- measured at chrome58: every chunk
 * becomes eager and the whole engine lands in the shell, 1486.8kB against a
 * 400kB budget, 0 lazy. So `bundle()` tells esbuild the target supports
 * dynamic import (`supported`), and SPLIT_MIN_CHROME records what the shipped
 * SHAPE needs regardless of the syntax target. A WebView that runs a `<script
 * type="module">` page at all is Chrome 61+, so the gap this leaves is Chrome
 * 61-62: the page loads and the shell's `import()` is a parse error.
 * ANDROID_WEBVIEW_FLOOR records no level between 26 (chrome58) and 30
 * (chrome87); whether `minSdkVersion` should move is recorded here, not
 * decided here.
 */
export const ANDROID_WEBVIEW_FLOOR = { 26: "chrome58", 30: "chrome87", 33: "chrome108" };
const tauriConf = JSON.parse(
  readFileSync(new URL("../src-tauri/tauri.conf.json", import.meta.url), "utf8"),
);
/** The Chrome the declared `minSdkVersion` ships. `undefined` when the table
 *  has no entry, and `bundle-target.test.mjs` says so rather than guessing. */
export const DECLARED_CHROME_FLOOR = ANDROID_WEBVIEW_FLOOR[tauriConf.bundle.android.minSdkVersion];
export const TARGETS = ["safari16", DECLARED_CHROME_FLOOR];

/** `chrome89` -> 89, so two floors can be compared rather than eyeballed. */
export function chromeMajor(target) {
  const m = /^chrome(\d+)$/.exec(target ?? "");
  return m ? Number(m[1]) : NaN;
}
/** The first Chrome whose `import()` esbuild leaves as an `import()`. Measured
 *  in bundle-target.test.mjs, one below and at; the header says why the build
 *  keeps it regardless of the floor. */
export const SPLIT_MIN_CHROME = "chrome63";

/** The installed praisonai's root -- through the `file:` link, so the real
 *  ../praisonai-ts directory -- or null when it is not installed. */
export function praisonaiRoot() {
  try {
    return dirname(createRequire(import.meta.url).resolve("praisonai/package.json"));
  } catch {
    return null;
  }
}

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
 * allowance or refuse the engine for being an engine. Measured at the
 * chrome58 floor: 1459.6kB across 16 chunks -- 1361kB of engine at chrome89
 * (zod 426kB, `ai` 276kB, @ai-sdk/openai 166kB, @ai-sdk/google 142kB, openai
 * 102kB, praisonai itself 79kB) plus ~100kB of lowering, because async
 * functions and classes become generators and prototypes below Chrome 55-72.
 * The ceiling sits ~10% above that on purpose: one more provider is 100-170kB
 * (measured), so adding one is a decision, not a drift.
 *
 * `tools/depgraph.test.mjs` pins both values; `bundle.test.mjs` proves each
 * can fail, and that neither is the other in disguise.
 */
export const SHELL_BUDGET_BYTES = 400 * 1024;
export const LAZY_BUDGET_BYTES = 1600 * 1024;

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
 * Every npm package whose source esbuild actually pulled INTO the bundle,
 * by package name.
 *
 * Read off `metafile.inputs` -- the files that were compiled in -- so it says
 * what SHIPPED rather than what was imported somewhere. An import esbuild left
 * external is not here; `classifyBareImports` is the function for those.
 *
 * Exported so a test can ask "is package X in the bundle?" by calling this
 * rather than re-deriving the node_modules path arithmetic inline, which is
 * the sort of predicate that keeps passing after the thing it checked moved.
 */
export function bundledPackages(metafile) {
  const found = new Set();
  for (const path of Object.keys(metafile.inputs ?? {})) {
    const at = path.lastIndexOf("node_modules/");
    if (at === -1) continue;
    const parts = path.slice(at + "node_modules/".length).split("/");
    found.add(parts[0].startsWith("@") ? `${parts[0]}/${parts[1]}` : parts[0]);
  }
  return [...found].sort();
}

/**
 * AI SDK PROVIDER packages a phone can never load, and must therefore never be
 * charged for.
 *
 * praisonai-ts reaches every chat provider through the registry in
 * `llm/providers/ai-sdk/provider-map.ts`, which does
 * `await import(providerInfo.package)` -- a computed specifier no bundler can
 * follow, so the package is the HOST's to supply at runtime. A webview has no
 * host resolver and no import map, so that import cannot succeed whatever the
 * bundle contains.
 *
 * `praisonai-ts`'s `llm/embeddings.ts` used to be the exception: three LITERAL
 * `import()` calls naming `@ai-sdk/openai`, `@ai-sdk/google` and
 * `@ai-sdk/cohere`. A literal is a BUNDLER instruction, so esbuild emitted all
 * three as chunks -- 326.7kB, measured, charged to the lazy budget -- on a
 * code path a phone has no way to reach and no reason to take. Routing
 * embeddings through the same registry removed them, and this list is what
 * stops them coming back one literal at a time.
 *
 * A hand-kept list of four packages was the wrong shape: praisonai-ts's
 * registry (`llm/providers/ai-sdk/types.ts`) names ~50 `@ai-sdk/*` providers,
 * so a literal `import('@ai-sdk/mistral')` -- or groq, deepseek, any of the
 * others -- would sail past a gate that only looked for openai/google/cohere/
 * anthropic and cost 100-170kB in silence until the budget tripped. So the
 * gate is a NAMESPACE rule now: every `@ai-sdk/*` package is host-loaded and
 * must not ship, and a new provider is covered the day it is added upstream,
 * with no second edit here.
 *
 * The exceptions are the packages `ai` is BUILT FROM, not providers it can
 * load: `ai` statically imports `@ai-sdk/provider`, `@ai-sdk/provider-utils`
 * and `@ai-sdk/gateway`, so they belong in the bundle for exactly as long as
 * `ai` does. They are named individually -- an allowlist, not a prefix -- so a
 * provider that happened to share a prefix could never hide behind them.
 */
export const AI_INTERNAL_AI_SDK_PACKAGES = [
  "@ai-sdk/provider", "@ai-sdk/provider-utils", "@ai-sdk/gateway",
];

/**
 * Whether `pkg` is an AI SDK PROVIDER a phone can never load (as opposed to one
 * of `ai`'s own internals). The `@ai-sdk/` namespace minus {@link
 * AI_INTERNAL_AI_SDK_PACKAGES}. Kept as a predicate, not a fixed list, so the
 * whole provider registry is covered without enumerating it here.
 */
export function isHostLoadedAISDKProvider(pkg) {
  return pkg.startsWith("@ai-sdk/") && !AI_INTERNAL_AI_SDK_PACKAGES.includes(pkg);
}

/**
 * The host-loaded providers actually present in a shipped bundle: every
 * `@ai-sdk/*` package `bundledPackages` found that is not one of `ai`'s
 * internals. Empty is the healthy state; anything here is pure weight on a code
 * path a webview cannot take.
 */
export function bundledHostLoadedProviders(metafile) {
  return bundledPackages(metafile).filter(isHostLoadedAISDKProvider);
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
/** This package: where bare imports are resolved from FIRST (see the plugin). */
const PACKAGE_ROOT = fileURLToPath(new URL("..", import.meta.url));

/**
 * @param options
 *   `outdir` turns on code splitting: the entry is written as `app.js` and
 *   everything behind an `import()` becomes a `chunk-*.js` beside it, which
 *   is the shape `index.html` loads. `outfile` is the single-file form, kept
 *   for the fixture tests and for a caller that wants one artefact.
 *   `targets` and `keepDynamicImport` exist for `bundle-target.test.mjs`:
 *   the first to measure a floor other than the declared one, the second to
 *   show that the `supported` override below is load-bearing.
 */
export async function bundle({
  entry, outfile, outdir, minify = true, write = true, targets = TARGETS, keepDynamicImport = true,
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
    // `import()` is what makes the engine a chunk, and it is Chrome 63. Below
    // that esbuild would LOWER it to a static import and quietly undo the
    // split -- the file header has the numbers. Kept as an import() at any
    // target; SPLIT_MIN_CHROME records what that costs. `false` leaves esbuild
    // to its own table, which is how the test measures it.
    ...(keepDynamicImport ? { supported: { "dynamic-import": true } } : {}),
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
          // Resolved from THIS package first, and from the importer second.
          //
          // Peers are the consumer's to provide: praisonai lists `ai` and
          // `@ai-sdk/*` as optional peers, this package declares them, and a
          // registry install hoists them beside praisonai where its imports
          // find them. Through the `file:` link Node's real-path resolution
          // looks in ../praisonai-ts/node_modules instead and cannot see them
          // -- `@ai-sdk/cohere`, which praisonai imports and never declares,
          // was reported unresolved, measured. Consumer-first is the layout a
          // registry install produces, without depending on hoisting to
          // produce it, and it keeps `zod` and `@ai-sdk/provider-utils` to
          // one copy. praisonai's own dependencies (openai, and the rest) are
          // not here and fall through to its node_modules, as they should.
          //
          // A specifier neither can resolve must not abort the build with
          // esbuild's own error: it is left external so it reaches the
          // metafile, where the `unresolved` check below names it in the
          // gate's words, alongside every other reason a bundle cannot ship.
          const probe = { kind: args.kind, importer: args.importer, pluginData: PROBE };
          const here = await build.resolve(args.path, { ...probe, resolveDir: PACKAGE_ROOT });
          if (here.errors.length === 0) {
            return { path: here.path, namespace: here.namespace, external: here.external, sideEffects: here.sideEffects };
          }
          const there = await build.resolve(args.path, { ...probe, resolveDir: args.resolveDir });
          return there.errors.length > 0 ? { path: args.path, external: true } : null;
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
  // By NAME, not "the first .js output": under `write: false` a split build's
  // outputFiles are in no particular order, and the first one was a chunk.
  const entryName = outPath.split("/").pop();
  const code = write
    ? await readFile(outPath, "utf8")
    : (result.outputFiles?.find((f) => f.path.split("/").pop() === entryName)?.text ?? "");

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
  // A bare import that is NOT a builtin and NOT a CLI-only external, and still
  // left the build as an external, is one the plugin's probe could not resolve
  // FROM ITS IMPORTER -- the same question esbuild asks, in the same place.
  // Read off the metafile rather than re-resolved from the entry, and that
  // matters now that `praisonai` is a `file:` link: its own dependencies
  // (openai, and the rest) live in ../praisonai-ts/node_modules and resolve
  // from there, not from this package's entry, so a resolve-from-the-entry
  // would call a bundled, working import "unresolved".
  //
  // A webview has no module resolver. `import "openai"` in the shipped file is
  // a hard failure at import time, before any code runs, with the same blank
  // screen as a Node builtin -- and the gate once said `shippable: true` for
  // exactly that: bundling praisonai-ts's webview entry reported 80.5kB, 0
  // problems, while silently leaving out openai, ai, @ai-sdk/*, chalk, ora,
  // boxen, figlet and cli-table3. Loads on a laptop with node_modules beside
  // it, dies on a phone.
  const unresolved = bare.filter(
    (name) =>
      !RUNTIME_MARKERS.has(name) &&
      !NODE_BUILTINS.includes(name.split("/")[0]) &&
      !CLI_ONLY_PACKAGES.includes(name.split("/")[0]),
  );
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
