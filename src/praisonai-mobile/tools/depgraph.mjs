/**
 * The layer rule, as callable functions.
 *
 * Two seams are the entire point of this package's shape, and both are only
 * real if something mechanical enforces them:
 *
 *   - the agent-framework seam: only engines/src/praisonai-ts may import
 *     "praisonai". Swapping frameworks is then a new directory plus a
 *     conformance run, never an edit above the seam.
 *   - the UI-shell seam: only adapters/src/tauri may import "@tauri-apps/*",
 *     and inside it only bridge.ts may do so directly. Swapping Tauri for
 *     React Native is then adapters/ plus ui/, and core/protocol/engines do
 *     not move.
 *
 * Imports come from a real esbuild parse rather than a regex. A regex reports
 * the specifier inside `const help = "import { invoke } from '@tauri-apps/api'"`
 * and misses `export * from`, and an over-reporting checker is one that gets
 * switched off -- at which point it protects nothing. tools/fixtures pins both
 * directions.
 *
 * Every function here is named and exported so tools/depgraph.test.mjs can CALL
 * it. A checker with no test that makes it report something is a checker that
 * passes on an empty result forever.
 */
import * as esbuild from "esbuild";
import { relative, resolve, dirname, sep } from "node:path";

/** Node builtins are always allowed; the bundler aliases or excludes them. */
const isBuiltin = (specifier) =>
  specifier.startsWith("node:") ||
  ["fs", "path", "os", "crypto", "events", "stream", "http", "https", "url", "util", "assert", "zlib", "child_process", "vm", "readline", "buffer", "process", "worker_threads"].includes(
    specifier,
  );

const isRelative = (specifier) => specifier.startsWith(".");

/** Posix-style, root-relative, so the rules read the same on every platform. */
const norm = (p) => p.split(sep).join("/");

/**
 * Every import specifier in `files`, keyed by root-relative path.
 *
 * `bundle: true` with an onResolve hook that marks everything external. That
 * combination is deliberate and the obvious alternative does not work:
 * `bundle: false` leaves `metafile.inputs[].imports` empty, because esbuild
 * never resolves anything -- so the checker reported no violations for every
 * file and the fixtures passed vacuously.
 */
export async function importsOf(files, root) {
  const out = new Map();
  for (const file of files) {
    const specifiers = [];
    await esbuild.build({
      entryPoints: [file],
      bundle: true,
      write: false,
      logLevel: "silent",
      outdir: "/tmp/praisonai-mobile-depgraph",
      plugins: [
        {
          name: "capture-specifiers",
          setup(build) {
            // Capture what the file DECLARES and stop there. Marking every
            // resolution external means nothing is followed and nothing needs
            // to be installed -- the rule is about a file's own imports, not
            // its transitive closure, and "@tauri-apps/api" must be reportable
            // whether or not it is in node_modules.
            build.onResolve({ filter: /.*/ }, (args) => {
              if (args.kind === "entry-point") return null;
              specifiers.push(args.path);
              return { path: args.path, external: true };
            });
          },
        },
      ],
    });
    out.set(norm(relative(root, resolve(file))), specifiers);
  }
  return out;
}

/** Which layer owns `relPath`, or null when no layer does. */
export function layerOf(relPath, config) {
  const p = norm(relPath);
  for (const [name, layer] of Object.entries(config.layers)) {
    if (p === layer.path || p.startsWith(layer.path + "/")) return name;
  }
  return null;
}

/**
 * Resolve a specifier to a layer name, or to a bare package name.
 *
 * A relative specifier is resolved against the importing file, so
 * "../../../protocol/src/events.ts" from core/src/run/ lands in protocol. A
 * bare specifier is reduced to its package name, so "@tauri-apps/api/core" and
 * "@tauri-apps/api" are the same rule.
 */
export function targetOf(specifier, fromFile, config) {
  if (isRelative(specifier)) {
    const resolved = norm(resolve("/" + dirname(norm(fromFile)), specifier)).replace(/^\//, "");
    return layerOf(resolved, config);
  }
  if (specifier.startsWith("@")) {
    const [scope, name] = specifier.split("/");
    return name === undefined ? scope : `${scope}/${name}`;
  }
  return specifier.split("/")[0];
}

/**
 * Does `relPath` fall under `pattern`?
 *
 * Three forms, because the allowlist needs all three: an exact file
 * ("adapters/src/tauri/bridge.ts"), a directory prefix ("adapters/src/tauri"),
 * and a glob ("**\/*.test.ts"). A prefix must stop at a path boundary or
 * "adapters/src/tau" would match "adapters/src/tauri/shell.ts".
 */
export function matchesAllowlist(pattern, relPath) {
  const p = norm(relPath);
  const pat = norm(pattern);
  if (pat.includes("*")) {
    // Substitute placeholders first. Replacing "**/" with "(?:.*/)?" and then
    // running a "*" -> "[^/]*" pass over the result corrupts the regex that
    // was just emitted, which is how this silently matched nothing.
    const GLOBSTAR_SLASH = "\u0000A";
    const GLOBSTAR = "\u0000B";
    const STAR = "\u0000C";
    const rx = new RegExp(
      "^" +
        pat
          .replace(/\*\*\//g, GLOBSTAR_SLASH)
          .replace(/\*\*/g, GLOBSTAR)
          .replace(/\*/g, STAR)
          .replace(/[.+^${}()|[\]\\]/g, "\\$&")
          .split(GLOBSTAR_SLASH).join("(?:.*/)?")
          .split(GLOBSTAR).join(".*")
          .split(STAR).join("[^/]*") +
        "$",
    );
    return rx.test(p);
  }
  if (/\.[a-z]+$/.test(pat)) return p === pat;
  return p === pat || p.startsWith(pat + "/");
}

/** Is this external package allowed from this file? */
function externalAllowed(pkg, relPath, config) {
  for (const [name, allowed] of Object.entries(config.externals ?? {})) {
    if (!matchesAllowlist(name, pkg) && name !== pkg) continue;
    return allowed.some((pattern) => matchesAllowlist(pattern, relPath));
  }
  // A package with no rule is unconstrained: the allowlist names the things
  // that are dangerous, not every dependency the package may ever use.
  return true;
}

/**
 * Every violation, as data. Four kinds, deliberately distinct -- an ungoverned
 * file is not a bad import, it is a hole in the rule itself, and collapsing the
 * two hides the more serious one.
 */
export function violations(importMap, config) {
  const found = [];
  for (const [file, specifiers] of importMap) {
    const from = layerOf(file, config);

    if (from === null) {
      found.push({
        kind: "ungoverned",
        file,
        specifier: "",
        from: null,
        to: null,
        message: `${file} belongs to no declared layer, so no rule covers it`,
      });
      continue;
    }

    // A test file may additionally reach the shared fakes. Production code may
    // not: a fake reachable from a shipped module is a fake that will one day
    // be shipped. The narrower rule is why this is keyed on the filename
    // rather than granted to the whole layer.
    const isTest = /\.test\.(ts|mjs)$/.test(file);
    const mayImport = [
      ...(config.layers[from].mayImport ?? []),
      ...(isTest ? (config.testImports ?? []) : []),
    ];

    for (const specifier of specifiers) {
      if (isBuiltin(specifier)) continue;

      const to = targetOf(specifier, file, config);
      if (to === null) continue; // relative import that leaves every layer

      const isLayer = Object.prototype.hasOwnProperty.call(config.layers, to);

      if (isLayer) {
        if (to === from) continue; // within a layer is always fine
        if (mayImport.includes(to)) continue;
        found.push({
          kind: "cross-layer",
          file,
          specifier,
          from,
          to,
          message: `${from} may not import ${to} (declared: ${mayImport.join(", ") || "nothing"})`,
        });
        continue;
      }

      if (!externalAllowed(to, file, config)) {
        found.push({
          kind: "external",
          file,
          specifier,
          from,
          to,
          message: `${to} is not allowed from ${file}`,
        });
      }
    }
  }
  return found;
}
