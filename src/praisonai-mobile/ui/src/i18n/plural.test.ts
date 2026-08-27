/**
 * Plural selection.
 *
 * The guarantee: the form is chosen by CLDR category, so a locale with more
 * than two forms gets the right one. The bug being pinned is the ternary that
 * ships in app/src/dom.ts today --
 *
 *     `event${row.count === 1 ? "" : "s"}`
 *
 * -- which is correct English and wrong in most of the languages the app would
 * be translated into.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { countedPhrase, pluralCategory, selectPlural, type PluralForms } from "./plural.ts";

const PL: PluralForms = {
  one: "{n} wydarzenie",
  few: "{n} wydarzenia",
  many: "{n} wydarzeń",
  other: "{n} wydarzenia",
};

test("Polish picks three different forms where the English ternary picks two", () => {
  // THE BUG. `n === 1 ? "" : "s"` gives 2, 5 and 22 the same word. Polish gives
  // them three: 2 is `few`, 5 is `many`, 22 is `few` again.
  assert.equal(pluralCategory("pl", 1), "one");
  assert.equal(pluralCategory("pl", 2), "few");
  assert.equal(pluralCategory("pl", 5), "many");
  assert.equal(pluralCategory("pl", 22), "few");
  assert.equal(countedPhrase("pl", 5, "5", PL), "5 wydarzeń");
  assert.notEqual(countedPhrase("pl", 2, "2", PL), countedPhrase("pl", 5, "5", PL));
});

test("a language with one form and a language with six are both handled", () => {
  // Japanese has no plural at all, so an appended "s" is pure noise. Welsh has
  // six categories, which no ternary can reach.
  assert.equal(pluralCategory("ja", 1), "other");
  assert.equal(pluralCategory("ja", 7), "other");
  assert.deepEqual(
    [0, 1, 2, 3, 6, 7].map((n) => pluralCategory("cy", n)),
    ["zero", "one", "two", "few", "many", "other"],
  );
  // Arabic has a category for zero specifically -- "no events" is a different
  // word, not the plural with a 0 in front of it.
  assert.equal(pluralCategory("ar", 0), "zero");
  assert.equal(pluralCategory("ar", 2), "two");
});

test("English still gets English right", () => {
  // The pair: an implementation that always returned "other" would satisfy the
  // Japanese assertions above and quietly print "1 events" for every user.
  assert.equal(pluralCategory("en", 1), "one");
  assert.equal(pluralCategory("en", 0), "other");
  assert.equal(pluralCategory("en", 2), "other");
  assert.equal(
    countedPhrase("en", 1, "1", { one: "{n} event", other: "{n} events" }),
    "1 event",
  );
});

test("a category the translation did not supply falls back instead of blanking", () => {
  // A translator who supplied only `one` and `other` for Polish is normal and
  // incomplete. Selecting `few` and finding undefined would paint "undefined"
  // or an empty label; the chain lands on a real word.
  const partial: PluralForms = { one: "{n} plik", other: "{n} plików" };
  assert.equal(selectPlural("pl", 2, partial), "{n} plików");
  assert.equal(selectPlural("pl", 1, partial), "{n} plik");
});

test("a non-finite count and an unusable locale both answer instead of throwing", () => {
  // usage.chars arrives from the wire and NaN has reached a formatter in this
  // package before; a bad locale tag arrives from stored settings.
  assert.equal(pluralCategory("en", Number.NaN), "other");
  assert.doesNotThrow(() => pluralCategory("!!", 3));
  assert.equal(selectPlural("!!", 3, { one: "one", other: "many" }), "many");
});

test("the category comes from the number and the text comes from the string", () => {
  // Formatting is locale work that happens elsewhere: "٥" is five in Arabic
  // digits, and selection must still see the numeric 5.
  assert.equal(countedPhrase("pl", 5, "٥", PL), "٥ wydarzeń");
});
