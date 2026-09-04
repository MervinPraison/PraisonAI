/**
 * The settings screen.
 *
 * The store goes out of its way to keep secrets away from the settings file and
 * to expose presence without a getter. These tests are what stop the view from
 * handing the value back through the front door -- and what stop an unresolved
 * keychain lookup from being rendered as "you have no key".
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  CONFIGURED,
  GENERAL_SECTION,
  NOT_SET,
  SOFTWARE_SECRETS_WARNING,
  buildSettings,
  controlFor,
  labelOf,
  rowsOf,
  secretRowsOf,
  validateInput,
  type SecretPresence,
  type SecretRow,
  type SettingsRow,
} from "./view-model.ts";
import { UNKNOWN } from "../format.ts";
import { clampNum, type SettingDef, type SettingValue, type SettingsFacade } from "../../../core/src/settings/store.ts";
import type { SecretRef } from "../../../core/src/ports/secrets.ts";

const OPENAI: SecretRef = { slot: "openai", account: "default" };

/**
 * A facade over a plain map. The real one is built in core's own tests; here
 * the subject is the view, so the store is reduced to the three things this
 * file reads from it.
 */
function fakeFacade(
  defs: readonly SettingDef[],
  values: Readonly<Record<string, SettingValue>> = {},
  hardwareBacked = true,
): SettingsFacade {
  return {
    get: (key) => values[key] ?? defs.find((d) => d.key === key)?.default,
    isSet: (key) => key in values,
    set: async () => true,
    defs: () => defs,
    subscribe: () => () => undefined,
    hasSecret: async () => false,
    setSecret: async () => undefined,
    clearSecret: async () => undefined,
    secretsAreHardwareBacked: hardwareBacked,
  };
}

const DEFS: readonly SettingDef[] = [
  { key: "model", default: "gpt-4o-mini", label: "Model", section: "Engine", choices: ["gpt-4o-mini", "gpt-4o"] },
  { key: "temperature", default: 0.7, section: "Engine", validate: clampNum(0, 2), help: "Higher is more random." },
  { key: "showReasoning", default: false, label: "Show reasoning" },
  { key: "apiKey", default: "", label: "API key", section: "Keys", secret: true },
];

const value = (rows: readonly SettingsRow[], key: string): SettingsRow => {
  const row = rows.find((r) => r.key === key);
  assert.ok(row !== undefined, `no row for ${key}`);
  return row;
};

test("rows are grouped by section and an ungrouped setting lands under General", () => {
  // A registry that grows a section nobody renders is a setting the user can
  // never reach -- the exact reason `defs()` was added to the store.
  const view = buildSettings(fakeFacade(DEFS));
  assert.deepEqual(
    view.sections.map((s) => s.title),
    ["Engine", GENERAL_SECTION, "Keys"],
  );
  assert.deepEqual(
    view.sections[1]?.rows.map((r) => r.key),
    ["showReasoning"],
  );
});

test("section order follows the registry rather than the alphabet", () => {
  // Alphabetical ordering silently reshuffles the whole screen the day a
  // section is renamed, and the setting someone is walking a user through by
  // phone is suddenly somewhere else.
  const defs: readonly SettingDef[] = [
    { key: "z", default: "", section: "Zulu" },
    { key: "a", default: "", section: "Alpha" },
  ];
  assert.deepEqual(
    buildSettings(fakeFacade(defs)).sections.map((s) => s.title),
    ["Zulu", "Alpha"],
  );
});

test("a def with choices renders as a picker and a boolean renders as a toggle", () => {
  // A closed set typed into a free text field is a model name with a typo in
  // it, which fails at request time with a provider error nobody can act on.
  const rows = rowsOf(buildSettings(fakeFacade(DEFS)));
  const model = value(rows, "model");
  assert.equal(model.kind === "value" && model.control, "choice");
  assert.deepEqual(model.kind === "value" ? model.choices : null, ["gpt-4o-mini", "gpt-4o"]);
  const toggle = value(rows, "showReasoning");
  assert.equal(toggle.kind === "value" && toggle.control, "toggle");
  const temperature = value(rows, "temperature");
  assert.equal(temperature.kind === "value" && temperature.control, "number");
});

test("an empty choices list falls back to the typed control rather than a dead picker", () => {
  // A picker with nothing in it cannot be operated at all, so the setting
  // becomes unreachable while still looking like a normal row.
  assert.equal(controlFor({ key: "x", default: 1, choices: [] }), "number");
});

test("the control kind comes from the def even when the stored value has the wrong type", () => {
  // A hand-edited settings file writes a string over a boolean. Deriving the
  // control from the value turns the toggle into a text box, and the setting
  // can then never be put back.
  const rows = rowsOf(buildSettings(fakeFacade(DEFS, { showReasoning: "yes" as unknown as boolean })));
  const row = value(rows, "showReasoning");
  assert.equal(row.kind === "value" && row.control, "toggle");
});

test("a secret row carries presence and has no value field at all", () => {
  // THE GUARANTEE. store.ts hands the UI a facade with no getter "so a view
  // cannot accidentally fault a key into the render tree where it can reach a
  // log, a crash report or a screenshot". A view model with a value field on
  // the secret row is where that ends.
  const presence: SecretPresence = new Map([["apiKey", { ref: OPENAI, configured: true }]]);
  const rows = secretRowsOf(buildSettings(fakeFacade(DEFS), presence));
  assert.equal(rows.length, 1);
  const row = rows[0];
  assert.ok(row !== undefined);
  assert.equal("value" in row, false);
  assert.equal(row.presence, CONFIGURED);
  assert.deepEqual(row.ref, OPENAI);
});

test("the type itself refuses a value on a secret row", () => {
  // The pair for the runtime check above: `in` only proves this particular
  // build did not set one. `value?: never` is what stops the next person from
  // adding it "just for the placeholder".
  const row: SecretRow = {
    kind: "secret",
    id: "secret:apiKey",
    key: "apiKey",
    label: "API key",
    help: null,
    state: "configured",
    presence: CONFIGURED,
    ref: OPENAI,
    // @ts-expect-error a secret row may not carry a value -- see rule 1.
    value: "sk-live-do-not-leak",
  };
  assert.equal(row.key, "apiKey");
});

test("a non-secret row does carry its current value", () => {
  // The pair that makes "expose nothing" fail: a screen that renders no values
  // at all satisfies the secret rule and is also useless.
  const rows = rowsOf(buildSettings(fakeFacade(DEFS, { temperature: 1.5 })));
  const row = value(rows, "temperature");
  assert.equal(row.kind === "value" && row.value, 1.5);
});

test("a stored false is rendered rather than replaced by a truthy default", () => {
  // `||` instead of `??` here is a toggle that switches itself back on every
  // time the screen is reopened, which reads as the setting not saving.
  const defs: readonly SettingDef[] = [{ key: "beta", default: true }];
  const rows = rowsOf(buildSettings(fakeFacade(defs, { beta: false })));
  const row = value(rows, "beta");
  assert.equal(row.kind === "value" && row.value, false);
});

test("a configured secret reads Configured and an empty slot reads Not set", () => {
  const configured = secretRowsOf(
    buildSettings(fakeFacade(DEFS), new Map([["apiKey", { ref: OPENAI, configured: true }]])),
  );
  const missing = secretRowsOf(
    buildSettings(fakeFacade(DEFS), new Map([["apiKey", { ref: OPENAI, configured: false }]])),
  );
  assert.equal(configured[0]?.presence, CONFIGURED);
  assert.equal(configured[0]?.state, "configured");
  assert.equal(missing[0]?.presence, NOT_SET);
  assert.equal(missing[0]?.state, "not-set");
});

test("a presence check that has not come back is unknown, not Not set", () => {
  // `hasSecret` is async and the first paint is not. Rendering the gap as "Not
  // set" tells someone their key is missing while it is sitting in the
  // keychain, and the obvious response is to paste it in again.
  const rows = secretRowsOf(buildSettings(fakeFacade(DEFS)));
  assert.equal(rows[0]?.state, "unknown");
  assert.equal(rows[0]?.presence, UNKNOWN);
  assert.notEqual(rows[0]?.presence, NOT_SET);
});

test("a software-only keychain is surfaced as a warning row", () => {
  // ports/secrets.ts: the view "shows an explicit warning when this is false
  // rather than implying a safety the platform is not providing". Nothing else
  // in the package can keep that promise.
  const view = buildSettings(fakeFacade(DEFS, {}, false));
  assert.equal(view.warnings.length, 1);
  assert.equal(view.warnings[0]?.kind, "warning");
  assert.equal(view.warnings[0]?.text, SOFTWARE_SECRETS_WARNING);
  assert.equal(view.secretsAreHardwareBacked, false);
});

test("no warning is shown when secrets really are hardware backed", () => {
  // The pair: a screen that always warns is a screen whose warning means
  // nothing, and the iOS keychain would be libelled on every launch.
  assert.deepEqual(buildSettings(fakeFacade(DEFS, {}, true)).warnings, []);
});

test("a label falls back to the key and help is carried through", () => {
  // A row with no label has no hit target and no meaning; `maxTokens` is ugly
  // but at least says which setting it is.
  assert.equal(labelOf({ key: "maxTokens", default: 1 }), "maxTokens");
  assert.equal(labelOf({ key: "maxTokens", default: 1, label: "  " }), "maxTokens");
  const rows = rowsOf(buildSettings(fakeFacade(DEFS)));
  assert.equal(value(rows, "temperature").help, "Higher is more random.");
  assert.equal(value(rows, "model").help, null);
});

test("two defs sharing a key produce one row, so no two rows share an id", () => {
  // render/reconcile.ts keys on the row id: "two rows sharing an id is how a
  // keyed renderer paints one row's content into another's node".
  const defs: readonly SettingDef[] = [
    { key: "model", default: "a" },
    { key: "model", default: "b" },
  ];
  const rows = rowsOf(buildSettings(fakeFacade(defs)));
  assert.equal(rows.length, 1);
  assert.equal(rows[0]?.value, "a");
});

test("every row id in the whole view is unique", () => {
  const rows = rowsOf(buildSettings(fakeFacade(DEFS)));
  assert.equal(new Set(rows.map((r) => r.id)).size, rows.length);
});

test("an emptied number field is refused rather than stored as zero", () => {
  // Number("") is 0, not NaN. A max-tokens of 0 that the user never typed is a
  // setting that breaks every request with no visible cause.
  const def: SettingDef = { key: "temperature", default: 0.7 };
  assert.equal(validateInput(def, ""), null);
  assert.equal(validateInput(def, "   "), null);
  assert.equal(validateInput(def, "abc"), null);
  assert.equal(validateInput(def, "Infinity"), null);
});

test("a well-formed number is accepted", () => {
  // The pair: a validator that refuses everything makes the field read-only
  // while looking perfectly editable.
  assert.equal(validateInput({ key: "temperature", default: 0.7 }, " 1.5 "), 1.5);
});

test("the def's own validate runs after parsing, so an out-of-range value is refused", () => {
  // Otherwise the screen offers a value that `set` then silently returns false
  // for, which reads to the user as a setting that will not stick.
  const def: SettingDef = { key: "temperature", default: 0.7, validate: clampNum(0, 2) };
  assert.equal(validateInput(def, "9"), 2);
  assert.equal(validateInput(def, "-4"), 0);
});

test("a value outside a def's closed set is refused, and one inside it is returned as itself", () => {
  // A picker that can smuggle a free value is a picker in name only; the wrong
  // model name fails later, at request time, as a provider error.
  const def: SettingDef = { key: "model", default: "gpt-4o-mini", choices: ["gpt-4o-mini", "gpt-4o"] };
  assert.equal(validateInput(def, "gpt-5-turbo"), null);
  assert.equal(validateInput(def, " gpt-4o "), "gpt-4o");
});

test("a numeric choice comes back as a number rather than as its typed text", () => {
  // Storing "2" where the engine expects 2 is a setting that is present,
  // accepted and ignored.
  const def: SettingDef = { key: "n", default: 1, choices: [1, 2, 4] };
  assert.equal(validateInput(def, "2"), 2);
});

test("a boolean field parses the words it renders and refuses anything else", () => {
  const def: SettingDef = { key: "showReasoning", default: false };
  assert.equal(validateInput(def, "true"), true);
  assert.equal(validateInput(def, "  FALSE "), false);
  assert.equal(validateInput(def, "maybe"), null);
});

test("a secret is refused by the text-field path entirely", () => {
  // It goes to setSecret. A SettingValue coming back from here is the first
  // step of the journey that ends with an API key in the settings file --
  // engine/server.py:653, the failure the whole split was written against.
  assert.equal(validateInput({ key: "apiKey", default: "", secret: true }, "sk-live"), null);
});

test("the software-secrets warning says where the key really is", () => {
  // The message was rewritten when the Tauri build got a real keychain: it used
  // to say secrets were "stored in app memory on this platform", which was
  // shown on a PHONE as well, because the phone really was using app memory.
  // Now the only reader is a browser, and the two facts that reader needs are
  // that the key goes no further than the tab and that it will not be there
  // next time. Pinned as behaviour rather than as a string equality, so a
  // rewording that keeps the meaning passes and one that drops it does not.
  const text = SOFTWARE_SECRETS_WARNING;
  assert.match(text, /browser|tab/i, "the message must name where the key is");
  assert.match(text, /again|not saved|only/i, "the message must say the key does not persist");
  assert.doesNotMatch(
    text,
    /\bin a hardware-backed keychain\b(?!\.)/i,
    "the message must not imply a keychain the browser does not have",
  );
  // The old sentence, refused by name. It is accurate on the web and was ALSO
  // being shown on a device, which is the state this change ended.
  assert.doesNotMatch(text, /on this platform/i, "there is only one platform that shows this now");
});

// ---- rule 5: a control that cannot do anything says so ----------------------
//
// Two of these shipped on the same screen. `Remove` sat under a row reading
// "Not set", and `Engine address` rendered identically whether or not an engine
// that reads it was selected -- while its own help text said "Only used by the
// remote engine". Both answers are computed here rather than in the renderer,
// so a second renderer cannot get a different one and a test does not need a
// DOM to ask.

test("Remove is offered only when there is a key to remove", () => {
  // The defect, exactly: the button was unconditional, so a user with no key
  // was offered a control that destroys nothing and reports nothing. It is the
  // defect class this package spent two days eliminating, in the screen that
  // introduced it.
  const configured: SecretPresence = new Map([["apiKey", { ref: OPENAI, configured: true }]]);
  const missing: SecretPresence = new Map([["apiKey", { ref: OPENAI, configured: false }]]);

  const withKey = secretRowsOf(buildSettings(fakeFacade(DEFS), configured))[0];
  const withoutKey = secretRowsOf(buildSettings(fakeFacade(DEFS), missing))[0];

  assert.equal(withKey?.canClear, true, "a stored key must be removable");
  assert.equal(withoutKey?.canClear, false, "there is nothing to remove");
  // And the presence word and the button agree. Two sources for one fact is
  // how a row comes to say "Not set" with a live Remove under it.
  assert.equal(withoutKey?.presence, NOT_SET);
});

test("a key whose lookup has not landed offers no Remove either -- the pair", () => {
  // `canClear` is `state === "configured"`, not `state !== "not-set"`. UNKNOWN
  // is a keychain check still in flight (rule 2), and offering to destroy a
  // credential the app has not confirmed exists is the same false promise
  // pointed the other way -- and the state EVERY row is in on first paint.
  const row = secretRowsOf(buildSettings(fakeFacade(DEFS)))[0];
  assert.equal(row?.presence, UNKNOWN);
  assert.equal(row?.canClear, false, "an unresolved lookup must not offer Remove");
});

const DEPENDENT: readonly SettingDef[] = [
  { key: "engineId", default: "remote-http", label: "Engine", section: "Engine", choices: ["remote-http", "praisonai-ts"] },
  {
    key: "baseUrl",
    default: "http://127.0.0.1:8765",
    label: "Engine address",
    section: "Engine",
    appliesWhen: { key: "engineId", equals: "remote-http" },
  },
];

test("a setting whose switch is off does not apply, and names the switch", () => {
  const rows = rowsOf(buildSettings(fakeFacade(DEPENDENT, { engineId: "praisonai-ts" })));
  const row = value(rows, "baseUrl");
  assert.equal(row.kind, "value");
  assert.equal(row.kind === "value" && row.applies, false, "nothing reads it under this engine");
  // The LABEL of the controlling setting, not its key: a user sent hunting for
  // `engineId` on a screen that only ever says "Engine" has been sent nowhere.
  assert.deepEqual(row.kind === "value" ? row.inactiveBecause : null, {
    label: "Engine",
    value: "remote-http",
  });
});

test("the same setting applies once its switch is on -- the pair", () => {
  // Without this, a row hard-wired to `applies: false` would satisfy the test
  // above and the address would be permanently uneditable -- which is the
  // recovery path a phone depends on (#4694).
  const rows = rowsOf(buildSettings(fakeFacade(DEPENDENT, { engineId: "remote-http" })));
  const row = value(rows, "baseUrl");
  assert.equal(row.kind === "value" && row.applies, true);
  assert.equal(row.kind === "value" ? row.inactiveBecause : "x", null);
});

test("a setting with no dependency always applies", () => {
  // Nearly every def. A default of `applies: false` would switch the whole
  // screen off at once.
  for (const row of rowsOf(buildSettings(fakeFacade(DEFS)))) {
    if (row.kind !== "value") continue;
    assert.equal(row.applies, true, `${row.key} has no dependency and must apply`);
  }
});

test("a dependency the DEFAULT already satisfies applies before anyone touches it", () => {
  // Read through `get` and not `isSet`: a def's default is a live value -- the
  // engine really is remote-http on first launch -- so asking whether the
  // controlling setting had been CHANGED would report the address inactive on
  // a screen where it is the only thing that works.
  const rows = rowsOf(buildSettings(fakeFacade(DEPENDENT)));
  assert.equal(value(rows, "baseUrl").kind === "value", true);
  const row = value(rows, "baseUrl");
  assert.equal(row.kind === "value" && row.applies, true, "the default engine is the remote one");
});
