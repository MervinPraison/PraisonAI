/**
 * The inverse of decode.ts: a typed event back onto the wire shape.
 *
 * Not used in production -- the app only ever reads events. It exists so the
 * round-trip test can exercise every branch of the decoder from the type side,
 * and so fakes and fixtures can produce genuine frames instead of hand-written
 * object literals that drift from the contract.
 *
 * Keeping it beside the decoder is deliberate: a field renamed in one and not
 * the other fails the round-trip immediately, which is the cheapest possible
 * place to notice.
 */
import type { RunEvent } from "./events.ts";

/** camelCase in the type system, snake_case on the wire. This is the only
 *  place in the package that knows both conventions. */
export function encodeEvent(event: RunEvent): Record<string, unknown> {
  const base = { type: event.type, msg_id: event.msgId };

  switch (event.type) {
    case "start":
      return { ...base, run_id: event.runId };
    case "delta":
    case "reasoning":
      return { ...base, text: event.text };
    case "tool_drafting":
      return { ...base, name: event.name };
    case "tool_call":
      return { ...base, call_id: event.callId, name: event.name, args: event.args };
    case "tool_result":
      return {
        ...base,
        call_id: event.callId,
        name: event.name,
        ok: event.ok,
        output: event.output,
        seconds: event.seconds,
      };
    case "approval_request":
      return {
        ...base,
        approval_id: event.approvalId,
        call_id: event.callId,
        name: event.name,
        args: event.args,
      };
    case "usage":
      return { ...base, chars: event.chars, seconds: event.seconds, ttft: event.ttftSeconds };
    case "cancelled":
      return { ...base, run_id: event.runId };
    case "error":
      return { ...base, kind: event.kind, message: event.message };
    case "end":
      return {
        ...base,
        user_index: event.userIndex,
        assistant_index: event.assistantIndex,
        versions: event.versions,
        active: event.active,
      };
  }
}

/** An SSE frame as the desktop engine writes it: `event:` line, `data:` line,
 *  blank line. Used by the remote-http engine's fixtures. */
export function encodeSseFrame(event: RunEvent): string {
  const payload = encodeEvent(event);
  delete payload["type"];
  return `event: ${event.type}\ndata: ${JSON.stringify(payload)}\n\n`;
}
