/**
 * What the non-chat screens actually LOOK like, measured in a real engine.
 *
 * app/src/css.test.ts reads `app.css` as text. That catches a declaration that
 * is written wrong; it cannot catch a declaration that is not written at all,
 * and it cannot catch a rule whose selector matches nothing the app emits.
 * Both of those shipped:
 *
 *   - `.topbar` is the only rule in the stylesheet that consumes
 *     `--safe-area-inset-top`, and only the chat screen builds a `.topbar`.
 *     `buildSettingsScreen` / `buildChatsScreen` emit a bare
 *     `<section class="screen screen-settings">`, so on an Android 15 emulator
 *     the "Settings" heading's box started at y = 20 with a 49px inset -- 29px
 *     of the title painted under the status-bar clock -- and every heading sat
 *     at x = 0, which in landscape is inside the display cutout.
 *   - those screens are `overflow: visible`, so a settings list taller than the
 *     viewport had rows that could not be scrolled to at all.
 *   - the chat-row block was written as `.chat-row`; main.ts emits `row-chat`.
 *     The rule has therefore never painted, and rows fell back to the bare
 *     `button` styling -- a centred, auto-width pill instead of a list row.
 *
 * So this file asserts COMPUTED GEOMETRY, never declaration text. A device with
 * insets is simulated by overriding the four `--safe-area-inset-*` custom
 * properties, which is the documented bridge between `env()` and the app
 * (core/src/ports/shell.ts INSET_VARIABLES): everything downstream of that
 * variable is the code under test.
 */
import test, { after } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, readFile, readdir, symlink } from "node:fs/promises";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, extname, join, normalize, resolve } from "node:path";
import { chromium } from "playwright";

const pkg = resolve(dirname(new URL(import.meta.url).pathname), "..");
const ENGINE = "http://127.0.0.1:8765";

/**
 * Build into a PRIVATE dist, not the package's own.
 *
 * `tools/build-webview.mjs` starts with `rm -rf <root>/dist`, and it takes the
 * root as its one argument. Two test files that both build and then serve
 * `<pkg>/dist` therefore race: measured under a full `npm run check`, this
 * file's server handed out a half-written `app.js` while `web-boot.test.mjs`
 * was rebuilding, the app never booted, and the first case here sat on the
 * boot wait for a full minute. A root of symlinks costs nothing and makes the
 * two builds independent.
 */
async function buildPrivately() {
  const root = await mkdtemp(join(tmpdir(), "praisonai-layout-"));
  for (const entry of await readdir(pkg)) {
    if (entry === "dist") continue;
    await symlink(join(pkg, entry), join(root, entry));
  }
  const built = spawnSync(process.execPath, [join(pkg, "tools/build-webview.mjs"), root], {
    encoding: "utf8",
  });
  assert.equal(built.status, 0, `the build must succeed first:\n${built.stdout}${built.stderr}`);
  return join(root, "dist");
}

/** Deep enough to be unmistakable and different on every edge, so a fix that
 *  wires one inset into all four sides fails here rather than passing. */
const INSETS = { top: 44, right: 21, bottom: 34, left: 13 };

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".webmanifest": "application/manifest+json",
  ".png": "image/png",
};

function serveDist(dist) {
  const server = createServer(async (req, res) => {
    let rel = new URL(req.url, "http://x").pathname.slice(1);
    if (rel === "" || rel.endsWith("/")) rel += "index.html";
    const file = normalize(join(dist, rel));
    if (!file.startsWith(dist) || !existsSync(file)) {
      res.writeHead(404).end("not found");
      return;
    }
    res.writeHead(200, {
      "content-type": MIME[extname(file)] ?? "application/octet-stream",
      "cache-control": "no-store",
    });
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
        "no browser to measure the layout in: run `npx playwright install chromium` (or install Google Chrome).\n" +
          `  bundled: ${bundled.message.split("\n")[0]}\n  system: ${system.message.split("\n")[0]}`,
      );
    }
  }
}

/**
 * Build, serve and launch ONCE for the whole file.
 *
 * Doing it per case built dist/ five times and started five Chromiums, and
 * under the parallelism of a full `npm run check` that was slow enough to trip
 * the boot wait -- a flake that says nothing about the layout.
 */
let shared = null;
async function shell() {
  if (shared !== null) return shared;
  const server = await serveDist(await buildPrivately());
  const browser = await launch();
  shared = { server, browser };
  return shared;
}

after(async () => {
  if (shared === null) return;
  await shared.browser.close();
  shared.server.closeAllConnections?.();
  await new Promise((ok) => shared.server.close(ok));
});

/** The built app on a phone-sized viewport, with the four inset variables
 *  standing in for a notched device. Each case gets its OWN context, so one
 *  case's injected stylesheet and appended nodes cannot reach the next. */
async function openApp(t) {
  const { server, browser } = await shell();

  // `serviceWorkers: "block"` because this file is about layout and the service
  // worker is a second, stateful source of the page's bytes: a context that
  // keeps one alive serves the NEXT page from its cache, and a precache that
  // has not finished leaves that page waiting on a fetch nothing will answer.
  // Under the parallelism of a full `npm run check` that showed up as one case
  // in five hanging on the boot wait for a full minute -- a flake that says
  // nothing about any inset. tools/web-boot.test.mjs is where the worker is
  // the subject and is tested properly.
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    serviceWorkers: "block",
  });
  t.after(() => context.close());
  const page = await context.newPage();
  await page.route((u) => u.href.startsWith(ENGINE), (route) => route.abort("connectionrefused"));
  await page.goto(`http://127.0.0.1:${server.address().port}/`, { waitUntil: "load" });
  await page.locator('textarea[aria-label="Message"]').waitFor({ timeout: 60_000 });
  // AFTER load, so this beats app.css's `:root` block on order rather than
  // relying on specificity.
  await page.addStyleTag({
    content:
      `:root{--safe-area-inset-top:${INSETS.top}px;--safe-area-inset-right:${INSETS.right}px;` +
      `--safe-area-inset-bottom:${INSETS.bottom}px;--safe-area-inset-left:${INSETS.left}px}`,
  });
  // Then a `resize`, which is what a browser fires on a rotation and what makes
  // the shell re-read those variables and republish. Going through the shell
  // rather than styling `#root` directly is the point: main.ts writes the
  // EFFECTIVE `--inset-*` onto `#root` from `shell.insets`, so a test that set
  // them itself would be asserting against its own value and would pass with
  // the shell unplugged.
  await page.evaluate(() => window.dispatchEvent(new Event("resize")));
  await page.waitForFunction(
    (top) => document.getElementById("root").style.getPropertyValue("--inset-top") === `${top}px`,
    INSETS.top,
    { timeout: 10_000 },
  );
  return page;
}

/** Navigate by tapping the affordance a user taps, so the test cannot pass
 *  against a screen the app has no route to. */
async function go(page, route) {
  await page.locator(`button[data-action="navigate"][data-route="${route}"]`).click();
  const screen = page.locator(`.screen-${route}`);
  await screen.waitFor({ timeout: 10_000 });
  return screen;
}

for (const route of ["settings", "chats"]) {
  test(`the ${route} screen clears the safe area on every edge`, async (t) => {
    const page = await openApp(t);
    await go(page, route);

    const box = await page.evaluate((r) => {
      const screen = document.querySelector(`.screen-${r}`);
      const heading = screen.querySelector(".screen-heading");
      const h = heading.getBoundingClientRect();
      return {
        headingTop: h.top,
        headingLeft: h.left,
        headingRight: h.right,
        viewportWidth: window.innerWidth,
        // The screen fills the window, so its own padding is what has to hold
        // the content off the edges.
        screenBottom: screen.getBoundingClientRect().bottom,
        padBottom: parseFloat(getComputedStyle(screen).paddingBottom),
      };
    }, route);

    // The reported defect, as a number: the heading's own box must start below
    // the status bar, not 29px inside it.
    assert.ok(
      box.headingTop >= INSETS.top,
      `the ${route} heading starts at y=${box.headingTop}, inside the ${INSETS.top}px top inset`,
    );
    assert.ok(
      box.headingLeft >= INSETS.left,
      `the ${route} heading starts at x=${box.headingLeft}, inside the ${INSETS.left}px left inset`,
    );
    assert.ok(
      box.headingRight <= box.viewportWidth - INSETS.right,
      `the ${route} heading reaches x=${box.headingRight}, inside the ${INSETS.right}px right inset`,
    );
    assert.ok(
      box.padBottom >= INSETS.bottom,
      `the ${route} screen keeps ${box.padBottom}px below its last row, under a ${INSETS.bottom}px home indicator`,
    );
  });

  test(`the ${route} screen can be scrolled when its content overflows`, async (t) => {
    const page = await openApp(t);
    await go(page, route);

    const scrolled = await page.evaluate((r) => {
      const screen = document.querySelector(`.screen-${r}`);
      // Content taller than any phone, so the question is only whether the
      // screen scrolls -- not how many settings happen to be registered today.
      const filler = document.createElement("div");
      filler.style.height = "3000px";
      filler.style.flex = "none";
      screen.append(filler);
      const before = { scrollHeight: screen.scrollHeight, clientHeight: screen.clientHeight };
      screen.scrollTop = 500;
      return { ...before, scrollTop: screen.scrollTop };
    }, route);

    assert.ok(
      scrolled.scrollHeight > scrolled.clientHeight,
      `the ${route} screen did not even overflow, so this test proves nothing`,
    );
    assert.ok(
      scrolled.scrollTop > 0,
      `the ${route} screen will not scroll (scrollTop stayed ${scrolled.scrollTop}), ` +
        "so every row past the fold is unreachable",
    );
  });
}

test("a chat row is a full-width list row, and a long title is truncated", async (t) => {
  const page = await openApp(t);
  const screen = await go(page, "chats");
  await screen.waitFor();

  // The class list `buildChatsScreen` builds, verbatim. app/src/main.test.ts
  // holds the other half of this pair: that the builder emits these names.
  const measured = await page.evaluate(() => {
    const screen = document.querySelector(".screen-chats");
    const row = document.createElement("button");
    row.type = "button";
    row.className = "row row-chat row-chat-chat";
    row.textContent = "A chat whose title came from a very long first message ".repeat(6);
    screen.append(row);
    const style = getComputedStyle(row);
    const rect = row.getBoundingClientRect();
    const content = screen.clientWidth
      - parseFloat(getComputedStyle(screen).paddingLeft)
      - parseFloat(getComputedStyle(screen).paddingRight);
    return {
      display: style.display,
      textAlign: style.textAlign,
      whiteSpace: style.whiteSpace,
      textOverflow: style.textOverflow,
      width: rect.width,
      height: rect.height,
      content,
    };
  });

  assert.equal(measured.display, "flex", "a chat row is a list row, not an inline-block button");
  assert.equal(measured.textAlign, "left", "a chat row's title reads from the leading edge");
  assert.equal(measured.whiteSpace, "nowrap", "a long chat title must not wrap to many lines");
  assert.equal(measured.textOverflow, "ellipsis", "a long chat title is ellipsised");
  assert.ok(
    Math.abs(measured.width - measured.content) < 1,
    `a chat row is ${measured.width}px wide inside a ${measured.content}px column: it must fill it`,
  );
  // The truncation, as geometry rather than as a declaration: six repeats of
  // that sentence cannot fit on one line of a 390px phone unless it is clipped.
  assert.ok(
    measured.height < 100,
    `a long chat title grew the row to ${measured.height}px instead of staying one line`,
  );
});
