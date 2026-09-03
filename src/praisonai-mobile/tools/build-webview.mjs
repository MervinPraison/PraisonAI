/**
 * The webview build: bundle the app, and copy the files a page needs.
 *
 * Deliberately separate from tools/bundle.mjs, which is a GATE rather than a
 * build system -- its header is explicit that every check fails the build
 * rather than warning, and mixing a copy step into it would blur that.
 *
 * dist/ serves two consumers from one output: the Tauri shell (frontendDist)
 * and the web build deployed by .github/workflows/mobile-web.yml. The web
 * additions -- manifest, icons, service worker -- are inert inside the shell
 * (app/register-sw.js declines to register there), so one build is enough.
 */
import { mkdir, copyFile, rm, readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { dirname, join, resolve } from "node:path";
import { bundle, isShippable, SHELL_BUDGET_BYTES, LAZY_BUDGET_BYTES } from "./bundle.mjs";

const here = dirname(new URL(import.meta.url).pathname);
// Overridable so a test can drive the real script against a package whose
// bundle is deliberately unshippable. Removing the `process.exit(1)` below
// survived: the errors are printed and the build "succeeds", shipping a
// dist/ that dies on load.
const pkg = resolve(process.argv[2] ?? here + "/..");
const dist = join(pkg, "dist");

await rm(dist, { recursive: true, force: true });
await mkdir(join(dist, "icons"), { recursive: true });

// The page, the stylesheet, the manifest and the registration script are
// copied verbatim: none is compiled, and a transform step would be one more
// thing between what is written and what ships.
const verbatim = ["index.html", "app.css", "manifest.webmanifest", "register-sw.js"];
for (const name of verbatim) {
  await copyFile(join(pkg, "app", name), join(dist, name));
}

// The icons are whichever the manifest names, read from the Tauri icon set so
// the two platforms cannot drift: an icon the manifest lists but the shell
// does not have fails here, not on a phone's home screen.
const manifest = JSON.parse(await readFile(join(pkg, "app/manifest.webmanifest"), "utf8"));
const icons = manifest.icons.map((icon) => icon.src);
for (const src of icons) {
  if (!src.startsWith("./icons/")) throw new Error(`manifest icon must live under ./icons/: ${src}`);
  const name = src.slice("./icons/".length);
  await copyFile(join(pkg, "src-tauri/icons", name), join(dist, "icons", name));
}

// `outdir`, not `outfile`: esbuild's `splitting` needs a directory to put the
// shared and lazily-loaded chunks in. `entryNames` pins the entry to app.js so
// index.html's `<script type="module" src="./app.js">` keeps working unchanged.
const report = await bundle({
  entry: join(pkg, "app/src/main.ts"),
  outdir: dist,
});

for (const name of report.lazy) {
  console.log(`  ! ${name} is imported lazily -- fine while no mobile path calls it`);
}
for (const problem of report.problems) {
  console.error(`  ✖ ${problem}`);
}
for (const chunk of report.chunks) {
  const when = report.eager.has(chunk.name) ? "eager" : "lazy ";
  console.log(`  ${when} ${chunk.name.padEnd(22)} ${(chunk.bytes / 1024).toFixed(1)}kB`);
}
console.log(
  `bundle: shell ${(report.shellBytes / 1024).toFixed(1)}kB of a ` +
  `${(SHELL_BUDGET_BYTES / 1024).toFixed(0)}kB budget, lazy ` +
  `${(report.lazyBytes / 1024).toFixed(1)}kB of a ${(LAZY_BUDGET_BYTES / 1024).toFixed(0)}kB budget, ` +
  `${report.chunks.length} chunks, ${report.bare.length} external`,
);

if (!isShippable(report)) {
  console.error("\nThe webview bundle is not shippable. See above.");
  process.exit(1);
}

// The service worker is the one file whose contents depend on the build: it
// precaches exactly what was just written, under a cache name derived from
// those bytes. A hash rather than the package version, because two builds of
// one version differ the moment a source file does, and a worker that thinks
// they are the same serves the old one forever.
// What the worker precaches is every file needed to RENDER the app with no
// network: the page, the stylesheet, the manifest, the icons, and the entry
// plus every chunk esbuild marked EAGER.
//
// Read off `report.eager` rather than hand-written. A hand-written list was
// wrong the moment code splitting landed: `splitting` gave app.js an eager
// chunk-*.js sibling that nothing precached, so the app rendered online and
// died on an offline reload -- tools/web-boot.test.mjs caught exactly that.
//
// The LAZY chunks are deliberately not here. Splitting exists so a browser
// does not pay 1.4MB it may never use, and precaching them would undo the
// whole point; app/sw.js caches them as they are fetched instead, so a
// feature keeps working offline once it has been used.
const eager = [...report.eager].sort().map((name) => `./${name}`);
const precache = [...verbatim.map((name) => `./${name}`), ...eager, ...icons];
const hash = createHash("sha256");
for (const entry of precache) {
  hash.update(entry);
  hash.update(await readFile(join(dist, entry)));
}
const buildId = hash.digest("hex").slice(0, 16);
const template = await readFile(join(pkg, "app/sw.js"), "utf8");
for (const token of ["__BUILD_ID__", "__PRECACHE__"]) {
  if (!template.includes(token)) throw new Error(`app/sw.js has lost its ${token} token`);
}
const sw = template.replace("__BUILD_ID__", buildId).replace("__PRECACHE__", JSON.stringify(precache));
await writeFile(join(dist, "sw.js"), sw);
console.log(`service worker: cache praisonai-mobile-${buildId}, ${precache.length} files precached`);
