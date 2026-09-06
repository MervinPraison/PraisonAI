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
  // RESOLVED, not matched as text. This read `/\+\s*[\d.]+rem/` -- a literal
  // rem after the plus -- which was true only while every gutter in the file
  // was a hardcoded number. The moment they became scale tokens the assertion
  // failed, and the tempting repair (allow `var(...)` too) would have passed
  // over `+ var(--nonexistent)` and over `+ var(--space-0)` if that were 0.
  // So the token is looked up on `:root` and the NUMBER it resolves to is what
  // is checked.
  const gutter = addendOf(value);
  assert.ok(gutter > 0, `the gutter must survive a zero inset, and it is ${gutter}rem: ${value}`);
});

/** Every custom property declared on `:root`, for resolving one token to the
 *  number it stands for. Only `:root` -- a token redefined for dark mode is a
 *  colour, and no geometry in this file is theme-dependent. */
const ROOT_TOKENS = new Map(
  declarationsOf(ruleFor(":root").body).filter(([prop]) => prop.startsWith("--")),
);

/**
 * A token's value in rem, following `var()` indirection as far as it goes.
 *
 * `--gutter: var(--space-4)` and `--space-4: .75rem` is two hops, and the
 * point of the scale is that a rule names the role rather than the number --
 * so a test that cannot follow the indirection cannot check the number.
 * Anything that does not end at a rem literal returns NaN, which fails every
 * comparison below rather than passing one.
 */
function remOf(token: string, seen = new Set<string>()): number {
  if (seen.has(token)) return Number.NaN;
  seen.add(token);
  const raw = ROOT_TOKENS.get(token);
  if (raw === undefined) return Number.NaN;
  const indirect = /^var\((--[a-z0-9-]+)\)$/.exec(raw.trim())?.[1];
  if (indirect !== undefined) return remOf(indirect, seen);
  const rem = /^([\d.]+)rem$/.exec(raw.trim())?.[1];
  return rem === undefined ? Number.NaN : Number(rem);
}

/** The rem added to an inset inside `calc(var(--inset-x) + <addend>)`, whether
 *  the addend is written as a literal or as a scale token. */
function addendOf(padding: string): number {
  const literal = /\+\s*([\d.]+)rem/.exec(padding)?.[1];
  if (literal !== undefined) return Number(literal);
  const token = /\+\s*var\((--[a-z0-9-]+)\)/.exec(padding)?.[1];
  return token === undefined ? Number.NaN : remOf(token);
}

test("the stylesheet's gutter and the one main.ts writes inline are the same number", () => {
  // The composer is the ONE element whose inline padding is written from
  // script -- an inline style beats the stylesheet, and it has to, because the
  // value moves with the live insets. So the gutter exists twice: as
  // `--gutter` here and as a literal inside a template string in main.ts.
  //
  // Nothing connected them. Renaming or retuning the scale would have left the
  // composer sitting a few pixels off every other screen edge in the app --
  // the kind of drift that is invisible in a screenshot of one screen and
  // obvious the moment you tab between two.
  const scripted = /padding-inline-start",\s*`([^`]*)`/.exec(main)?.[1] ?? "";
  const inline = addendOf(scripted);
  assert.ok(inline > 0, `main.ts writes no gutter at all: ${scripted}`);

  const token = remOf("--gutter");
  assert.ok(Number.isFinite(token), "--gutter must resolve to a rem through :root");
  assert.equal(
    token,
    inline,
    `app.css lays out on a ${token}rem gutter and main.ts writes ${inline}rem inline`,
  );

  // And the stylesheet's own screen edges use that token rather than a number
  // of their own, which is what makes the check above worth making.
  // BOTH inline sides, separately. The first version of this loop asked for
  // `--inset-(right|left)` in one alternation, which is satisfied by either --
  // so replacing the right-hand gutter with a bare `.5rem` left the left-hand
  // one matching and the mutation survived. A screen inset correctly on one
  // edge and wrongly on the other is precisely the defect worth catching.
  for (const selector of [".screen-settings,\n.screen-chats", ".transcript", ".topbar"]) {
    const rule = RULES.find((r) => r.selector.replace(/\s+/g, " ") === selector.replace(/\s+/g, " "));
    assert.ok(rule !== undefined, `app.css must still declare "${selector}"`);
    for (const side of ["right", "left"] as const) {
      assert.match(
        rule.body,
        new RegExp(`calc\\(var\\(--inset-${side}\\)\\s*\\+\\s*var\\(--gutter\\)\\)`),
        `${selector} must build its ${side} padding from --gutter`,
      );
    }
  }
});

/**
 * Rules parsed by BRACE MATCHING, not by a `}`-anchored regex.
 *
 * `[^}]*` stops at the first closing brace it meets, which for a declaration
 * containing `calc(...)` or a nested block is not the end of the rule -- an
 * earlier agent's colour test silently matched nothing and passed over a rule
 * it had never seen. This walks the stylesheet, so a selector that is absent is
 * absent rather than "not matched".
 */
function rules(source: string): readonly { selector: string; body: string }[] {
  const found: { selector: string; body: string }[] = [];
  let index = 0;
  while (index < source.length) {
    const open = source.indexOf("{", index);
    if (open === -1) break;
    let depth = 1;
    let cursor = open + 1;
    while (cursor < source.length && depth > 0) {
      if (source[cursor] === "{") depth += 1;
      else if (source[cursor] === "}") depth -= 1;
      cursor += 1;
    }
    const selector = source.slice(index, open).trim();
    const body = source.slice(open + 1, cursor - 1);
    // An at-rule (`@media`) holds rules rather than declarations; recurse into
    // it so a token redefined for dark mode is found under its own selector.
    if (selector.startsWith("@")) found.push(...rules(body));
    else found.push({ selector, body });
    index = cursor;
  }
  return found;
}

/** Every rule whose selector list contains `wanted`, asserted non-empty -- so a
 *  selector that was renamed fails here instead of passing vacuously. */
function rulesFor(wanted: string): readonly { selector: string; body: string }[] {
  const matched = rules(css).filter((rule) =>
    rule.selector.split(",").some((part) => part.trim() === wanted),
  );
  assert.ok(matched.length > 0, `no rule in app.css has the selector "${wanted}"`);
  return matched;
}

test("a hidden Remove button is actually hidden", () => {
  // `.setting-clear` is a flex ITEM in a `.row-setting` flex column, and
  // main.ts sets `hidden` on it the moment there is no key to remove. The
  // pairing this file already asserts for `.screen[hidden]` applies: an author
  // `display` declaration beats the user agent's `[hidden] { display: none }`,
  // and the failure mode is the exact defect being fixed -- a `Remove` button
  // under a row that reads "Not set".
  const hiding = rulesFor(".setting-clear[hidden]");
  assert.ok(
    hiding.some((rule) => /display\s*:\s*none/.test(rule.body)),
    `.setting-clear[hidden] must set display: none -- found: ${hiding.map((r) => r.body).join(" | ")}`,
  );
});

test("a field that is switched off says so in the note, not in a warning colour", () => {
  // "Set Engine to remote-http to use this" is not an error. Painting it
  // `--warn` beside a field the user has not touched teaches people that the
  // warning colour means nothing, which is what it costs when a real refusal
  // appears in `.setting-error` two lines below.
  const inactive = rulesFor(".row-setting .setting-inactive");
  const body = inactive.map((r) => r.body).join(" ");
  assert.match(body, /color\s*:\s*var\(--soft\)/, `the inactive note must be soft, not loud: ${body}`);
  assert.equal(/var\(--warn\)/.test(body), false, `nothing is wrong: ${body}`);
  // And it hides properly, for the same author-declaration reason as above.
  const hidden = rulesFor(".row-setting .setting-inactive[hidden]");
  assert.ok(hidden.some((rule) => /display\s*:\s*none/.test(rule.body)), "an empty note must not paint");
});

test("the settings sections are styled on the class the app actually emits", () => {
  // app.css styled `.section-heading`; `buildSettingsScreen` emits
  // `.settings-section`. So every heading rendered at the browser's default
  // `h3` and the screen read as one flat list -- a credential and an engine
  // address at the same weight. The class names have to be the SAME name.
  assert.ok(main.includes('className = "settings-section"'), "main.ts still emits settings-section");
  const styled = rulesFor(".screen-settings .settings-section");
  const body = styled.map((r) => r.body).join(" ");
  assert.match(body, /text-transform|font-size|letter-spacing/, `a heading must look like one: ${body}`);
  // The lead section keeps the ink colour while the others go soft: that is the
  // hierarchy, and it is the whole reason main.ts writes `data-lead`.
  assert.ok(main.includes('dataset["lead"]'), "main.ts must mark the lead section");
  const lead = rulesFor('.screen-settings .settings-section[data-lead]');
  assert.match(lead.map((r) => r.body).join(" "), /color\s*:\s*var\(--ink\)/);
});

test("nothing removes the focus ring from a keyboard focus", () => {
  /*
   * This branch introduced `.screen-heading:focus { outline: none }` and a
   * comment claiming "a real keyboard focus still gets one, from
   * `:focus-visible` below". The comment was wrong, and specificity is why:
   * `.screen-heading:focus` is (0,2,0) and the global `:focus-visible` rule is
   * (0,1,0), so the suppression won for BOTH kinds of focus and route
   * navigation to a heading left a keyboard user with no visible focus at all.
   * `praisonai-triage-agent[bot]` caught it and scoped the rule to
   * `:focus:not(:focus-visible)`, which is the correct idiom.
   *
   * None of the gates on this branch saw it -- they measure colour, size and
   * weight, and this is a rule that removes something. So the invariant is
   * stated directly: a rule may quieten a programmatic focus, but no rule may
   * take the outline off an element that is `:focus-visible`.
   *
   * Text-level rather than computed, deliberately: `:focus-visible` depends on
   * the heuristics of the last input modality, which a headless browser cannot
   * be made to assert both ways reliably. The cascade, however, is decidable
   * from the selector alone.
   */
  const killers = RULES.filter((rule) =>
    declarationsOf(rule.body).some(
      ([prop, value]) => prop === "outline" && /^(none|0)\b/.test(value.trim()),
    ),
  );
  assert.ok(
    killers.length > 0,
    "no rule suppresses an outline -- if that is now true, delete this test rather than letting it pass vacuously",
  );
  for (const rule of killers) {
    for (const selector of rule.selector.split(",").map((s) => s.trim())) {
      if (!/:focus\b/.test(selector)) continue;
      assert.match(
        selector,
        /:not\(\s*:focus-visible\s*\)/,
        `"${selector}" removes the outline from every focus, keyboard included; ` +
          "scope it with :focus:not(:focus-visible)",
      );
    }
  }

  // And the ring it must not remove has to exist in the first place.
  const ring = RULES.filter((r) => r.selector.split(",").some((s) => s.trim() === ":focus-visible"));
  assert.equal(ring.length, 1, "app.css must declare the :focus-visible ring exactly once");
  // Destructured and re-guarded rather than indexed: `assert.equal` on the
  // length narrows nothing for tsc, and `npm test` strips types without
  // checking them -- so an indexed read passes every run here and fails
  // `npm run typecheck`, which is the first thing `npm run check` does.
  const [only] = ring;
  assert.ok(only !== undefined, "the :focus-visible rule must have been parsed");
  assert.match(only.body, /outline:\s*\d/, "the ring must actually draw an outline");
});
