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
async function openApp(t, { seedChats = false } = {}) {
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
  /*
   * Stored conversations, for the cases that need the chats list to have rows
   * in it -- written through the SAME localStorage keys and JSON envelope
   * `core/src/chat/repository.ts` reads (`praisonai.chats.<id>`, and
   * `{schemaVersion, chat:{id,title,updated,engineId,messages}}`), so the rows
   * on screen are painted by `buildChatsScreen` from real stored chats rather
   * than pasted in as markup by the test.
   *
   * That distinction is not pedantry: the case that measures the type scale
   * walks whatever is on screen, and an empty chats list has no `.chat-title`
   * on it at all. Measured -- a mutation putting a hardcoded `15px` on
   * `.chat-title` SURVIVED the scale check until these rows existed, because
   * the element it broke was never rendered.
   */
  if (seedChats) {
    await context.addInitScript(() => {
      const put = (id, title, ago, messages) =>
        localStorage.setItem(`praisonai.chats.${id}`, JSON.stringify({
          schemaVersion: 1,
          chat: { id, title, updated: Date.now() - ago, engineId: "remote-http", messages },
        }));
      put("chat-1", "Three days in Lisbon", 4 * 60_000, [
        { role: "user", content: "Plan three days in Lisbon.", at: Date.now() - 5 * 60_000 },
        { role: "assistant", content: "Day 1: Alfama.", at: Date.now() - 4 * 60_000 },
      ]);
      put("chat-2", "Why is the parser dropping the last frame of a stream?", 3 * 3600_000, [
        { role: "user", content: "Why is the parser dropping the last frame?", at: Date.now() - 3 * 3600_000 },
      ]);
      put("chat-3", "Untitled", 30 * 3600_000, []);
    });
  }
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

/*
 * ---- The visual identity, measured rather than declared --------------------
 *
 * Everything below asserts COMPUTED style in the same real engine the geometry
 * cases above use, and for the same reason: app/src/css.test.ts reads the
 * stylesheet as text, so it can check that a declaration is written and cannot
 * check what the declaration DOES. A contrast ratio, a resolved type step and
 * the relative brightness of two surfaces are all facts about the rendered
 * page, and none of them survives being spelled out as a string match.
 *
 * The rows are built here with the class names and data attributes
 * `app/src/dom.ts` emits, exactly as the chat-row case above builds a
 * `.row-chat`. `app/src/main.test.ts` and `app/src/dom.test.ts` hold the other
 * half of every one of those pairs -- that the builder still emits these names
 * -- so a rename fails on that side rather than passing vacuously on this one.
 */

/** One of each row kind, as the app writes them. Built in the page. */
const TRANSCRIPT_FIXTURE = `
  <div class="row row-user" data-speaker="user" data-state="unstored">
    <span class="sr-only">You said:</span><span class="user-text">Plan three days in Lisbon.</span>
    <span class="user-note">Not saved</span></div>
  <div class="row row-text">Day 1: Alfama and the viewpoints. Day 2: Belem. Day 3: Sintra.</div>
  <div class="row row-reasoning">The user wants an itinerary, so I will keep each day short.</div>
  <div class="row row-tool" data-status="running"><span class="tool-status">Running</span>
    <span class="tool-name">search</span><span class="tool-meta">0.4s</span></div>
  <div class="row row-tool" data-status="ok"><span class="tool-status">Succeeded</span>
    <span class="tool-name">read_file</span><span class="tool-meta">0.3s</span>
    <pre class="tool-output">hello</pre></div>
  <div class="row row-tool" data-status="failed"><span class="tool-status">Failed</span>
    <span class="tool-name">rm</span><span class="tool-meta">0.1s</span></div>
  <div class="row row-tool" data-status="unresolved"><span class="tool-status">No result</span>
    <span class="tool-name">slow_tool</span><span class="tool-meta">&mdash;</span></div>
  <div class="row row-approval" data-state="pending"><p>Allow search?</p>
    <button type="button" data-choice="allow">Allow</button>
    <button type="button" data-choice="deny">Deny</button></div>
  <div class="row row-error" data-tone="failure" data-recovery="retry">The engine is rate limited.</div>
  <div class="row row-notice" data-tone="warning">Stopped</div>
  <div class="row row-notice" data-tone="neutral">Reconnected</div>
  <div class="row row-dropped">2 events were dropped</div>
`;

/**
 * WCAG 2.x relative luminance and contrast, defined in the page so the numbers
 * come from the colours the ENGINE resolved -- `var()` chains, the dark-scheme
 * block, `currentColor` and all -- rather than from hexes copied out of the
 * stylesheet into the test, which is the mistake that makes a colour gate
 * agree with itself forever.
 */
const COLOUR_HELPERS = `
  function parse(c) {
    const m = c.match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const p = m[1].split(",").map((n) => parseFloat(n));
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  }
  function over(fg, bg) {
    // Source-over compositing, so an element with opacity or an rgba colour is
    // judged on what is actually on the glass.
    const a = fg.a;
    return { r: fg.r * a + bg.r * (1 - a), g: fg.g * a + bg.g * (1 - a), b: fg.b * a + bg.b * (1 - a), a: 1 };
  }
  function lum(c) {
    const f = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  }
  function ratio(a, b) {
    const x = lum(a), y = lum(b);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
  }
  /** The colour actually behind an element: the first ancestor that paints one,
   *  composited down through every translucent layer above it. */
  function backdrop(el) {
    const stack = [];
    for (let n = el; n; n = n.parentElement) {
      const s = getComputedStyle(n);
      const c = parse(s.backgroundColor);
      if (c && c.a > 0) stack.push({ c, o: parseFloat(s.opacity) });
      if (c && c.a === 1 && parseFloat(s.opacity) === 1) break;
    }
    let out = { r: 255, g: 255, b: 255, a: 1 };
    for (let i = stack.length - 1; i >= 0; i -= 1) {
      const l = stack[i];
      out = over({ ...l.c, a: l.c.a * l.o }, out);
    }
    return out;
  }
  /** The effective opacity of an element, including every ancestor's. */
  function chainOpacity(el) {
    let o = 1;
    for (let n = el; n; n = n.parentElement) o *= parseFloat(getComputedStyle(n).opacity);
    return o;
  }
`;

/** Open the app, put a full transcript in it, and set the colour scheme. */
async function openTranscript(t, scheme, options = {}) {
  const page = await openApp(t, options);
  await page.emulateMedia({ colorScheme: scheme });
  await page.evaluate((html) => {
    const transcript = document.querySelector("main.transcript");
    // The welcome panel is up on a fresh chat and the stylesheet takes the
    // transcript's stretch away while it is; these rows are the "has rows"
    // case, so put the screen into it the way main.ts does.
    const screen = document.querySelector('.screen[data-screen="chat"]');
    delete screen.dataset.empty;
    document.querySelector(".empty-state").hidden = true;
    transcript.innerHTML = html;
  }, TRANSCRIPT_FIXTURE);
  return page;
}

/** Every text-bearing element under #root that is actually on screen, with the
 *  contrast of its composited colour against its composited backdrop. */
const CONTRAST_SWEEP = `(() => {
  ${COLOUR_HELPERS}
  const out = [];
  for (const el of document.querySelectorAll("#root *")) {
    // Only elements with their OWN text: a wrapper's colour is never read.
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim() !== "");
    if (!own) continue;
    if (el.closest(".sr-only")) continue;                     // never painted
    if (el.disabled || el.closest("[disabled]")) continue;    // WCAG exempts disabled controls
    if (el.closest("[hidden]") || el.hidden) continue;        // not on screen
    if (el.getBoundingClientRect().width === 0) continue;
    const s = getComputedStyle(el);
    const fg = parse(s.color);
    if (!fg) continue;
    const bg = backdrop(el);
    const composited = over({ ...fg, a: fg.a * chainOpacity(el) }, bg);
    const r = ratio(composited, bg);
    const px = parseFloat(s.fontSize);
    const bold = parseInt(s.fontWeight, 10) >= 700;
    // WCAG's large-text threshold: 24px, or 18.66px when bold.
    const need = px >= 24 || (bold && px >= 18.66) ? 3 : 4.5;
    if (r < need) {
      out.push({ what: el.className || el.tagName, text: el.textContent.trim().slice(0, 30),
                 ratio: Math.round(r * 100) / 100, need });
    }
  }
  return out;
})()`;

for (const scheme of ["light", "dark"]) {
  test(`every word on every screen clears WCAG AA in ${scheme} mode`, async (t) => {
    /*
     * All THREE screens, not just the transcript.
     *
     * This swept `.transcript *, .topbar *, .composer *` and passed while a
     * mutation dimming `.chat-updated` to #a8b0ba -- a timestamp on the chats
     * list at 2.9:1 -- survived, because the element was on a screen the sweep
     * never visited. A contrast gate that checks one screen out of three is a
     * gate that reports on the screen you happened to be looking at.
     *
     * Each screen is measured while it is the VISIBLE one: `mount.ts` sets
     * `hidden` on the others, and a hidden element has no useful computed
     * style to read.
     */
    const findings = [];
    let swept = 0;

    // A FRESH page per route, rather than one page walked through all three.
    // Only the chat screen builds a `.topbar`, and the topbar is where the
    // navigation buttons live -- so from Settings there is nothing to click to
    // reach Chats, and a loop that tried timed out on a button `mount.ts` had
    // correctly hidden. Going back is the OS gesture, which is not a control
    // on the page at all.
    for (const route of ["chat", "settings", "chats"]) {
      const page = await openTranscript(t, scheme, { seedChats: true });
      if (route !== "chat") {
        await page.locator(`button[data-action="navigate"][data-route="${route}"]`).click();
        await page.locator(`.screen-${route}`).waitFor({ timeout: 10_000 });
      }
      for (const f of await page.evaluate(CONTRAST_SWEEP)) findings.push({ ...f, route });
      // The sample cannot shrink to nothing and still pass: a sweep that found
      // no text would report no failures either.
      const counted = await page.evaluate(`
        [...document.querySelectorAll("#root *")].filter((el) =>
          !el.hidden && !el.closest("[hidden]") && el.getBoundingClientRect().width > 0 &&
          [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim() !== "")
        ).length`);
      assert.ok(counted > 3, `only ${counted} text elements were visible on ${route}: nothing was swept`);
      swept += counted;
    }
    assert.ok(swept > 20, `only ${swept} text elements across all three screens`);

    assert.deepEqual(
      findings,
      [],
      `${scheme} mode has text below its WCAG AA threshold:\n` +
        findings.map((f) => `  ${f.ratio}:1 (needs ${f.need}) on ${f.route}: ${f.what} -- "${f.text}"`).join("\n"),
    );
  });
}

for (const [scheme, direction] of [["light", "recedes"], ["dark", "advances"]]) {
  test(`the ${scheme} theme is designed, not inverted: the user's bubble ${direction} by the right amount`, async (t) => {
    // The specific defect that inverting one palette into the other produces
    // here, as a number.
    //
    // `--accent` in dark has to be light enough to read as TEXT on a near-black
    // ground -- it is 10.6:1 -- so a bubble FILLED with it, which is what one
    // shared token gives you, is a beacon: the brightest thing on the screen,
    // once per user message, all the way down a conversation. In light the
    // identical rule is the opposite experience, because there the same fill is
    // DARKER than the page and recedes.
    //
    // So the invariant is not "which surface is brightest" -- in dark the
    // bubble is legitimately the brightest, it is the only raised surface in
    // the transcript. It is the DIRECTION and the MAGNITUDE of the step:
    // away from the page in each theme's own sense, far enough to be plainly a
    // surface and no further. 10.56 fails the ceiling; 1.0 fails the floor.
    const page = await openTranscript(t, scheme);

    const measured = await page.evaluate(`(() => {
      ${COLOUR_HELPERS}
      const bubble = backdrop(document.querySelector(".row-user"));
      const ground = backdrop(document.querySelector(".transcript"));
      return { bubble: lum(bubble), ground: lum(ground), separation: ratio(bubble, ground) };
    })()`);

    if (scheme === "light") {
      assert.ok(
        measured.bubble < measured.ground,
        "in light the bubble is a dark fill on a pale page: it must recede, not glow",
      );
    } else {
      assert.ok(
        measured.bubble > measured.ground,
        "in dark the bubble is the one raised surface in the transcript",
      );
    }
    assert.ok(
      measured.separation > 1.5,
      `the ${scheme} bubble is only ${measured.separation.toFixed(2)}:1 against the transcript: ` +
        "it reads as no bubble at all",
    );
    // The ceiling is what inverting the palette breaks. A dark bubble filled
    // with `--accent` measures 10.56:1 here.
    assert.ok(
      measured.separation < 6,
      `the ${scheme} bubble is ${measured.separation.toFixed(2)}:1 against the transcript -- a beacon, ` +
        "repeated once per message down the whole conversation",
    );
  });
}

test("the two speakers are told apart by shape and side, not only by colour", async (t) => {
  // The transcript layer is written against exactly this: a conversation whose
  // sides differ only in hue is one a colour-blind reader cannot follow and a
  // screen-reader user never hears. So the user's row is pulled to the end of
  // the flex column and filled, and the assistant's is left as prose on the
  // page -- and the assistant's row must NOT have picked up a fill of its own,
  // which is what made both sides slabs before.
  const page = await openTranscript(t, "light");

  const shape = await page.evaluate(`(() => {
    ${COLOUR_HELPERS}
    const user = document.querySelector(".row-user");
    const text = document.querySelector(".row-text");
    const transcript = document.querySelector(".transcript");
    const us = getComputedStyle(user), ts = getComputedStyle(text);
    return {
      userAlign: us.alignSelf,
      userFilled: ratio(backdrop(user), backdrop(transcript)),
      assistantOwnBackground: parse(ts.backgroundColor).a,
      userRight: user.getBoundingClientRect().right,
      assistantRight: text.getBoundingClientRect().right,
      userLeft: user.getBoundingClientRect().left,
      assistantLeft: text.getBoundingClientRect().left,
      userCorners: [us.borderTopLeftRadius, us.borderTopRightRadius,
                    us.borderBottomRightRadius, us.borderBottomLeftRadius],
    };
  })()`);

  assert.equal(shape.userAlign, "flex-end", "the user's row must hug the trailing edge");
  assert.ok(
    shape.userLeft > shape.assistantLeft + 8,
    `the user's row starts at ${shape.userLeft} and the assistant's at ${shape.assistantLeft}: ` +
      "the indent is what says whose turn it is",
  );
  assert.equal(
    shape.assistantOwnBackground,
    0,
    "the assistant's answer is prose on the page; a fill turns a long answer into a slab",
  );
  assert.ok(
    shape.userFilled > 3,
    `the user's bubble is only ${shape.userFilled.toFixed(2)}:1 against the transcript`,
  );
  // One corner cut, and exactly one: the notch that points the bubble back at
  // the person who wrote it. Three round and one small is the whole shape.
  const distinct = new Set(shape.userCorners);
  assert.equal(
    distinct.size,
    2,
    `the user bubble's corners are ${JSON.stringify(shape.userCorners)}: one notch, not four or none`,
  );
});

test("every size and weight in the app is a step on the type scale", async (t) => {
  /*
   * A scale nothing is held to is a comment. This walks the real DOM of all
   * three screens and asserts each rendered font-size is a step -- so the next
   * `font-size: .82rem` written by hand fails here rather than quietly making
   * the scale seven steps, then nine.
   *
   * A FRESH page per route, for a reason that cost a mutation: this first
   * clicked Settings and then Chats on one page and swept afterwards, and
   * `ui/src/screens.ts` UNMOUNTS the screen you leave -- so the settings
   * markup was not in the document at all when the sweep ran. A mutation
   * putting `.72rem` on the settings eyebrow survived it. Each route is now
   * measured while it is the one on screen, exactly as the contrast sweep is.
   */
  const sizes = new Map();
  const weights = new Map();
  let allowed = null;
  let root = null;

  for (const route of ["chat", "settings", "chats"]) {
    const page = await openTranscript(t, "light", { seedChats: true });
    if (route !== "chat") {
      await page.locator(`button[data-action="navigate"][data-route="${route}"]`).click();
      await page.locator(`.screen-${route}`).waitFor({ timeout: 10_000 });
    }

    const measured = await page.evaluate(() => {
      const rootPx = parseFloat(getComputedStyle(document.documentElement).fontSize);
      const steps = ["--text-xs", "--text-sm", "--text-md", "--text-base", "--text-lg", "--text-xl"];
      const css = getComputedStyle(document.documentElement);
      const seen = [];
      for (const el of document.querySelectorAll("#root *")) {
        const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim() !== "");
        if (!own || el.closest(".sr-only")) continue;
        if (el.hidden || el.closest("[hidden]") || el.getBoundingClientRect().width === 0) continue;
        const style = getComputedStyle(el);
        seen.push([
          Math.round(parseFloat(style.fontSize) * 100) / 100,
          el.className || el.tagName,
          parseInt(style.fontWeight, 10),
        ]);
      }
      return {
        rootPx,
        allowed: steps.map((s) => Math.round(parseFloat(css.getPropertyValue(s)) * rootPx * 100) / 100),
        seen,
      };
    });

    root ??= measured.rootPx;
    allowed ??= measured.allowed;
    assert.ok(measured.seen.length >= 3, `only ${measured.seen.length} sized elements on ${route}`);
    for (const [px, what, weight] of measured.seen) {
      if (!sizes.has(px)) sizes.set(px, `${what} (${route})`);
      if (!weights.has(weight)) weights.set(weight, `${what} (${route})`);
    }
  }

  // 0.02px, not half a pixel. The tolerance exists only for the rounding in
  // `px = round(rem * root * 100) / 100`, and every step lands on a whole pixel
  // at a 16px root. A half-pixel window is wide enough to accept `.82rem`
  // (13.12px) as `--text-sm` (13px) -- which is exactly the hand-written size
  // this scale replaced, so the gate would have passed over its own reason for
  // existing. Verified by mutation: at 0.51 that substitution survives, at 0.02
  // it fails.
  const offScale = [...sizes.entries()].filter(
    ([px]) => !allowed.some((a) => Math.abs(a - px) < 0.02),
  );
  assert.deepEqual(
    offScale,
    [],
    `sizes that are not a step on the scale (allowed: ${allowed?.join(", ")}px at a ${root}px root):\n` +
      offScale.map(([px, what]) => `  ${px}px on ${what}`).join("\n"),
  );
  // The sample cannot shrink to nothing and still pass.
  assert.ok(sizes.size >= 5, `only ${sizes.size} distinct sizes found across three screens`);

  /*
   * And the WEIGHTS, which is the half of the type decision a size check
   * cannot see.
   *
   * This file used `font-weight: 550` for settings labels. CSS font matching
   * for a requested weight above 500 searches UPWARD first, and Roboto ships
   * 400/500/700 as separate faces -- so 550 rendered as 550 on iOS, where SF
   * is variable, and as 700, full bold, on Android. A label meant to read a
   * shade heavier than its value was bolder than the screen heading above it,
   * on one platform only, and no screenshot of the other would ever show it.
   *
   * Three values, named on :root, and nothing else. 400/500/700 are the three
   * Android actually has, so a rule that asks for one of them gets the same
   * answer on both platforms.
   */
  const namedWeights = await (async () => {
    const page = await openTranscript(t, "light");
    return page.evaluate(() => {
      const css = getComputedStyle(document.documentElement);
      return ["--weight-normal", "--weight-medium", "--weight-strong"]
        .map((n) => parseInt(css.getPropertyValue(n).trim(), 10));
    });
  })();
  assert.deepEqual(namedWeights, [400, 500, 700], "the three weights Android has, named on :root");

  const offWeight = [...weights.entries()].filter(([w]) => !namedWeights.includes(w));
  assert.deepEqual(
    offWeight,
    [],
    `weights that are not one of ${namedWeights.join("/")} -- a weight between two faces ` +
      `resolves differently on Android and iOS:\n` +
      offWeight.map(([w, what]) => `  ${w} on ${what}`).join("\n"),
  );
  assert.ok(weights.size >= 2, `only ${weights.size} distinct weights: the hierarchy is not being used`);
});
