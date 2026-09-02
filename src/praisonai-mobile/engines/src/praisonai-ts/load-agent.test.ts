/**
 * The seam that turns `praisonai` into a chunk, exercised for real.
 *
 * `load-agent.ts` is the one place the package name is a literal, and the
 * whole split rests on that literal resolving to a module with an `Agent` in
 * it. `tools/app-bundle.test.mjs` proves esbuild can see it; this proves Node
 * can load it, which is the same claim from the other side -- a typo in the
 * specifier, or an upstream release that stops exporting `Agent` from
 * `praisonai/mobile`, fails here with the name in the message rather than on a
 * device as "the in-process engine is unavailable in this build".
 */
import test from "node:test";
import assert from "node:assert/strict";

import { loadPraisonAgent } from "./load-agent.ts";

test("praisonai/mobile resolves and exports a constructible Agent", async () => {
  const Agent = await loadPraisonAgent();
  assert.equal(typeof Agent, "function", "Agent must be a class, not a namespace");
  // Constructing opens no upstream: the model is only contacted on a turn.
  const agent = new Agent({ instructions: "test", llm: "gpt-4o-mini" });
  assert.equal(typeof agent.streamEvents, "function", "and the instance must speak agent-api.ts");
});
