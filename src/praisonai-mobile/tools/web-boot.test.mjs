/**
 * Boot proof: the built dist/ loads in a real browser and works as a PWA.
 *
 * Every other test here runs in Node. This one serves dist/ over HTTP -- under
 * a repository subpath, because that is how GitHub Pages serves it -- and
 * drives headless Chromium through the states a user actually meets:
 *
 *   1. first load: the page boots, the composer and Send render, and the only
 *      console error is the engine at 127.0.0.1:8765 not answering (which the
 *      page reports as a notice, not a crash);
 *   2. the manifest is linked and served as application/manifest+json, and its
 *      start_url resolves inside the subpath;
 *   3. the service worker registers with the subpath as its scope and finishes
 *      precaching;
 *   4. the server is then shut down and the page reloaded: it must render from
 *      the cache with no network at all;
 *   5. the CSP is enforced: an inline script injected at runtime does not run.
 *
 * The engine port is intercepted and refused, so the outcome does not depend
 * on whether a desktop engine happens to be running on this machine.
 *
 * The browser is Playwright's Chromium (`npx playwright install chromium`),
 * falling back to an installed Google Chrome. Neither being present FAILS the
 * suite rather than skipping it: a boot proof that skips is a page nobody has
 * seen boot.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, extname, join, normalize, resolve } from "node:path";
import { chromium } from "playwright";

const pkg = resolve(dirname(new URL(import.meta.url).pathname), "..");
const dist = join(pkg, "dist");
/** The subpath GitHub Pages serves a project site from. */
const BASE = "/PraisonAI/";
const ENGINE = "http://127.0.0.1:8765";

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".webmanifest": "application/manifest+json",
  ".png": "image/png",
};

/**
 * dist/ under BASE, and nothing else.
 *
 * `overrides` maps a dist-relative path to the bytes to serve INSTEAD of the
 * file on disk. That is how the redeploy test below stands up a "v2" of the
 * site without rebuilding or touching a source file: the deployed bytes
 * change under a browser that already has the old ones cached, which is
 * exactly the situation a service worker either handles or makes permanent.
 */
function serveDist(overrides = new Map()) {
  const server = createServer(async (req, res) => {
    const url = new URL(req.url, "http://x");
    if (!url.pathname.startsWith(BASE)) {
      res.writeHead(404).end("outside the site's subpath");
      return;
    }
    let rel = url.pathname.slice(BASE.length);
    if (rel === "" || rel.endsWith("/")) rel += "index.html";
    if (overrides.has(rel)) {
      res.writeHead(200, { "content-type": MIME[extname(rel)] ?? "application/octet-stream", "cache-control": "no-store" });
      res.end(overrides.get(rel));
      return;
    }
    const file = normalize(join(dist, rel));
    if (!file.startsWith(dist) || !existsSync(file)) {
      res.writeHead(404).end("not found");
      return;
    }
    res.writeHead(200, { "content-type": MIME[extname(file)] ?? "application/octet-stream", "cache-control": "no-store" });
    res.end(await readFile(file));
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok(server)));
}

async function launch() {
  try {
    return await chromium.launch();
  } catch (bundled) {
    try {
      return await chromium.launch({ channel: "chrome" });
    } catch (system) {
      throw new Error(
        "no browser for the boot proof: run `npx playwright install chromium` (or install Google Chrome).\n" +
          `  bundled: ${bundled.message.split("\n")[0]}\n  system: ${system.message.split("\n")[0]}`,
      );
    }
  }
}

test("the built web app boots, installs, and survives going offline", async (t) => {
  const built = spawnSync(process.execPath, [join(pkg, "tools/build-webview.mjs")], { encoding: "utf8" });
  assert.equal(built.status, 0, `the build must succeed before it can be booted:\n${built.stdout}${built.stderr}`);

  const server = await serveDist();
  const origin = `http://127.0.0.1:${server.address().port}`;
  const site = origin + BASE;
  const browser = await launch();
  t.after(async () => {
    await browser.close();
    server.closeAllConnections?.();
    await new Promise((ok) => server.close(ok));
  });

  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(`console.error: ${m.text()} @ ${m.location().url}`);
  });
  // Refuse the engine deterministically: this proof must not depend on a
  // desktop engine being up or down on the machine running it.
  await page.route((u) => u.href.startsWith(ENGINE), (route) => route.abort("connectionrefused"));

  // ---- 1. first load ------------------------------------------------------
  const response = await page.goto(site, { waitUntil: "load" });
  assert.equal(response.status(), 200);
  await page.locator('textarea[aria-label="Message"]').waitFor({ timeout: 15_000 });
  const send = page.locator('button[data-action="send"]');
  await send.waitFor();
  assert.equal(await send.textContent(), "Send", "the Send control renders with its label");
  await page.locator('.row-notice[data-tone="warning"]').waitFor({ timeout: 15_000 });
  assert.match(
    await page.locator('.row-notice[data-tone="warning"]').first().textContent(),
    /not answering/,
    "no engine reachable is reported as a notice, and the composer stays usable",
  );
  const unexpected = errors.filter((e) => !e.includes(ENGINE));
  assert.deepEqual(unexpected, [], `console errors on boot:\n${unexpected.join("\n")}`);

  // ---- 2. manifest ----------------------------------------------------------
  const manifestHref = await page.evaluate(() => document.querySelector('link[rel="manifest"]')?.href ?? null);
  assert.ok(manifestHref, "index.html must link a web app manifest");
  assert.ok(manifestHref.startsWith(site), `the manifest resolves inside the subpath, got ${manifestHref}`);
  const manifestRes = await page.request.get(manifestHref);
  assert.equal(manifestRes.status(), 200);
  assert.match(manifestRes.headers()["content-type"], /^application\/manifest\+json/);
  const manifest = await manifestRes.json();
  assert.equal(manifest.display, "standalone");
  assert.equal(new URL(manifest.start_url, manifestHref).href, site, "start_url resolves to the subpath root");
  assert.equal(new URL(manifest.scope, manifestHref).href, site, "and so does scope");
  for (const icon of manifest.icons) {
    const r = await page.request.get(new URL(icon.src, manifestHref).href);
    assert.equal(r.status(), 200, `icon ${icon.src} must be served`);
    assert.match(r.headers()["content-type"], /^image\/png/);
  }
  assert.ok(manifest.icons.some((i) => i.sizes === "512x512"), "a 512x512 icon is required to be installable");

  // ---- 3. service worker --------------------------------------------------
  // An explicit poll rather than page.waitForFunction: with an async
  // predicate that one resolved on a falsy value instead of polling, so it
  // could return before activation -- or, with no registration at all,
  // return null instantly and make the next line the failure.
  const activeScope = () =>
    page.evaluate(async () => {
      const reg = await navigator.serviceWorker.getRegistration();
      return reg?.active?.state === "activated" ? reg.scope : null;
    });
  const deadline = Date.now() + 20_000;
  let scope = await activeScope();
  while (scope === null && Date.now() < deadline) {
    await new Promise((ok) => setTimeout(ok, 100));
    scope = await activeScope();
  }
  assert.ok(scope !== null, "no service worker became active within 20s: is it registered?");
  assert.equal(scope, site, "the worker's scope is the subpath");
  const swRes = await page.request.get(site + "sw.js");
  assert.match(swRes.headers()["content-type"], /^text\/javascript/);
  const cached = await page.evaluate(async () => {
    const keys = await caches.keys();
    const hits = {};
    for (const rel of ["index.html", "app.js", "app.css", "manifest.webmanifest", "register-sw.js"]) {
      hits[rel] = (await caches.match(new URL(rel, location.href).href)) !== undefined;
    }
    return { keys, hits };
  });
  assert.equal(cached.keys.length, 1, `exactly one cache, got ${cached.keys}`);
  assert.match(cached.keys[0], /^praisonai-mobile-[0-9a-f]{16}$/);
  for (const [rel, hit] of Object.entries(cached.hits)) assert.ok(hit, `${rel} must be precached`);

  // ---- 4. offline ---------------------------------------------------------
  // Take the page under the worker's control, then take the network away for
  // real: the server stops accepting connections, and the browser is told it
  // is offline as well. If the reload renders, it rendered from the cache.
  await page.reload({ waitUntil: "load" });
  assert.ok(await page.evaluate(() => navigator.serviceWorker.controller !== null), "the page is controlled by the worker");
  server.closeAllConnections?.();
  await new Promise((ok) => server.close(ok));
  await context.setOffline(true);
  const offlineErrors = [];
  page.on("pageerror", (e) => offlineErrors.push(e.message));
  await page.goto(site, { waitUntil: "load" });
  await page.locator('textarea[aria-label="Message"]').waitFor({ timeout: 15_000 });
  assert.equal(await page.locator('button[data-action="send"]').textContent(), "Send", "Send renders offline");
  assert.deepEqual(offlineErrors, [], "no script error offline");
  assert.equal(await page.evaluate(() => document.styleSheets.length > 0 && getComputedStyle(document.body).margin), "0px", "the stylesheet came from the cache too");

  // ---- 5. CSP is enforced -------------------------------------------------
  const ran = await page.evaluate(() => {
    const s = document.createElement("script");
    s.textContent = "window.__inline_ran = true";
    document.body.append(s);
    return window.__inline_ran === true;
  });
  assert.equal(ran, false, "script-src 'self' must block an inline script");
});

test("a redeployed site replaces the cached one instead of being pinned behind it", async (t) => {
  // A stale-cache service worker is worse than no service worker: it pins
  // every returning visitor to a build that has been replaced, and the user
  // cannot tell, cannot fix it, and will not report it. Two mechanisms stop
  // that, and BOTH survived being deleted until this test existed:
  //
  //   - navigation is network-first. A cache-first HTML entry serves the old
  //     page for as long as the cache lives, so a deploy reaches nobody.
  //   - `activate` deletes every cache but the current one. Without it the
  //     old build's bytes stay on disk forever, and the first bug in the
  //     eviction order pairs an old chunk with a new page.
  //
  // The first test's assertions could not see either: one browser context,
  // one build, one cache, so "exactly one cache" was true whether or not
  // anything was ever deleted. This one deploys a SECOND version under a
  // browser that already holds the first.
  const built = spawnSync(process.execPath, [join(pkg, "tools/build-webview.mjs")], { encoding: "utf8" });
  assert.equal(built.status, 0, `${built.stdout}${built.stderr}`);

  const v1Html = await readFile(join(dist, "index.html"), "utf8");
  const v1Sw = await readFile(join(dist, "sw.js"), "utf8");
  const v1Cache = /const CACHE = "(praisonai-mobile-[0-9a-f]{16})";/.exec(v1Sw)?.[1];
  assert.ok(v1Cache, "the built worker must name a versioned cache for this test to version it");

  const overrides = new Map();
  const server = await serveDist(overrides);
  const origin = `http://127.0.0.1:${server.address().port}`;
  const site = origin + BASE;
  const browser = await launch();
  t.after(async () => {
    await browser.close();
    server.closeAllConnections?.();
    await new Promise((ok) => server.close(ok));
  });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  await page.route((u) => u.href.startsWith(ENGINE), (route) => route.abort("connectionrefused"));

  const activeCaches = () => page.evaluate(() => caches.keys().then((k) => k.sort()));
  const waitForActive = async (why) => {
    const deadline = Date.now() + 20_000;
    for (;;) {
      const state = await page.evaluate(async () => {
        const reg = await navigator.serviceWorker.getRegistration();
        return reg?.active?.state === "activated";
      });
      if (state) return;
      assert.ok(Date.now() < deadline, `no worker became active within 20s (${why})`);
      await new Promise((ok) => setTimeout(ok, 100));
    }
  };

  // ---- v1 is installed and controlling ------------------------------------
  await page.goto(site, { waitUntil: "load" });
  await page.locator('textarea[aria-label="Message"]').waitFor({ timeout: 15_000 });
  await waitForActive("first load");
  await page.reload({ waitUntil: "load" });
  assert.ok(await page.evaluate(() => navigator.serviceWorker.controller !== null), "v1 must be controlling the page");
  assert.deepEqual(await activeCaches(), [v1Cache], "v1 holds exactly its own cache");

  // A cache left behind by a build older than this browser session. `activate`
  // is the only thing that will ever remove it.
  // ...and a cache owned by a DIFFERENT app on this same GitHub Pages origin
  // (all of an account's project sites share one *.github.io origin, and Cache
  // Storage is partitioned by origin, not by worker scope). `activate` must
  // leave this one alone -- deleting it would wipe a sibling site's offline data.
  const siblingCache = "some-other-app-cache";
  await page.evaluate(async (sibling) => {
    const old = await caches.open("praisonai-mobile-000000000000dead");
    await old.put("./stale.js", new Response("// from a build two deploys ago"));
    const other = await caches.open(sibling);
    await other.put("./other.js", new Response("// a different app's asset"));
  }, siblingCache);

  // ---- the site is redeployed: new HTML, same worker ----------------------
  // The worker's bytes are untouched, so NO new worker installs and nothing
  // re-precaches. The only thing that can put the new page in front of the
  // user is the navigation handler going to the network first.
  const marker = "redeployed-build-marker";
  overrides.set("index.html", v1Html.replace("</body>", `<div id="${marker}"></div></body>`));
  await page.reload({ waitUntil: "load" });
  await page.locator('textarea[aria-label="Message"]').waitFor({ timeout: 15_000 });
  assert.equal(
    await page.locator(`#${marker}`).count(),
    1,
    "a reload served the CACHED page, not the redeployed one: navigation must be network-first, " +
      "or every returning visitor stays on the old build",
  );

  // ---- and now a new worker ships ----------------------------------------
  const v2Cache = "praisonai-mobile-1111111111111111";
  overrides.set("sw.js", v1Sw.replace(v1Cache, v2Cache));
  await page.evaluate(async () => {
    const reg = await navigator.serviceWorker.getRegistration();
    await reg.update();
  });

  // `activate` deletes only THIS app's stale caches: the old praisonai-mobile
  // cache is gone, the current one remains, and the sibling app's cache is
  // untouched. The expected set is sorted -- "praisonai-mobile-1..." precedes
  // "some-other-app-cache".
  const expected = [v2Cache, siblingCache].sort();
  const settled = (k) => k.length === expected.length && k.every((v, i) => v === expected[i]);
  const deadline = Date.now() + 20_000;
  let keys = await activeCaches();
  while (!settled(keys) && Date.now() < deadline) {
    await new Promise((ok) => setTimeout(ok, 100));
    keys = await activeCaches();
  }
  assert.deepEqual(
    keys,
    expected,
    "after the new worker activated the old caches are still there: `activate` must delete every " +
      "praisonai-mobile cache but the current one, or a replaced build's bytes live on the user's disk forever",
  );
  assert.ok(
    keys.includes(siblingCache),
    "`activate` deleted a cache owned by a DIFFERENT app on the same origin: cleanup must be scoped " +
      "to the praisonai-mobile- prefix, or updating this app wipes a sibling GitHub Pages site's offline data",
  );

  // The new build is the one being served, from its own cache.
  await page.reload({ waitUntil: "load" });
  await page.locator('textarea[aria-label="Message"]').waitFor({ timeout: 15_000 });
  assert.ok(await page.evaluate(() => navigator.serviceWorker.controller !== null), "v2 controls the page");
});
