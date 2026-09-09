/**
 * Per-tool guardrails: validate the arguments and the result of ONE tool.
 *
 * Python parity: praisonaiagents/guardrails/tool_guardrails.py
 *
 * praisonai-ts already had guardrails at two scopes and nothing in between:
 * whole-run output validation, and an agent-wide tool surface that fires for
 * every tool the agent can reach. Neither lets a tool author say "*this one*
 * tool must never be called with a recipient outside the company domain".
 * This module adds the missing scope, declared on the tool itself next to
 * `approval` and `restartSafe`:
 *
 * ```ts
 * const sendEmail = tool({
 *   name: 'send_email',
 *   inputGuardrails: [(args: any) =>
 *     String(args.to ?? '').endsWith('@corp.com')
 *       ? [true, args]
 *       : [false, 'Recipient is outside the company domain.']],
 *   execute: async ({ to, body }) => { ... },
 * });
 * ```
 *
 * The guardrail fires on every invocation of `send_email` and never for any
 * other tool.
 *
 * ## What a guardrail receives and returns
 *
 * An **input** guardrail takes the arguments object the model proposed. An
 * **output** guardrail takes the raw result the tool returned. Both use the
 * `[success, value]` convention already used across this package:
 *
 * - `[true, value]` — allow; `value` replaces the arguments/result, so a
 *   guardrail can **rewrite** (sanitise arguments, redact a secret out of a
 *   result). `[true, null]` allows the original through unchanged.
 * - `[false, 'reason']` — block. The reason is handed back to the **model** as
 *   the tool result so it can react; it is never thrown at the user.
 * - A bare `true` / `false` works too, as does a `GuardrailValidationResult`.
 * - `undefined` / `null` means "no opinion" — allow unchanged. The deny path is
 *   explicit, so nothing is lost by being permissive here.
 * - Anything else is a contract violation and **fails closed**: an unreadable
 *   verdict is not an approval.
 *
 * A guardrail that throws also fails closed.
 */

import type { GuardrailValidationResult } from './index';

/** An input guardrail gates the arguments before dispatch. */
export const INPUT = 'input' as const;
/** An output guardrail gates the raw result before it re-enters the LLM context. */
export const OUTPUT = 'output' as const;

export type GuardrailDirection = typeof INPUT | typeof OUTPUT;

/**
 * The protocol method each direction drives. Per-tool guardrails deliberately
 * speak the SAME protocol as agent-wide ones so a guardrail written for one
 * scope drops into the other with no adaptation.
 */
export const METHOD_FOR: Record<GuardrailDirection, string> = {
  [INPUT]: 'validateToolCall',
  [OUTPUT]: 'validateToolResult',
};

const DEFAULT_REASON: Record<GuardrailDirection, string> = {
  [INPUT]: 'rejected by an input guardrail',
  [OUTPUT]: 'rejected by an output guardrail',
};

/** Attribute a tool declares its guardrails on, per direction. */
export const ATTR_FOR: Record<GuardrailDirection, string> = {
  [INPUT]: 'inputGuardrails',
  [OUTPUT]: 'outputGuardrails',
};

/** `[ok, valueOrReason]` — the shape every guardrail method returns. */
export type GuardrailVerdict = [boolean, any];

/** Anything a user may pass as a single guardrail entry. */
export type ToolGuardrailSpec = ((value: any) => any) | ToolGuardrailLike;

/** An object already speaking the guardrail protocol. */
export interface ToolGuardrailLike {
  name?: string;
  validateToolCall?(toolName: string, args: any): GuardrailVerdict;
  validateToolResult?(toolName: string, result: any): GuardrailVerdict;
}

/**
 * The model-facing value returned when a guardrail blocks. Python returns the
 * equivalent dict rather than raising: a blocked call is a normal, expected
 * policy outcome, and throwing would abort the run and surface a stack trace
 * for it. Handing the reason back lets the model pick different arguments,
 * choose another tool, or explain to the user.
 */
export interface ToolGuardrailDenial {
  error: string;
  guardrail_denied: true;
  tool_guardrail: GuardrailDirection;
}

/** True when a tool result is a guardrail denial rather than real output. */
export function isToolGuardrailDenial(value: any): value is ToolGuardrailDenial {
  return Boolean(value) && typeof value === 'object' && value.guardrail_denied === true;
}

function isGuardrailValidationResult(value: any): value is GuardrailValidationResult {
  return (
    Boolean(value) &&
    typeof value === 'object' &&
    !Array.isArray(value) &&
    typeof value.success === 'boolean'
  );
}

/**
 * Normalise a user guardrail's return value into `[ok, value, reason]`.
 *
 * Accepts every shape documented above. Unknown shapes fail closed — a verdict
 * we cannot read must not be treated as an approval.
 */
export function interpretGuardrailOutcome(
  outcome: any,
  original: any,
  defaultReason: string,
): [boolean, any, string] {
  if (outcome === undefined || outcome === null) {
    // "No opinion": a validator that objects explicitly (returns false or
    // throws) and simply falls off the end on the happy path.
    return [true, original, ''];
  }

  if (typeof outcome === 'boolean') {
    return outcome ? [true, original, ''] : [false, original, defaultReason];
  }

  if (Array.isArray(outcome) && outcome.length === 2) {
    const [ok, data] = outcome;
    if (ok) {
      // `null`/`undefined` means "unchanged" — keep the caller's value rather
      // than replacing it with nothing.
      return [true, data === undefined || data === null ? original : data, ''];
    }
    return [false, original, data ? String(data) : defaultReason];
  }

  if (isGuardrailValidationResult(outcome)) {
    if (outcome.success) {
      return [true, outcome.result === undefined || outcome.result === null ? original : outcome.result, ''];
    }
    return [false, original, outcome.error || defaultReason];
  }

  return [
    false,
    original,
    `guardrail returned ${Array.isArray(outcome) ? 'array' : typeof outcome}; ` +
      'expected [boolean, value], a boolean, a GuardrailValidationResult, or null',
  ];
}

/**
 * Adapts a plain `fn(value) => [ok, value]` into the guardrail protocol.
 *
 * Keeping the adapter protocol-shaped (rather than special-casing functions in
 * the executor) is what lets per-tool and agent-wide guardrails share one chain
 * implementation and one call path.
 */
abstract class CallableToolGuardrail implements ToolGuardrailLike {
  /**
   * Set by the subclass THROUGH the constructor, not as a field initializer:
   * subclass field initializers run after `super()`, so a `readonly direction =
   * INPUT` field would still be undefined in here.
   */
  readonly direction: GuardrailDirection;
  readonly name: string;
  protected readonly fn: (value: any) => any;

  constructor(direction: GuardrailDirection, fn: (value: any) => any, name?: string) {
    this.direction = direction;
    if (typeof fn !== 'function') {
      throw new TypeError(
        `A tool guardrail must be a function or expose ` +
          `${METHOD_FOR[direction]}(); got ${typeof fn}.`,
      );
    }
    this.fn = fn;
    this.name = name || fn.name || 'anonymous';
  }

  protected run(value: any): [boolean, any, string] {
    return interpretGuardrailOutcome(this.fn(value), value, DEFAULT_REASON[this.direction]);
  }
}

/**
 * Gates a single tool's arguments before the tool runs.
 *
 * A rewrite must still be an object of keyword arguments — returning anything
 * else is treated as a contract violation and blocks, because handing a
 * non-object to the tool would throw inside user code instead of producing a
 * message the model can act on.
 */
export class ToolInputGuardrail extends CallableToolGuardrail {
  constructor(fn: (value: any) => any, name?: string) {
    super(INPUT, fn, name);
  }

  validateToolCall(toolName: string, args: any): GuardrailVerdict {
    const [ok, value, reason] = this.run(args);
    if (!ok) return [false, reason];
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return [
        false,
        `input guardrail '${this.name}' rewrote the arguments to ` +
          `${Array.isArray(value) ? 'array' : typeof value}; expected an object of keyword arguments`,
      ];
    }
    return [true, value];
  }
}

/** Gates a single tool's raw result before it re-enters the LLM context. */
export class ToolOutputGuardrail extends CallableToolGuardrail {
  constructor(fn: (value: any) => any, name?: string) {
    super(OUTPUT, fn, name);
  }

  validateToolResult(toolName: string, result: any): GuardrailVerdict {
    const [ok, value, reason] = this.run(result);
    if (!ok) return [false, reason];
    return [true, value];
  }
}

/**
 * Runs guardrails in order, short-circuiting on the first failure and
 * reporting *why* a tool call was rejected.
 *
 * Each guardrail's allowed value feeds the next, so a chain can sanitise in
 * stages. A guardrail that throws fails closed unless `failOpen` is set.
 */
export class ToolGuardrailChain {
  readonly guardrails: ToolGuardrailLike[];
  readonly failOpen: boolean;
  readonly direction: GuardrailDirection;

  constructor(
    guardrails: ToolGuardrailLike[],
    options: { failOpen?: boolean; direction?: GuardrailDirection } = {},
  ) {
    this.guardrails = guardrails;
    this.failOpen = options.failOpen ?? false;
    this.direction = options.direction ?? INPUT;
  }

  validateToolCall(toolName: string, args: any): GuardrailVerdict {
    return this.runDirection(INPUT, toolName, args);
  }

  validateToolResult(toolName: string, result: any): GuardrailVerdict {
    return this.runDirection(OUTPUT, toolName, result);
  }

  private runDirection(
    direction: GuardrailDirection,
    toolName: string,
    initial: any,
  ): GuardrailVerdict {
    const methodName = METHOD_FOR[direction];
    const defaultReason = DEFAULT_REASON[direction];
    let value = initial;

    for (const guardrail of this.guardrails) {
      const method = (guardrail as any)?.[methodName];
      if (typeof method !== 'function') continue;

      let ok: boolean;
      let processed: any;
      try {
        [ok, processed] = method.call(guardrail, toolName, value);
      } catch (error) {
        const name = guardrail?.name || 'guardrail';
        const reason = error instanceof Error ? error.message : String(error);
        if (this.failOpen) {
          console.warn(
            `[praisonai] Tool guardrail '${name}' threw on '${toolName}' and failOpen is set; ` +
              `allowing through: ${reason}`,
          );
          continue;
        }
        // Fail closed: a broken guardrail must block, not permit.
        return [false, `guardrail '${name}' failed: ${reason}`];
      }

      if (!ok) {
        // A second element that is not a non-empty string is not a reason, so
        // the direction's default is used in that case.
        return [false, typeof processed === 'string' && processed ? processed : defaultReason];
      }
      value = processed;
    }

    return [true, value];
  }
}

/** Turn one user-supplied entry into a protocol-conforming guardrail. */
function coerceOne(item: ToolGuardrailSpec, direction: GuardrailDirection): ToolGuardrailLike {
  const methodName = METHOD_FOR[direction];
  if (item && typeof (item as any)[methodName] === 'function') {
    // Already speaks the protocol — reuse it verbatim.
    return item as ToolGuardrailLike;
  }
  if (typeof item === 'function') {
    return direction === INPUT
      ? new ToolInputGuardrail(item)
      : new ToolOutputGuardrail(item);
  }
  throw new TypeError(
    `${ATTR_FOR[direction]} entries must be a function or expose ${methodName}(); ` +
      `got ${item === null ? 'null' : typeof item}.`,
  );
}

/**
 * Coerce an `inputGuardrails` / `outputGuardrails` value into a chain.
 *
 * Accepts a single guardrail or an array of them; each entry may be a plain
 * function or any object already exposing the matching protocol method.
 * Returns `undefined` when nothing was declared, which is what keeps the
 * executor's fast path free of any per-call work for unguarded tools.
 */
export function buildToolGuardrails(
  spec: ToolGuardrailSpec | ToolGuardrailSpec[] | undefined | null,
  direction: GuardrailDirection,
): ToolGuardrailChain | undefined {
  if (spec === undefined || spec === null) return undefined;
  if (spec instanceof ToolGuardrailChain) return spec;

  const items = (Array.isArray(spec) ? spec : [spec]).map(item => coerceOne(item, direction));
  if (items.length === 0) return undefined;
  return new ToolGuardrailChain(items, { direction });
}

/** Where a coerced chain is memoised on a tool object, per direction. */
const CACHE_KEY = '__praisonToolGuardrailChains';

/**
 * Return the guardrail chain declared on `toolObj`, or `undefined`.
 *
 * `tool({...})` coerces at definition time, so this is usually a single
 * property read. An object may instead declare a raw array; that is coerced on
 * first use and memoised. A malformed declaration is warned about and treated
 * as "no guardrail" rather than breaking every call to the tool.
 */
export function getToolGuardrailChain(
  toolObj: any,
  direction: GuardrailDirection,
): ToolGuardrailChain | undefined {
  if (!toolObj) return undefined;

  const declared = toolObj[ATTR_FOR[direction]];
  if (declared === undefined || declared === null) return undefined;
  if (declared instanceof ToolGuardrailChain) return declared;

  const cache = toolObj[CACHE_KEY];
  if (cache && typeof cache === 'object' && direction in cache) {
    return cache[direction];
  }

  let chain: ToolGuardrailChain | undefined;
  try {
    chain = buildToolGuardrails(declared, direction);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    console.warn(
      `[praisonai] Ignoring malformed ${ATTR_FOR[direction]} on tool ` +
        `'${toolObj?.name ?? String(toolObj)}': ${reason}`,
    );
    chain = undefined;
  }

  try {
    const store = cache && typeof cache === 'object' ? cache : {};
    store[direction] = chain;
    if (!cache) {
      Object.defineProperty(toolObj, CACHE_KEY, {
        value: store,
        enumerable: false,
        writable: true,
        configurable: true,
      });
    }
  } catch {
    // e.g. a frozen tool object — memoising is an optimisation, not a contract.
  }

  return chain;
}

/** Build the model-facing denial for a blocked call. */
export function toolGuardrailDenial(
  toolName: string,
  direction: GuardrailDirection,
  reason: string,
): ToolGuardrailDenial {
  const what = direction === INPUT ? 'was blocked by an input guardrail' : 'result was blocked by an output guardrail';
  return {
    error: `Tool '${toolName}' ${what}: ${reason}`,
    guardrail_denied: true,
    tool_guardrail: direction,
  };
}
