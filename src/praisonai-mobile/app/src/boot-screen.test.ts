/**
 * The boot indicator: the thing on screen while there is no app yet.
 *
 * Before this existed a cold start was blank -- no wordmark, no text, nothing
 * -- from the moment the launcher icon was tapped until app.js had been
 * fetched, parsed and run. Measured on an Android 15 emulator (software GPU,
 * `am force-stop` then `am start`, timed from the WebView's own
 * `first-contentful-paint`): 1.36 s of white in light mode, 1.42 s of black in
 * dark. On slower silicon, a first launch after install, or a cold page cache
 * it is longer, and there is nothing in any of it to tell a user that the app
 * is starting rather than broken.
 *
 * Everything asserted here is about a frame that is painted BEFORE any module
 * has executed, which is why every one of these tests reads the shipped file
 * off disk rather than driving code. `app/index.html`, `app/app.css` and
 * `app/boot-guard.js` are copied verbatim into dist/ by
 * tools/build-webview.mjs; they are not typechecked, not bundled, and until
 * now not covered -- the same gap `css.test.ts` was written to close for the
 * stylesheet.
 *
 * The one thing NOT asserted here is removal, because removal is behaviour:
 * `main.test.ts` mounts the real composition root over a root that already
 * holds a boot indicator and proves the first render takes it away.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { runInNewContext } from "node:vm";

const html = readFileSync(join(import.meta.dirname, "../index.html"), "utf8");
const guardSource = readFileSync(join(import.meta.dirname, "../boot-guard.js"), "utf8");
/** Comments explain the rules and name the very tokens a rule must contain, so
 *  they are stripped before matching -- exactly as css.test.ts does. */
const css = readFileSync(join(import.meta.dirname, "../app.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const markup = html.replace(/<!--[\s\S]*?-->/g, "");

/** What is inside `<div id="root">`, as written in the page. */
function rootContent(): string {
  const open = /<div id="root"\s*>/.exec(markup);
  assert.ok(open !== null, "app/index.html must still have a #root container");
  const rest = markup.slice(open.index + open[0].length);
  const end = rest.indexOf("</div>\n    <noscript");
  assert.ok(end !== -1, "the #root container must close before <noscript>");
  return rest.slice(0, end);
}

test("the page paints a boot indicator, before any script has run", () => {
  // The defect in one line: #root shipped empty, so the first frame was the
  // body's background colour and nothing else. The fix has to be IN THE
  // MARKUP -- an indicator drawn by app.js appears at the same moment the app
  // does and covers nothing at all.
  const inside = rootContent();
  assert.match(inside, /data-boot\b/, "#root must hold the boot indicator on first paint");

  // And it must precede every <script>. The CSP is `script-src 'self'` with no
  // inline scripts, so this element cannot be created by the page; it is only
  // ever markup the parser meets before it meets the bundle.
  const boot = markup.indexOf("data-boot");
  const script = markup.indexOf("<script");
  assert.ok(script !== -1, "the page must still load a script, or this proves nothing");
  assert.ok(boot < script, "the boot indicator must be parsed before any script element");
});

test("the boot indicator says which app is starting, and that it is starting", () => {
  // A bare spinner or an empty box answers neither question a user has at this
  // moment: did I open the right thing, and is it doing anything. Both answers
  // are words, because words are what a system font can paint with no second
  // request.
  const inside = rootContent();
  assert.match(inside, /PraisonAI/, "the wordmark names the app");
  const note = /class="boot-note"[^>]*>([^<]+)</.exec(inside)?.[1]?.trim() ?? "";
  assert.ok(note.length > 0, "the indicator must say something, not just show a mark");
  assert.match(note, /start/i, `the note must say the app is starting, not "${note}"`);
});

test("the boot indicator is styled by the render-blocking stylesheet, not by script", () => {
  // app.css is a <link> in <head>, so it is parsed before the first frame;
  // app.js is a deferred module and is not. Styling the indicator from script
  // would make it appear at the same moment the app does, i.e. never usefully.
  const head = html.slice(0, html.indexOf("</head>"));
  assert.match(head, /<link rel="stylesheet" href="\.\/app\.css"/, "app.css must be linked in <head>");

  // Every class the boot markup uses must have a rule here, so a renamed class
  // cannot leave the indicator unstyled and silent about it.
  const classes = [...rootContent().matchAll(/class="([^"]+)"/g)].flatMap((m) => (m[1] ?? "").split(/\s+/));
  assert.ok(classes.includes("boot"), "the container carries the .boot class");
  for (const name of new Set(classes)) {
    assert.ok(css.includes(`.${name}`), `app.css has no rule for .${name}`);
  }
});

/**
 * Every `.boot*` rule in the stylesheet, selector and declarations.
 *
 * Parsed as ALL rules and then filtered, rather than matched with a pattern
 * anchored on `}`. The first version of this did the latter, and a global
 * regex consumes the brace it anchors on -- so it saw `.boot` and `.boot-note`
 * and skipped `.boot-mark` entirely, between them. A hardcoded `#14171c` on the
 * wordmark went straight through the assertions below while the test read as
 * green. The `expect` list at the bottom is the second half of the fix: a rule
 * that stops being seen has to fail rather than shrink the sample.
 */
function bootRules(): string {
  const rules = [...css.matchAll(/([^{}]+)\{([^{}]*)}/g)]
    .map((m) => ({ selector: (m[1] ?? "").trim(), body: m[2] ?? "" }))
    .filter((r) => /(^|[\s,])\.boot[\w-]*/.test(r.selector));
  const seen = rules.map((r) => r.selector).join(" ");
  for (const expect of [".boot", ".boot-mark", ".boot-note", ".boot-failed"]) {
    assert.match(seen, new RegExp(`\\${expect}[^\\w-]`), `no ${expect} rule was read out of app.css`);
  }
  return rules.map((r) => `${r.selector}{${r.body}}`).join("\n");
}

test("the boot indicator takes its colours from the theme tokens, so a dark device gets a dark boot screen", () => {
  // A white boot screen handing over to a dark app on every launch would be
  // worse than the blank page this replaces -- a flash that reads as a
  // rendering fault. Nothing here can name a colour: :root defines the tokens
  // and the `prefers-color-scheme: dark` block redefines them, so using the
  // tokens is the whole of the dark-mode support.
  const rules = bootRules();
  const literals = [...rules.matchAll(/(#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\b(?:white|black|silver|gray|grey)\b)/g)];
  assert.deepEqual(
    literals.map((m) => m[0]),
    [],
    `the boot indicator must not name a colour; use the :root tokens:\n${rules}`,
  );
  for (const decl of rules.matchAll(/(?:^|[;{])\s*(?:color|background(?:-color)?)\s*:([^;}]*)/g)) {
    assert.match(decl[1] ?? "", /var\(--/, `a boot colour must come from a token: ${decl[0]}`);
  }

  // And the tokens it uses must actually be the ones the dark theme moves. A
  // token that only ever has one value would pass the check above while
  // painting the same colour in both themes.
  const dark = /@media \(prefers-color-scheme: dark\)\s*\{([\s\S]*?)\n\}/.exec(css)?.[1] ?? "";
  for (const token of [...rules.matchAll(/var\((--[\w-]+)/g)].map((m) => m[1] ?? "")) {
    if (token.startsWith("--inset") || token.startsWith("--safe-area")) continue;
    assert.match(dark, new RegExp(`${token}\\s*:`), `${token} is not redefined for dark mode`);
  }
});

test("the boot indicator clears the safe-area insets", () => {
  // The header clearing the status bar was a measured fix (app.css's own note:
  // 29px of the "Settings" heading painted under the clock). The boot screen is
  // painted before ANY of that machinery runs, so it lays out against the
  // `env()` fallback the stylesheet declares -- and it has to consume it, or a
  // short landscape viewport puts these lines inside a cutout.
  const padding = /\.boot\s*\{([^}]*)}/.exec(css)?.[1] ?? "";
  for (const side of ["top", "right", "bottom", "left"]) {
    assert.match(padding, new RegExp(`--inset-${side}`), `.boot must respect the ${side} inset`);
  }
});

// ---- the failure path -------------------------------------------------------
//
// The shipped bytes, run. `boot-guard.js` is a plain classic script outside the
// bundle, so there is nothing to import -- but there is also no reason to
// assert its SOURCE when the file is small enough to execute against a fake
// window and be asked what it does.

interface FakeNode {
  hidden: boolean;
  querySelector(selector: string): FakeNode | null;
}

/** A page in one of two states: still showing the boot indicator, or past it. */
function runGuard(showing: boolean): {
  note: FakeNode;
  failed: FakeNode;
  fire: (target: unknown) => void;
  fireThrow: () => void;
  capture: boolean;
} {
  const note: FakeNode = { hidden: false, querySelector: () => null };
  const failed: FakeNode = { hidden: true, querySelector: () => null };
  const boot: FakeNode = {
    hidden: false,
    querySelector: (s) => (s === "[data-boot-note]" ? note : s === "[data-boot-failed]" ? failed : null),
  };
  let handler: ((event: unknown) => void) | null = null;
  let capture = false;
  const window = {
    addEventListener(type: string, fn: (event: unknown) => void, useCapture?: boolean) {
      if (type !== "error") return;
      handler = fn;
      capture = useCapture === true;
    },
  };
  const document = { querySelector: (s: string) => (s === "[data-boot]" && showing ? boot : null) };
  runInNewContext(guardSource, { window, document });
  assert.ok(handler !== null, "boot-guard.js must listen for error events");
  return {
    note,
    failed,
    // A resource error carries the failed element as its target.
    fire: (target) => handler?.({ target }),
    // A thrown exception's error event has the window as its target.
    fireThrow: () => handler?.({ target: window }),
    capture,
  };
}

test("the guard is loaded before the bundle, and not deferred", () => {
  // A race, closed by ordering. `<script type="module">` is implicitly
  // deferred: it is FETCHED while the document parses and EXECUTED afterwards,
  // and its `error` event fires whenever that fetch settles. A guard placed
  // after it -- or given `defer` -- is a guard that may not have run yet when
  // that happens, and an error nobody is listening for is an indicator that
  // claims "Starting…" forever.
  //
  // Asserted on the markup rather than in a browser, and that is not a
  // shortcut: over a real connection the fetch always loses to the parser, so
  // the wrong order passes a browser proof every time and fails the day a
  // service worker or a memory cache answers instantly. The ordering is the
  // guarantee; this is where it is pinned.
  const guard = markup.indexOf('src="./boot-guard.js"');
  const bundle = markup.indexOf('src="./app.js"');
  assert.ok(guard !== -1, "the page must load boot-guard.js, or nothing reports a failed boot");
  assert.ok(bundle !== -1, "the page must still load the bundle");
  assert.ok(guard < bundle, "boot-guard.js must be loaded before app.js");
  const tag = /<script[^>]*boot-guard\.js[^>]*>/.exec(markup)?.[0] ?? "";
  assert.doesNotMatch(tag, /\b(defer|async|type="module")/, `the guard must run during parsing: ${tag}`);
});

test("a boot script that fails to load turns the indicator into a failure notice", () => {
  // The one failure with nobody left to report it: app/src/crash.ts is
  // installed by `mount()`, which lives in the module that just failed. Without
  // this, a static "Starting…" would sit there claiming progress forever --
  // which is worse than the blank page, because it is a blank page that lies.
  const { note, failed, fire } = runGuard(true);
  fire({ tagName: "SCRIPT", src: "https://example.test/PraisonAI/app.js" });
  assert.equal(failed.hidden, false, "the failure notice must be revealed");
  assert.equal(note.hidden, true, '"Starting…" must go: it is no longer true');
});

test("a throw before the app has rendered is reported: app code failing is a failed boot", () => {
  // A runtime error whose event.target is the window -- app.js parsed and ran
  // but threw on its way in, before mount() could install crash.ts. Nobody
  // else is left to report it, so the guard must.
  const { note, failed, fireThrow } = runGuard(true);
  fireThrow();
  assert.equal(failed.hidden, false, "a throw (target === window) is the app failing");
  assert.equal(note.hidden, true);
});

test("register-sw.js failing to load does not claim the app could not start", () => {
  // register-sw.js is a CLASSIC script that runs during parse, BEFORE the
  // deferred app.js module executes. If its download fails while app.js is
  // still in flight, the app can still load and mount -- so treating every
  // <script> error as an app-bundle failure would flash "could not start" on a
  // page that is about to boot fine. The worker declining to register is a
  // degraded page (see register-sw.js), not a broken one, so it must be
  // ignored exactly as a failed stylesheet or icon is.
  for (const src of [
    "https://example.test/PraisonAI/register-sw.js",
    "https://example.test/PraisonAI/boot-guard.js",
  ]) {
    const { note, failed, fire } = runGuard(true);
    fire({ tagName: "SCRIPT", src });
    assert.equal(failed.hidden, true, `a failed ${src} must not be reported as a boot failure`);
    assert.equal(note.hidden, false);
  }
});

test("the guard listens in the CAPTURE phase, because a resource error does not bubble", () => {
  // A bubble-phase listener on window hears a thrown exception and never hears
  // a <script> that failed to download -- which is the case this file exists
  // for. Capture is also what lets the listener be installed before the script
  // element it is about has been parsed.
  assert.equal(runGuard(true).capture, true);
});

test("a stylesheet or an icon that fails does not claim the app could not start", () => {
  // `error` in the capture phase hears EVERY failed subresource. A missing
  // favicon is a degraded page, not an app that cannot start, and saying
  // otherwise would be the same class of lie pointed the other way.
  for (const tagName of ["LINK", "IMG"]) {
    const { note, failed, fire } = runGuard(true);
    fire({ tagName });
    assert.equal(failed.hidden, true, `a failed ${tagName} must not be reported as a boot failure`);
    assert.equal(note.hidden, false);
  }
});

test("once the app has rendered, the guard says nothing at all", () => {
  // The invariant that keeps this file from double-reporting over
  // app/src/crash.ts: the app's first paint clears #root, so from then on
  // there is no boot indicator to find and every later error belongs to the
  // crash handler alone.
  const { note, failed, fire } = runGuard(false);
  fire({ tagName: "SCRIPT", src: "https://example.test/PraisonAI/app.js" });
  assert.equal(failed.hidden, true, "a post-render error is the crash handler's, not this file's");
  assert.equal(note.hidden, false);
});
