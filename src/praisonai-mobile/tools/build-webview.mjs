/**
 * The webview build: bundle the app, and copy the two files a page needs.
 *
 * Deliberately separate from tools/bundle.mjs, which is a GATE rather than a
 * build system -- its header is explicit that every check fails the build
 * rather than warning, and mixing a copy step into it would blur that.
 */
import { mkdir, copyFile, rm } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { bundle } from "./bundle.mjs";

const here = dirname(new URL(import.meta.url).pathname);
const pkg = resolve(here, "..");
const dist = join(pkg, "dist");

await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });

// The page and the stylesheet are copied verbatim: neither is compiled, and a
// transform step would be one more thing between what is written and what
// ships.
await copyFile(join(pkg, "app/index.html"), join(dist, "index.html"));
await copyFile(join(pkg, "app/app.css"), join(dist, "app.css"));

const report = await bundle({
  entry: join(pkg, "app/src/main.ts"),
  outfile: join(dist, "app.js"),
});

for (const name of report.lazy) {
  console.log(`  ! ${name} is imported lazily -- fine while no mobile path calls it`);
}
for (const problem of report.problems) {
  console.error(`  ✖ ${problem}`);
}
console.log(`bundle: ${(report.bytes / 1024).toFixed(1)}kB of a 400kB budget, ${report.bare.length} external`);

if (report.problems.length > 0) {
  console.error("\nThe webview bundle is not shippable. See above.");
  process.exit(1);
}
