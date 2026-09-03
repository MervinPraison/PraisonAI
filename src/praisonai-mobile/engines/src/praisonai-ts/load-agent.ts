/**
 * The one place `praisonai` is named, and the seam that makes it a CHUNK.
 *
 * The specifier is a LITERAL. That is the whole trick: esbuild can only put a
 * module in its own lazily-fetched chunk if it can see which module it is, and
 * a runtime-computed path (what this used to be) is opaque to the bundler --
 * so the engine either came along eagerly or, as external, not at all.
 *
 * It lives HERE rather than in `app/src/main.ts` because `tools/boundaries.json`
 * says only `engines/src/praisonai-ts` may import `praisonai`. That rule is the
 * agent-framework seam; making the import literal must not cost it.
 *
 * `praisonai/mobile` -- not `praisonai` -- is the package's webview-safe
 * allowlist entry. The default entry re-exports the CLI, the MCP server and the
 * knowledge store, whose Node builtins are import-time fatal in a webview.
 */
import type { PraisonAgent } from "./agent-api.ts";

/** The one member of praisonai's `Agent` constructor this seam uses. */
export interface PraisonAgentModule {
  new (config: { instructions: string; llm?: string }): PraisonAgent;
}

/**
 * Load the upstream `Agent` class, on demand.
 *
 * The import can REJECT -- a chunk that fails to fetch on a flaky connection,
 * or a build where the engine was left out. Left unwrapped that surfaces as an
 * opaque module error from inside the run loop; re-thrown as a plain Error,
 * `engine.ts` turns it into a recoverable `error` event through its existing
 * catch, which is the named on-screen failure the picker's contract requires.
 */
export async function loadPraisonAgent(): Promise<PraisonAgentModule> {
  try {
    const mod = (await import("praisonai/mobile")) as unknown as { Agent: PraisonAgentModule };
    return mod.Agent;
  } catch (cause) {
    throw new Error(
      "the in-process engine is unavailable in this build: praisonai could not be loaded",
      { cause },
    );
  }
}
