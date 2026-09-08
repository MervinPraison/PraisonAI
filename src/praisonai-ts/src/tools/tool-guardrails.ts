/**
 * Per-tool guardrails.
 *
 * Python parity: `praisonaiagents.guardrails.tool_guardrails`
 * (`@tool(input_guardrails=..., output_guardrails=...)`).
 *
 * Agent-wide guardrails check the final answer; the approval gate stops a call
 * to ask a human. Neither lets you validate ONE tool's arguments -- rejecting a
 * `sendEmail` whose recipient is off-domain -- without hand-wrapping the
 * function. These fill that gap.
 *
 * ```ts
 * const sendEmail = tool(fn, {
 *   inputGuardrails: (args) =>
 *     String(args.to).endsWith('@example.com')
 *       ? { allowed: true }
 *       : { allowed: false, message: 'recipient must be internal' },
 * });
 * ```
 *
 * A blocked call does not throw at the caller: it returns a message the model
 * can read and react to, which is what makes the guardrail useful mid-run
 * rather than fatal.
 */

/** Verdict from a tool guardrail. */
export interface ToolGuardrailResult {
  /** False blocks the call (input) or the result (output). */
  allowed: boolean;
  /** Why it was blocked. Surfaced to the model in place of the result. */
  message?: string;
  /**
   * Replacement value. For an input guardrail these are the arguments the tool
   * receives; for an output guardrail it is the result handed onward. Lets a
   * guardrail redact rather than refuse.
   */
  replacement?: any;
}

/** A tool guardrail: sees arguments (input) or the result (output). */
export type ToolGuardrailFunction = (
  value: any,
  context?: { toolName?: string; direction: 'input' | 'output' }
) => ToolGuardrailResult | Promise<ToolGuardrailResult>;

/** One or more guardrails, as accepted by `tool()`. */
export type ToolGuardrailInput = ToolGuardrailFunction | ToolGuardrailFunction[];

/** Raised when a tool guardrail blocks and the caller asked for an exception. */
export class ToolGuardrailBlocked extends Error {
  readonly toolName?: string;
  readonly direction: 'input' | 'output';

  constructor(direction: 'input' | 'output', message: string, toolName?: string) {
    super(
      `Tool ${toolName ? `'${toolName}' ` : ''}${direction} guardrail blocked the ` +
        `${direction === 'input' ? 'call' : 'result'}: ${message}`
    );
    this.name = 'ToolGuardrailBlocked';
    this.toolName = toolName;
    this.direction = direction;
  }
}

/** Normalise one-or-many into an array; `undefined` stays undefined so the fast path is free. */
export function buildToolGuardrails(
  input: ToolGuardrailInput | undefined
): ToolGuardrailFunction[] | undefined {
  if (!input) return undefined;
  const list = Array.isArray(input) ? input : [input];
  return list.length ? list : undefined;
}

/**
 * Run a guardrail chain. Returns the (possibly replaced) value, or a blocked
 * verdict for the caller to surface to the model.
 */
export async function runToolGuardrails(
  guardrails: ToolGuardrailFunction[] | undefined,
  value: any,
  direction: 'input' | 'output',
  toolName?: string
): Promise<{ blocked: false; value: any } | { blocked: true; message: string }> {
  if (!guardrails || guardrails.length === 0) return { blocked: false as const, value };
  let current = value;
  for (const g of guardrails) {
    const verdict = await g(current, { toolName, direction });
    if (!verdict.allowed) {
      return {
        blocked: true as const,
        message: verdict.message ?? `${direction} guardrail blocked the call`,
      };
    }
    if (verdict.replacement !== undefined) current = verdict.replacement;
  }
  return { blocked: false as const, value: current };
}
