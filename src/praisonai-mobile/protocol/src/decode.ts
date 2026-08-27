/**
 * Turn whatever arrived into a typed event, or into an explained no-op.
 *
 * There is a deliberate asymmetry with the engine here, and it looks like a
 * contradiction until you notice which side is last. engine/server.py:1152 says
 * of unrecognised *library* output:
 *
 *   "Unrecognised shapes become text rather than being dropped: a client that
 *    renders an unexpected object badly is recoverable, one that silently
 *    discards it is not."
 *
 * That is right for the engine, which is the last place that can preserve the
 * content. It is wrong for the wire. Here an unrecognised event NAME is a
 * no-op, because a client cannot render a shape it has no code for, and a throw
 * mid-stream kills a live answer that was otherwise fine. Unknown-is-ignored is
 * also the mechanism that makes additive versioning safe.
 *
 * decodeEvent NEVER throws. Every rejection is a value with a reason, so a
 * client can count them and a test can assert on them.
 */
import {
  ERROR_KINDS,
  type ApprovalChoice,
  type ErrorKind,
  type RunEvent,
} from "./events.ts";

export type IgnoredReason =
  | "unparseable_json"
  | "not_an_object"
  | "missing_type"
  | "unknown_event"
  | "missing_msg_id"
  | "missing_required_field"
  | "empty_text";

export interface DecodedOk {
  readonly kind: "event";
  readonly event: RunEvent;
}

export interface DecodedIgnored {
  readonly kind: "ignored";
  readonly reason: IgnoredReason;
  /** Enough to debug from a log line, never the whole payload. */
  readonly detail: string;
}

export type Decoded = DecodedOk | DecodedIgnored;

export function isDecoded(outcome: Decoded): outcome is DecodedOk {
  return outcome.kind === "event";
}

export function isIgnored(outcome: Decoded): outcome is DecodedIgnored {
  return outcome.kind === "ignored";
}

const ignore = (reason: IgnoredReason, detail: string): DecodedIgnored => ({
  kind: "ignored",
  reason,
  detail,
});

const asString = (v: unknown): string | null => (typeof v === "string" ? v : null);

const asNumber = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;

/**
 * Absent and null are different answers, and collapsing them is the bug this
 * whole file exists to prevent. `undefined` means the key was not there at all.
 */
const asNullableNumber = (
  o: Record<string, unknown>,
  key: string,
): number | null | undefined => {
  if (!(key in o)) return undefined;
  const v = o[key];
  if (v === null) return null;
  return asNumber(v);
};

const asArgs = (v: unknown): Readonly<Record<string, unknown>> =>
  v !== null && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : {};

/** Truncated so one enormous frame cannot fill a log or a crash report. */
const brief = (v: unknown): string => {
  try {
    const s = typeof v === "string" ? v : JSON.stringify(v);
    return (s ?? String(v)).slice(0, 120);
  } catch {
    // A circular object cannot be stringified. That is not a reason to throw.
    return Object.prototype.toString.call(v);
  }
};

export function decodeEvent(raw: unknown): Decoded {
  let value: unknown = raw;

  if (typeof raw === "string") {
    try {
      value = JSON.parse(raw);
    } catch {
      return ignore("unparseable_json", brief(raw));
    }
  }

  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return ignore("not_an_object", typeof value);
  }

  const o = value as Record<string, unknown>;

  const type = asString(o["type"]);
  if (type === null || type === "") return ignore("missing_type", brief(Object.keys(o)));

  const msgId = asString(o["msg_id"]);
  if (msgId === null || msgId === "") return ignore("missing_msg_id", type);

  const need = (field: string): DecodedIgnored =>
    ignore("missing_required_field", `${type}.${field}`);

  const ok = (event: RunEvent): DecodedOk => ({ kind: "event", event });

  switch (type) {
    case "start": {
      const runId = asString(o["run_id"]);
      if (runId === null) return need("run_id");
      return ok({ type: "start", msgId, runId });
    }

    case "delta":
    case "reasoning": {
      const text = asString(o["text"]);
      if (text === null) return need("text");
      // Neither an error nor renderable. Dropping it here keeps "a turn with no
      // delta is empty" a meaningful check further up.
      if (text === "") return ignore("empty_text", type);
      return ok({ type, msgId, text });
    }

    case "tool_drafting": {
      const name = asString(o["name"]);
      if (name === null) return need("name");
      return ok({ type: "tool_drafting", msgId, name });
    }

    case "tool_call": {
      const callId = asString(o["call_id"]);
      const name = asString(o["name"]);
      if (callId === null || callId === "") return need("call_id");
      if (name === null) return need("name");
      return ok({ type: "tool_call", msgId, callId, name, args: asArgs(o["args"]) });
    }

    case "tool_result": {
      const callId = asString(o["call_id"]);
      const name = asString(o["name"]);
      if (callId === null || callId === "") return need("call_id");
      if (name === null) return need("name");
      // NOT defaulted to true. The engine may coerce at its own boundary
      // because it is normalising a library's shape; we are reading a contract.
      // A missing `ok` read as success is precisely "a tool call that silently
      // failed still looks like a normal answer".
      if (typeof o["ok"] !== "boolean") return need("ok");
      const seconds = asNullableNumber(o, "seconds");
      return ok({
        type: "tool_result",
        msgId,
        callId,
        name,
        ok: o["ok"],
        output: asString(o["output"]) ?? "",
        seconds: seconds === undefined ? null : seconds,
      });
    }

    case "approval_request": {
      const approvalId = asString(o["approval_id"]);
      const callId = asString(o["call_id"]);
      const name = asString(o["name"]);
      if (approvalId === null || approvalId === "") return need("approval_id");
      if (callId === null || callId === "") return need("call_id");
      if (name === null) return need("name");
      return ok({
        type: "approval_request",
        msgId,
        approvalId,
        callId,
        name,
        args: asArgs(o["args"]),
      });
    }

    case "usage": {
      const chars = asNumber(o["chars"]);
      const seconds = asNumber(o["seconds"]);
      if (chars === null) return need("chars");
      if (seconds === null) return need("seconds");
      const ttft = asNullableNumber(o, "ttft"); // wire key, snake_case
      return ok({
        type: "usage",
        msgId,
        chars,
        seconds,
        ttftSeconds: ttft === undefined ? null : ttft,
      });
    }

    case "cancelled": {
      const runId = asString(o["run_id"]);
      if (runId === null) return need("run_id");
      return ok({ type: "cancelled", msgId, runId });
    }

    case "error": {
      const message = asString(o["message"]);
      if (message === null) return need("message");
      const rawKind = asString(o["kind"]);
      // Degrade, do not drop. We may not recognise a newer engine's taxonomy
      // entry, but the human still has to be able to read what went wrong.
      const kind: ErrorKind =
        rawKind !== null && (ERROR_KINDS as readonly string[]).includes(rawKind)
          ? (rawKind as ErrorKind)
          : "internal";
      return ok({ type: "error", msgId, kind, message });
    }

    case "end": {
      // null here is a real, load-bearing value: the turn is on screen but not
      // on disk. Absent is a different thing, and 0 is a third.
      const userIndex = asNullableNumber(o, "user_index");
      if (userIndex === undefined) return need("user_index");
      const assistantIndex = asNullableNumber(o, "assistant_index");
      const versions = asNumber(o["versions"]) ?? 1;
      const active = asNumber(o["active"]) ?? 0;
      return ok({
        type: "end",
        msgId,
        userIndex,
        assistantIndex:
          assistantIndex === undefined
            ? userIndex === null
              ? null
              : userIndex + 1
            : assistantIndex,
        versions: Math.max(1, versions),
        active: Math.min(Math.max(0, active), Math.max(1, versions) - 1),
      });
    }

    default:
      return ignore("unknown_event", type);
  }
}

/** The reverse channel. Not an event -- it travels up, while events travel down. */
export function decodeApprovalChoice(raw: unknown): ApprovalChoice | null {
  return raw === "allow" || raw === "always" || raw === "deny" ? raw : null;
}
