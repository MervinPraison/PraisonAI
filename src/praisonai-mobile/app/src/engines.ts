/**
 * Which engine the app runs, and the check that a swap is actually safe.
 *
 * This is the only file that knows more than one engine exists. Everything
 * above the seam takes an `AgentEnginePort` and cannot tell them apart, which
 * is the property the whole engines/ arrangement is for.
 *
 * The protocol check happens HERE, at composition, and it is the reason this
 * file is not just a switch statement. An engine speaking a different event
 * vocabulary must be a boot failure with a name attached -- not an unknown
 * event arriving halfway through someone's first answer, by which point there
 * is text on screen and no honest way to explain what went wrong.
 */
import type { AgentEnginePort } from "../../core/src/ports/agent-engine.ts";
import { PROTOCOL_VERSION, checkProtocol } from "../../protocol/src/version.ts";

export interface EngineChoice {
  readonly id: string;
  /** Built lazily: constructing an engine can open sockets and read secrets,
   *  and the app builds exactly one. */
  readonly create: () => AgentEnginePort | Promise<AgentEnginePort>;
}

export type EngineSelection =
  | { readonly ok: true; readonly engine: AgentEnginePort }
  | { readonly ok: false; readonly reason: "unknown_engine" | "protocol_mismatch"; readonly detail: string };

/**
 * Pick an engine by id and verify it before handing it over.
 *
 * Returns a result rather than throwing: an unusable engine should land the
 * user on a settings screen that says which one and why, not on a crash
 * handler. Both failures are recoverable by changing a setting.
 */
export async function selectEngine(
  id: string,
  choices: readonly EngineChoice[],
): Promise<EngineSelection> {
  const choice = choices.find((c) => c.id === id);
  if (choice === undefined) {
    return {
      ok: false,
      reason: "unknown_engine",
      detail: `no engine "${id}"; available: ${choices.map((c) => c.id).join(", ") || "(none)"}`,
    };
  }

  const engine = await choice.create();

  const verdict = checkProtocol(engine.protocolVersion);
  if (!verdict.ok) {
    // Dispose what we just built. An engine left holding a socket because its
    // version check failed is a leak that only shows up as a second failure.
    await engine.dispose();
    return {
      ok: false,
      reason: "protocol_mismatch",
      detail: `engine "${id}" speaks protocol ${engine.protocolVersion}, this build speaks ${PROTOCOL_VERSION}`,
    };
  }

  if (engine.id !== id) {
    // Not fatal, but worth refusing: chats record engine.id, so a factory
    // registered under one id returning another writes transcripts that
    // attribute themselves to an engine the user never selected.
    await engine.dispose();
    return {
      ok: false,
      reason: "unknown_engine",
      detail: `engine registered as "${id}" reports its id as "${engine.id}"`,
    };
  }

  return { ok: true, engine };
}
