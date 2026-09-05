/**
 * `inputFile` fan-out (Python `Process._create_loop_subtasks`).
 *
 * A task with an `inputFile` is a template: each CSV row (or each non-empty
 * line of a text file) becomes one subtask whose description is the parent
 * description followed by the row. The subtasks are chained with `nextTasks`,
 * the first is flagged `isStart`, and the last inherits the parent's
 * `nextTasks` so the workflow rejoins its original successor.
 *
 * The module returns `TaskConfig` values rather than `Task` instances so it
 * never has to import the `Task` class at run time.
 */

import * as fs from 'fs';
import * as path from 'path';
import type { Task, TaskConfig } from '../types';
import { inheritedExecutionConfig } from './task-loop';

/**
 * Parse a whole CSV document into logical records. `"` quotes a field, a
 * doubled `""` inside a quoted field is a literal quote (RFC 4180), a `\` escapes
 * the next character outside quotes (Python's `escapechar='\\'`), and a newline
 * inside quotes stays part of the field rather than starting a new record.
 * Returns one string[] per logical record.
 */
export function parseCsv(contents: string): string[][] {
    const records: string[][] = [];
    let record: string[] = [];
    let field = '';
    let quoted = false;
    let started = false;
    const pushField = () => { record.push(field); field = ''; };
    const pushRecord = () => { pushField(); records.push(record); record = []; started = false; };

    for (let i = 0; i < contents.length; i++) {
        const ch = contents[i];
        if (quoted) {
            if (ch === '"') {
                if (contents[i + 1] === '"') { field += '"'; i++; }
                else quoted = false;
            } else {
                field += ch;
            }
            continue;
        }
        if (ch === '\\' && i + 1 < contents.length) { field += contents[++i]; started = true; continue; }
        if (ch === '"') { quoted = true; started = true; continue; }
        if (ch === ',') { pushField(); started = true; continue; }
        if (ch === '\r') { continue; }
        if (ch === '\n') { if (started || field.length > 0) pushRecord(); continue; }
        field += ch;
        started = true;
    }
    if (started || field.length > 0) pushRecord();
    return records;
}

/**
 * Split one CSV line, honouring `"` quoting and `""` doubled-quote escaping.
 * Kept for callers that already hold a single physical record; prefer
 * `parseCsv` for whole files so quoted newlines survive.
 */
export function parseCsvLine(line: string): string[] {
    const [record] = parseCsv(line);
    return record ?? [''];
}

/**
 * The row texts an input file contributes. A CSV row of two or more fields
 * becomes Python's `"Question: <a>\nAnswer: <rest>"` pair; a single field, or a
 * line of a text file, is used verbatim. Empty rows are dropped.
 */
export function inputFileRows(contents: string, extension: string): string[] {
    if (extension.toLowerCase() !== '.csv') {
        return contents.split(/\r?\n/).map((l) => l.trim()).filter((l) => l.length > 0);
    }
    const rows: string[] = [];
    for (const fields of parseCsv(contents)) {
        if (fields.length === 0) continue;
        let text = (fields[0] ?? '').trim();
        if (fields.length > 1) {
            const question = (fields[0] ?? '').trim();
            const answer = fields.slice(1).map((f) => f.trim()).join(',');
            text = `Question: ${question}\nAnswer: ${answer}`;
        }
        if (text.length > 0) rows.push(text);
    }
    return rows;
}

/** How the parent task's file is read; injectable so tests need no disk. */
export type FileReader = (filePath: string) => string;

const readFromDisk: FileReader = (filePath) => fs.readFileSync(filePath, 'utf8');

/**
 * Build the subtask configs for `task`'s `inputFile`.
 *
 * @param decisionMode - Python's `decision_mode`: subtasks become `decision`
 *   tasks carrying a `done`/`retry`/`exit` condition table, as the workflow
 *   engine does for a start task.
 * @returns `[]` when the task has no `inputFile`.
 * @throws when the file cannot be read — the caller marks the task failed, as
 *   Python does.
 */
export function inputFileTaskConfigs(
    task: Task,
    options: { decisionMode?: boolean; readFile?: FileReader } = {}
): TaskConfig[] {
    if (!task.inputFile) return [];
    const readFile = options.readFile ?? readFromDisk;
    const rows = inputFileRows(readFile(task.inputFile), path.extname(task.inputFile));
    if (rows.length === 0) return [];

    const inheritedNext = task.nextTasks.length > 0 ? [...task.nextTasks] : [];
    const inheritedExecution = inheritedExecutionConfig(task);
    const nameFor = (index: number, text: string): string =>
        task.name ? `${task.name}_${index + 1}` : text;

    const names = rows.map((text, i) => nameFor(i, text));

    return rows.map((text, i): TaskConfig => {
        const description = task.description ? `${task.description}\n${text}` : text;
        const isLast = i === rows.length - 1;
        const nextTasks = isLast ? inheritedNext : [names[i + 1]];
        const base: TaskConfig = {
            ...inheritedExecution,
            description,
            name: names[i],
            agent: task.agent,
            expected_output: task.expected_output,
            onTaskComplete: task.onTaskComplete ?? task.callback,
            isStart: i === 0,
            taskType: options.decisionMode ? 'decision' : 'task',
            nextTasks,
        };
        if (options.decisionMode) {
            base.condition = {
                done: nextTasks.length > 0 ? nextTasks : [],
                retry: [names[i]],
                exit: [],
            };
        }
        return base;
    });
}
