/**
 * Turning an agent's raw text into a `TaskOutput`, and resolving the
 * `outputConfig` object onto the task's individual output fields.
 *
 * `buildTaskOutput` ports `praisonaiagents/agents/agents.py::_process_task_result`:
 * the raw text is stripped of a markdown fence and parsed when the task asked
 * for `outputJson` or `outputPydantic`; a parse failure is recorded as a
 * non-fatal error and the raw text stands.
 *
 * `resolveOutputConfig` ports
 * `praisonaiagents/workflows/workflow_configs.py::resolve_step_output_config`:
 * a string is a file path, an object supplies `file` / `json_model` /
 * `pydantic_model` / `variable`.
 */

import type { Task, TaskOutput } from '../types';

/** The fields an `outputConfig` (Python `TaskOutputConfig`) can carry. */
export interface ResolvedOutputConfig {
    file?: string;
    json?: unknown;
    pydantic?: unknown;
    variable?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Resolve an `outputConfig` value; `undefined` when it carries nothing. */
export function resolveOutputConfig(value: unknown): ResolvedOutputConfig | undefined {
    if (value === undefined || value === null) return undefined;
    if (typeof value === 'string') return { file: value };
    if (!isRecord(value)) return undefined;
    const resolved: ResolvedOutputConfig = {};
    if (typeof value.file === 'string') resolved.file = value.file;
    const json = value.jsonModel ?? value.json_model ?? value.json;
    if (json !== undefined && json !== null) resolved.json = json;
    const pydantic = value.pydanticModel ?? value.pydantic_model ?? value.pydantic;
    if (pydantic !== undefined && pydantic !== null) resolved.pydantic = pydantic;
    if (typeof value.variable === 'string') resolved.variable = value.variable;
    return Object.keys(resolved).length > 0 ? resolved : undefined;
}

/**
 * Python `Agents.clean_json_output`: strip a ```json fence so the payload can
 * be parsed.
 */
export function cleanJsonOutput(raw: string): string {
    let text = raw.trim();
    if (text.startsWith('```')) {
        text = text.replace(/^```[a-zA-Z]*\s*/, '');
        if (text.endsWith('```')) text = text.slice(0, -3);
    }
    return text.trim();
}

/**
 * Build the `TaskOutput` for `raw`.
 *
 * A task with neither `outputJson` nor `outputPydantic` gets a plain `RAW`
 * output; asking for either parses the text and sets the matching field and
 * `outputFormat`. A parse failure is appended to the task's `nonFatalErrors`.
 */
export function buildTaskOutput(task: Task, raw: string, agentName = 'Agent'): TaskOutput {
    const output: TaskOutput = {
        description: task.description,
        summary: task.description.slice(0, 10),
        raw,
        agent: agentName,
        outputFormat: 'RAW',
    };
    if (task.outputJson === undefined && task.outputPydantic === undefined) return output;

    const cleaned = cleanJsonOutput(raw);
    let parsed: unknown;
    try {
        parsed = JSON.parse(cleaned);
    } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        task.nonFatalErrors.push(`output parse: ${message}`);
        return output;
    }

    if (task.outputJson !== undefined) {
        if (isRecord(parsed)) {
            output.outputJson = parsed;
            output.outputFormat = 'JSON';
        } else {
            task.nonFatalErrors.push('output parse: expected a JSON object');
        }
    }
    if (task.outputPydantic !== undefined) {
        if (isRecord(parsed)) {
            output.outputPydantic = parsed;
            output.outputFormat = 'Pydantic';
        } else {
            task.nonFatalErrors.push('output parse: expected a JSON object for pydantic');
        }
    }
    return output;
}
