/**
 * Inter-task context assembly (Python `Process._build_task_context`).
 *
 * `retainFullContext` is the switch: with it every upstream result is folded
 * into the prompt; without it only the most recent one is, which is the whole
 * point of the flag (Python's comment calls it "Original behavior" vs "New
 * behavior"). Validation feedback from a failed guardrail is prepended so a
 * retry sees why the last attempt was rejected.
 */

import type { Task, TaskOutput } from '../types';

/** One upstream result, in run order. */
export interface PreviousOutput {
    name: string;
    raw: string;
}

export const CONTEXT_HEADER = '\nInput data from previous tasks:';

function rawOf(result: TaskOutput | string | null | undefined): string | undefined {
    if (result === null || result === undefined) return undefined;
    if (typeof result === 'string') return result.length > 0 ? result : undefined;
    return result.raw && result.raw.length > 0 ? result.raw : undefined;
}

/**
 * The results the task's own `context` list contributes, in declaration order.
 * String context items are literal input; Task items contribute their result.
 */
export function contextOutputs(task: Task): PreviousOutput[] {
    const out: PreviousOutput[] = [];
    for (const item of task.context) {
        if (typeof item === 'string') {
            if (item.trim().length > 0) out.push({ name: 'input', raw: item });
            continue;
        }
        const raw = rawOf(item.result);
        const name = item.name ?? item.description;
        if (raw !== undefined && name !== task.name) out.push({ name: name || 'context', raw });
    }
    return out;
}

/** Render `validationFeedback` the way Python's retry prompt does. */
export function renderValidationFeedback(feedback: unknown): string | undefined {
    if (feedback === undefined || feedback === null) return undefined;
    if (typeof feedback === 'string') {
        return `\nPrevious attempt failed validation with reason: ${feedback}`
            + '\nPlease try again with a different approach based on this feedback.\n';
    }
    if (typeof feedback !== 'object') return undefined;
    const f = feedback as Record<string, unknown>;
    const reason = f.validation_response ?? f.validationResponse ?? f.reason;
    let text = `\nPrevious attempt failed validation with reason: ${String(reason ?? '')}`;
    const validated = f.validated_task ?? f.validatedTask;
    if (validated) text += `\nValidated task: ${String(validated)}`;
    const details = f.validation_details ?? f.validationDetails;
    if (details) text += `\nValidation feedback: ${String(details)}`;
    const rejected = f.rejected_output ?? f.rejectedOutput;
    if (rejected) text += `\nRejected output: ${String(rejected)}`;
    text += '\nPlease try again with a different approach based on this feedback.\n';
    return text;
}

/**
 * Build the context block for `task`.
 *
 * @param task - the task about to run.
 * @param previous - upstream results in run order (workflow `nextTasks` edges).
 *   The runner supplies these; the task's own `context` list is read from the
 *   task itself.
 *
 * Consuming `validationFeedback` clears it, matching Python, so the feedback is
 * injected exactly once.
 */
export function buildTaskContext(task: Task, previous: readonly PreviousOutput[] = []): string {
    const feedback = renderValidationFeedback(task.validationFeedback);
    const ctx = contextOutputs(task);
    if (feedback !== undefined) task.validationFeedback = undefined;

    if (previous.length === 0 && ctx.length === 0) return feedback ?? '';

    let text = feedback === undefined ? CONTEXT_HEADER : feedback + CONTEXT_HEADER;

    if (task.retainFullContext) {
        for (const p of previous) text += `\n${p.name}: ${p.raw}`;
        for (const c of ctx) text += `\n${c.name}: ${c.raw}`;
        return text;
    }

    // Only the most recent upstream result, and the most recent context result.
    const lastPrevious = previous[previous.length - 1];
    if (lastPrevious) text += `\n${lastPrevious.name}: ${lastPrevious.raw}`;
    const lastContext = ctx[ctx.length - 1];
    if (lastContext) text += `\n${lastContext.name}: ${lastContext.raw}`;
    return text;
}
