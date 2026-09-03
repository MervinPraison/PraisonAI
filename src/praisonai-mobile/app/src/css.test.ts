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
