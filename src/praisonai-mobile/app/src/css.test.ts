/**
 * The stylesheet, checked against what the app does to it.
 *
 * `app.css` is not typechecked, not bundled through the gate, and not covered
 * by any test -- so three rules that decide whether the app is usable on a
 * phone were unasserted. Each of these was a measured defect, not a hypothetical.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const raw = readFileSync(join(import.meta.dirname, "../app.css"), "utf8");
/** Comments explain the rules and sometimes name the very token a rule must
 *  NOT contain, so they are stripped before matching. */
const css = raw.replace(/\/\*[\s\S]*?\*\//g, "");
const main = readFileSync(join(import.meta.dirname, "main.ts"), "utf8")
  .replace(/\/\/.*$/gm, "");

test("a hidden screen is actually hidden", () => {
  // `.screen { display: flex }` is an AUTHOR declaration and beats the user
  // agent's `[hidden] { display: none }`, so `el.hidden = true` in mount.ts did
  // nothing. Measured in headless Chrome: after tapping Settings the chat
  // screen was still on screen at half height with the settings list stacked
  // under it, and every navigation halved the viewport again.
  assert.match(css, /\.screen\[hidden\]\s*\{[^}]*display:\s*none/, "app.css must hide a hidden screen");
});

test("the composer does not add the bottom inset twice", () => {
  // `--keyboard-height` is written from `geometryOf`, which is already
  // `max(keyboard, insets.bottom)`. Adding `--safe-area-inset-bottom` back is
  // the `bottom + keyboard` sum that ui/src/layout/insets.ts calls "the single
  // most recognisable 'web page in a box' tell there is".
  // Each declaration taken up to its semicolon, rather than by a paren-matching
  // regex: `calc(var(a) + var(b))` has two nested groups and a `[^)]*` pattern
  // stops at the first `)`, which is why the first version of this test passed
  // against the bug it was written for.
  const declarations = [...css.matchAll(/padding-bottom\s*:([^;]*);/g)].map((m) => m[1] ?? "");
  const keyboardDecls = declarations.filter((d) => d.includes("--keyboard-height"));
  assert.ok(keyboardDecls.length > 0, "the composer must follow the keyboard at all");
  for (const d of keyboardDecls) {
    // BOTH names. The stylesheet now lays out against `--inset-bottom` (the
    // effective inset main.ts writes from `shell.insets`) rather than the
    // `--safe-area-inset-bottom` env() mirror, so a test that only knew the old
    // name would have gone quiet the moment the rename landed and let the
    // double-count back in under the new one.
    for (const name of ["--safe-area-inset-bottom", "--inset-bottom"]) {
      assert.ok(
        !d.includes(name),
        `--keyboard-height is already max(keyboard, inset); adding ${name} double-counts it:${d}`,
      );
    }
  }
});

test("the composer keeps a gutter when the inset is zero", () => {
  // main.ts writes padding-inline INLINE, which beats the stylesheet. Writing
  // the bare inset put the textarea flush to the screen edge at a 320px
  // viewport while every other element kept its 12px gutter.
  const starts = /padding-inline-start",\s*`([^`]*)`/.exec(main)?.[1] ?? "";
  const ends = /padding-inline-end",\s*`([^`]*)`/.exec(main)?.[1] ?? "";
  for (const [side, value] of [["start", starts], ["end", ends]] as const) {
    assert.match(value, /\+\s*\.75rem/, `the ${side} gutter must survive a zero inset: ${value}`);
  }
});

test("the viewport bridge the safe areas depend on is intact -- the pair", () => {
  // The three rules above are all about safe-area handling; if the bridge that
  // supplies the values were removed they would all pass while measuring zero.
  assert.match(css, /--safe-area-inset-bottom:\s*env\(safe-area-inset-bottom/);
  assert.match(css, /--safe-area-inset-top:\s*env\(safe-area-inset-top/);
});

// ---- the empty chat screen --------------------------------------------------
//
// These four assert a stylesheet, which is exactly where a test can lie to
// itself. The rules below are found by BRACE MATCHING, not by a global regex,
// and every selector is looked up through `ruleFor`, which fails when it is not
// found EXACTLY once.
//
// That is not fussiness. The first version of this block used
// `/\.empty-state\s*\{([^}]*)\}/g` over the whole file, and `[^}]*` stops at
// the first `}` -- so a rule containing a nested block, or simply renamed,
// silently dropped out of the sample and the loop that "checked every rule"
// checked nothing while still passing. A gate that shrinks its own sample to
// zero and reports success is worse than no gate.

interface CssRule {
  readonly selector: string;
  readonly body: string;
  /** The at-rule this sits inside, or "" at the top level. */
  readonly at: string;
}

/** Every rule in the sheet, by matching braces rather than by scanning for the
 *  next `}`. At-rules are recursed into, so a rule inside `@media` is found
 *  with the media condition attached rather than lost. */
function rulesOf(css: string, at = ""): CssRule[] {
  const out: CssRule[] = [];
  let start = 0;
  let i = 0;
  while (i < css.length) {
    if (css[i] !== "{") {
      i += 1;
      continue;
    }
    const prelude = css.slice(start, i).trim();
    let depth = 1;
    let j = i + 1;
    while (j < css.length && depth > 0) {
      if (css[j] === "{") depth += 1;
      else if (css[j] === "}") depth -= 1;
      j += 1;
    }
    assert.equal(depth, 0, `unbalanced braces in app.css after "${prelude}"`);
    const body = css.slice(i + 1, j - 1);
    if (prelude.startsWith("@")) out.push(...rulesOf(body, prelude));
    else out.push({ selector: prelude, body, at });
    i = j;
    start = j;
  }
  return out;
}

const RULES = rulesOf(css);

/** The one rule with this selector. Asserts it was found, so a selector that
 *  stops existing FAILS instead of quietly leaving nothing to check. */
function ruleFor(selector: string): CssRule {
  const found = RULES.filter((r) => r.selector === selector);
  assert.equal(found.length, 1, `app.css must declare "${selector}" exactly once (found ${found.length})`);
  return found[0] as CssRule;
}

/** `color: var(--ink)` -> ["color", "var(--ink)"]. Declarations only; these
 *  bodies hold no nested blocks. */
const declarationsOf = (body: string): readonly (readonly [string, string])[] =>
  body
    .split(";")
    .map((d) => d.trim())
    .filter((d) => d !== "")
    .map((d) => {
      const at = d.indexOf(":");
      return [d.slice(0, at).trim(), d.slice(at + 1).trim()] as const;
    });

test("the parser actually sees the stylesheet", () => {
  // The guard on every test below: if `rulesOf` ever returned an empty or tiny
  // list -- a syntax change, a wrong argument -- each `ruleFor` would fail, but
  // this says so in one sentence rather than as four confusing misses.
  assert.ok(RULES.length > 30, `only ${RULES.length} rules parsed out of app.css`);
  const selectors = new Set(RULES.map((r) => r.selector));
  for (const known of [":root", ".screen", ".transcript", ".composer", ".empty-state"]) {
    assert.ok(selectors.has(known), `"${known}" was not parsed out of app.css`);
  }
});

test("a hidden empty state is actually hidden", () => {
  // The same defect `.screen[hidden]` was written for, in a new place: the
  // author `display: flex` below beats the user agent's `[hidden]` rule, so
  // without an explicit override `emptyPanel.hidden = true` does nothing and
  // the welcome panel stays on screen underneath the conversation.
  assert.match(ruleFor(".empty-state").body, /display:\s*flex/, "the override is only needed because of this");
  assert.match(ruleFor(".empty-state[hidden]").body, /display:\s*none/);
  // And the button inside it, which is hidden on its own in the welcome state.
  assert.match(ruleFor(".empty-state button[hidden]").body, /display:\s*none/);
});

test("the transcript yields its height while the empty state is up", () => {
  // Both are children of the same flex column and `.transcript` is `flex: 1`.
  // With a second `flex: 1` beside it the two split the screen, and the panel
  // sits in the lower half under a tall blank box -- the very rectangle this
  // change exists to remove, halved.
  assert.match(ruleFor(".transcript").body, /flex:\s*1/);
  assert.match(ruleFor(".screen[data-empty] .transcript").body, /flex:\s*0\s+0\s+auto/);
  // The attribute the rule hangs on has to be one the app actually writes.
  assert.match(main, /dataset\["empty"\]/, "app.css keys off data-empty; main.ts must set it");
});

test("the empty state is legible in dark mode, because it uses no literal colours", () => {
  // The mutation this kills: replacing `var(--ink)` with the light value it
  // resolves to. That looks identical in every screenshot taken in light mode
  // and renders near-black text on the near-black dark ground.
  //
  // Both halves are asserted -- that the panel names tokens, and that the
  // tokens it names are actually redefined for dark. Either alone passes over
  // the bug: a token with no dark value is a literal with extra steps.
  const dark = RULES.filter((r) => /prefers-color-scheme:\s*dark/.test(r.at));
  assert.ok(dark.length > 0, "app.css has no dark-scheme block at all");
  const darkTokens = new Set(
    dark.flatMap((r) => declarationsOf(r.body).map(([prop]) => prop)).filter((p) => p.startsWith("--")),
  );
  const rootTokens = new Set(
    declarationsOf(ruleFor(":root").body).map(([prop]) => prop).filter((p) => p.startsWith("--")),
  );

  let checked = 0;
  for (const selector of [".empty-state .empty-title", ".empty-state .empty-body"]) {
    const rule = ruleFor(selector);
    const colours = declarationsOf(rule.body).filter(([prop]) => prop === "color");
    assert.equal(colours.length, 1, `${selector} must state its colour exactly once`);
    const [, value] = colours[0] as readonly [string, string];
    const token = /var\((--[a-z-]+)\)/.exec(value)?.[1];
    assert.ok(token !== undefined, `${selector} paints a literal colour: ${value}`);
    assert.ok(rootTokens.has(token), `${token} is not defined on :root`);
    assert.ok(darkTokens.has(token), `${token} has no dark-scheme value, so ${selector} cannot follow the theme`);
    checked += 1;
  }
  // The sample cannot shrink to nothing and still pass.
  assert.equal(checked, 2, "both empty-state text rules must have been checked");
});

test("the empty state keeps clear of the safe area", () => {
  // Every other full-width surface in this file lays out against `--inset-*`
  // and this one is no different: a landscape cutout would otherwise clip the
  // first and last characters of a centred line. The insets are ADDED to the
  // gutter rather than replacing it, for the reason the composer states -- a
  // device with no inset on a side must still keep its gutter.
  const padding = declarationsOf(ruleFor(".empty-state").body).filter(([prop]) => prop === "padding");
  assert.equal(padding.length, 1, ".empty-state must state its padding exactly once");
  const [, value] = padding[0] as readonly [string, string];
  for (const name of ["--inset-left", "--inset-right"]) {
    assert.ok(value.includes(name), `.empty-state ignores ${name}: ${value}`);
  }
  assert.match(value, /\+\s*[\d.]+rem/, `the gutter must survive a zero inset: ${value}`);
});
