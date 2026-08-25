/**
 * The transcript and the composer must sit on the same centre line.
 *
 * They did not. `.inner` (the transcript column) declared
 * `max-width:46rem; margin:0 auto` inside `#thread`, which is a flex column --
 * and an auto margin on a flex item's cross axis overrides `align-self:stretch`.
 * So the transcript shrink-wrapped its content and centred *itself*, while the
 * composer, a block child of a block <form>, stayed full width. On a 970px
 * window the two centre lines were about 240px apart and the chat looked
 * broken.
 *
 * jsdom has no layout engine, so these assert the declared values that decide
 * the layout, plus the specific flex trap that caused it.
 */
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import assert from 'node:assert/strict';
import test from 'node:test';

const HTML = readFileSync(new URL('../../ui/index.html', import.meta.url), 'utf8');
// Comments stripped first: a /* ... */ block directly above a rule would
// otherwise become part of the selector text and the lookup would miss.
const CSS = HTML.slice(HTML.indexOf('<style>'), HTML.indexOf('</style>'))
  .replace(/\/\*[\s\S]*?\*\//g, '');

/**
 * Declarations of the rule whose selector list contains exactly `selector`.
 *
 * Deliberately simple: split the stylesheet on braces rather than trying to
 * match a selector with a regex. The first attempt used `\\b` in front of a `.`
 * class selector, which can never match -- a dot is not a word character, so
 * every lookup failed and every assertion below reported a defect that was not
 * there.
 */
function rule(selector) {
  const found = [];
  for (const block of CSS.split('}')) {
    const i = block.indexOf('{');
    if (i < 0) continue;
    const sels = block.slice(0, i).split(',').map((x) => x.trim().replace(/\s+/g, ' '));
    if (!sels.includes(selector)) continue;
    found.push(block.slice(i + 1));
  }
  assert.ok(found.length, `no rule with the exact selector "${selector}"`);
  // Later rules win, so fold in order.
  const out = {};
  for (const body of found) {
    for (const decl of body.split(';')) {
      const c = decl.indexOf(':');
      if (c < 0) continue;
      out[decl.slice(0, c).trim()] = decl.slice(c + 1).trim();
    }
  }
  return out;
}

test('the transcript and the composer are the same column element', () => {
  // Stronger than "both declare the same max-width". They used to: .inner put
  // the gutter *inside* --col and <form> put it *outside*, so below 784px of
  // main width the boxes were 24px apart and 48px different in width -- and
  // the sign of the offset flipped when the sidebar was hidden. Wrapping the
  // composer in the same .inner makes a second column inexpressible.
  const inner = rule('.inner');
  assert.equal(inner['max-width'], 'var(--col)');
  assert.equal(inner.margin, '0 auto');
  assert.equal(inner.width, '100%');

  // Matched structurally, not as an exact markup string: the first version
  // pinned every attribute on #turns, so adding role="log" broke a test about
  // column geometry, which is not what it is for.
  const turns = /<div [^>]*class="inner"[^>]*id="turns"/.test(HTML);
  const composer = /<form id="f">\s*<div class="inner">\s*<div class="fi">/.test(HTML);
  assert.ok(turns, 'the transcript is not in an .inner');
  assert.ok(composer, 'the composer is not in an .inner -- it has its own column again');
});

test('both columns declare an explicit width, defeating the flex auto-margin trap', () => {
  // This is the actual bug. Without width:100% the flex item shrink-wraps.
  assert.equal(rule('.inner').width, '100%',
    '.inner will shrink-wrap and self-centre inside #thread');
  assert.equal(rule('.fi').width, '100%');
});

test('#thread is still the flex column that makes the trap possible', () => {
  // If this ever stops being a flex column the comment above is wrong, and
  // whoever reads it should be told rather than left guessing.
  const t = rule('#thread');
  assert.equal(t.display, 'flex');
  assert.equal(t['flex-direction'], 'column');
});

test('only .inner sets the horizontal gutter', () => {
  // Two elements insetting the same content is how they drifted apart. The
  // form must contribute vertical padding only.
  assert.equal(rule('.inner').padding, '0 var(--gutter)');
  const formPad = rule('form').padding.split(/\s+/);
  assert.equal(formPad[1], '0', `form still insets horizontally: ${formPad.join(' ')}`);
  assert.equal(rule('.fi')['max-width'], undefined,
    'the composer declares its own width again');
});

test('the update bar cannot cover the composer', () => {
  // It was position:fixed at bottom:18px, i.e. directly on top of the text
  // field, and a composer grown to ten lines would have been worse.
  const u = rule('.updbar');
  assert.notEqual(u.position, 'fixed', 'the update bar is floating over the page again');
  assert.equal(u['max-width'], 'var(--col)', 'the bar is not in the reading column');
});

test('nothing fixed is anchored into the composer strip', () => {
  // The composer occupies roughly the bottom 90px; anything pinned there
  // overlaps it. Toasts belong above the thread, not on the input.
  const fixed = [...CSS.matchAll(/([^{}]+)\{([^}]*position:\s*fixed[^}]*)\}/g)];
  assert.ok(fixed.length > 0, 'expected at least one fixed element to check');
  for (const [, sel, body] of fixed) {
    const bottom = /bottom:\s*(\d+)px/.exec(body);
    if (bottom) {
      assert.ok(Number(bottom[1]) > 130,
        `${sel.trim()} is pinned ${bottom[1]}px from the bottom, over the composer`);
    }
  }
});

test('a chat row shows something that tells two identical titles apart', async () => {
  const dom = new JSDOM('<!doctype html><div id="x"></div>');
  // Five conversations that all opened with the same sentence produced five
  // identical rows. The engine has always returned `updated` and `count`.
  assert.match(HTML, /class="meta"/, 'chat rows carry no distinguishing metadata');
  assert.match(HTML, /function relTime\(/, 'no relative-time helper');
  dom.window.close();
});

// --- interface scale ---------------------------------------------------------

test('text size drives the rem root, not just the message body', () => {
  // It used to set --fs, which only .bubble read: the chat text changed and
  // the sidebar, titlebar, settings and composer did not.
  assert.match(CSS, /html\{font-size:calc\(16px \* var\(--ui-scale/,
    'the root font size is not derived from the scale');
  assert.match(HTML, /setProperty\('--ui-scale'/, 'nothing ever sets --ui-scale');
});

test('no chrome dimension is pinned in pixels', () => {
  // A px width here stays put while the text around it grows, which turns a
  // text-size setting into a set of misaligned boxes. Hairlines and the 16px
  // scale base are the deliberate exceptions.
  const offenders = [];
  // `font:` shorthand included deliberately. The first version of this test
  // only looked for `font-size:`, so it passed while `body{font:14.5px/1.6 …}`
  // pinned the composer -- which inherits from body -- at a fixed size. The
  // interface scaled and the box you type into did not.
  for (const m of CSS.matchAll(
    /(width|height|min-width|max-width|font-size|font|top|left|right|bottom):\s*([^;}]*?(\d+(?:\.\d+)?)px[^;}]*)/g)) {
    const [, prop, value, num] = m;
    if (Number(num) <= 3) continue;                 // hairlines and insets
    if (value.includes('calc(16px * var(--ui-scale')) continue;  // the base itself
    offenders.push(`${prop}: ${value.trim()}`);
  }
  assert.deepEqual(offenders, [], `these will not scale:\n  ${offenders.join('\n  ')}`);
});

test('the reading column is expressed in rem so it scales too', () => {
  assert.match(CSS, /--col:\s*\d+(\.\d+)?rem/, 'the column is not in rem');
  assert.match(CSS, /--gutter:\s*\d+(\.\d+)?rem/);
});

test('contain-intrinsic-size scales, so off-screen turns are estimated correctly', () => {
  // content-visibility uses this as a stand-in height. Pinned in px it
  // under-estimates every turn at a larger text size and the scrollbar jumps.
  const t = rule('.turn');
  assert.match(t['contain-intrinsic-size'], /rem|em/,
    'the scroll estimate does not follow the text size');
});

test('code size is derived from the same scale as prose', () => {
  assert.match(HTML, /--fs-code',\s*\(\(Number\(c\.code_font_size\)\|\|12\)\s*\*\s*scale\)/,
    'code blocks keep their absolute size while the prose around them grows');
});

// --- controls and affordances ------------------------------------------------

test('a sidebar row is a control, not a div with a handler on its title', () => {
  // The handler sat on `.t` -- 59.7px of a 231px row -- so most of the row,
  // including the metadata line, was a dead click zone. And a div with onclick
  // is unreachable by keyboard.
  assert.match(HTML, /d\.setAttribute\('role','button'\)/, 'the row has no role');
  assert.match(HTML, /d\.tabIndex\s*=\s*0/, 'the row is not focusable');
  assert.match(HTML, /d\.onclick\s*=\s*ev\s*=>\s*\{\s*if\(!ev\.target\.closest\('\.x'\)\)/,
    'the click handler is not on the whole row');
  assert.match(HTML, /d\.onkeydown/, 'Enter and Space do not open a chat');
  assert.match(HTML, /\.t'\)\.title\s*=\s*c\.title/, 'a truncated title cannot be read');
});

test('the delete affordance is reachable without a mouse', () => {
  const css = CSS.replace(/\s+/g, ' ');
  assert.match(css, /\.chat:focus-within \.x/, 'delete only appears on hover');
});

test('the composer grows with its content', () => {
  // rows="1" with max-height:10rem and nothing assigning style.height:
  // measured 31.2px at twelve lines with scrollHeight 286.
  assert.match(HTML, /function autosize\(\)/);
  assert.match(HTML, /box\.addEventListener\('input',autosize\)/);
  // .value assignment fires no input event, so those paths must resize too.
  // setComposer is the one sanctioned writer; everything else must go through it.
  const strays = HTML.split('\n')
    .filter((l) => /box\.value\s*=/.test(l) && !l.includes('function setComposer'));
  assert.deepEqual(strays, [],
    `these set the composer without resizing it:\n  ${strays.join('\n  ')}`);
  assert.match(HTML, /function setComposer\(text\)\{ box\.value=text; autosize\(\); \}/);
});

test('syntax colours are tokens, defined in every theme block', () => {
  for (const tok of ['--tok-k', '--tok-s', '--tok-n', '--tok-f']) {
    const defs = (CSS.match(new RegExp(`${tok}:`, 'g')) || []).length;
    assert.ok(defs >= 4, `${tok} defined ${defs} times; needs all four theme blocks`);
  }
  assert.equal((CSS.match(/\.tok-[ksnf]\{color:#/g) || []).length, 0,
    'a syntax colour is still hardcoded and will fail in one theme');
});

test('the settings scrim covers the toast', () => {
  assert.ok(Number(/#overlay\{[^}]*z-index:(\d+)/.exec(CSS)[1])
          > Number(/#toast\{[^}]*z-index:(\d+)/.exec(CSS)[1]),
    'the toast paints above the dimmed scrim, undimmed');
});

test('a wide table scrolls instead of crushing its columns', () => {
  // display:block alone made the table shrink to its container so overflow-x
  // never engaged: 14 columns became 47.8px each with stacked headers.
  const t = rule('.bubble table');
  assert.equal(t.width, 'max-content', 'the table cannot exceed its container, so it cannot scroll');
  assert.equal(t['overflow-x'], 'auto');
  assert.equal(t['max-width'], '100%', 'the table will push the page sideways');
});

// --- dialogs and window chrome -----------------------------------------------

test('no native confirm() survives anywhere in the page', () => {
  // A WKWebView under Tauri implements no JS dialog panel, so `confirm()`
  // returns false immediately without showing anything. Every guard written as
  // `if (!confirm(...)) return;` takes the cancel branch every time -- which is
  // how adding confirm_delete silently broke deleting a conversation outright.
  const strays = HTML.split('\n')
    .map((l, i) => [i + 1, l])
    .filter(([, l]) => /(^|[^a-zA-Z.])confirm\s*\(/.test(l) && !/\*/.test(l));
  assert.deepEqual(strays.map(([n, l]) => `${n}: ${l.trim()}`), [],
    'these call the native dialog, which never appears and always cancels');
});

test('destructive confirmations go through the in-app dialog', () => {
  assert.match(HTML, /function askConfirm\(/, 'there is no in-app confirmation');
  for (const site of ['This cannot be undone', 'Delete this exchange']) {
    assert.ok(HTML.includes(site), `expected a confirmation for "${site}"`);
  }
  const calls = (HTML.match(/await askConfirm\(/g) || []).length;
  assert.ok(calls >= 5, `only ${calls} call sites use askConfirm`);
});

test('the titlebar carries the attribute Tauri actually reads', () => {
  // -webkit-app-region:drag is a Chromium feature. WKWebView does not implement
  // it, so the strip was inert however it was styled.
  assert.match(HTML, /<div class="titlebar" data-tauri-drag-region>/,
    'the titlebar cannot move the window');
});
