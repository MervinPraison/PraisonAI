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

/**
 * Split one CSV line, honouring `"` quoting and `\` escaping the way Python's
 * `csv.reader(quotechar='"', escapechar='\\')` does.
 */
export function parseCsvLine(line: string): string[] {
    const fields: string[] = [];
    let field = '';
    let quoted = false;
    for (let i = 0; i < line.length; i++) {
        const ch = line[i];
        if (ch === '\\' && i + 1 < line.length) { field += line[++i]; continue; }
        if (ch === '"') { quoted = !quoted; continue; }
        if (ch === ',' && !quoted) { fields.push(field); field = ''; continue; }
        field += ch;
    }
    fields.push(field);
    return fields;
}

/**
 * The row texts an input file contributes. A CSV row of two or more fields
 * becomes Python's `"Question: <a>\nAnswer: <rest>"` pair; a single field, or a
 * line of a text file, is used verbatim. Empty rows are dropped.
 */
export function inputFileRows(contents: string, extension: string): string[] {
    const lines = contents.split(/\r?\n/);
    if (extension.toLowerCase() !== '.csv') {
        return lines.map((l) => l.trim()).filter((l) => l.length > 0);
    }
    const rows: string[] = [];
    for (const line of lines) {
        if (line.trim().length === 0) continue;
        const fields = parseCsvLine(line);
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

    const inherited = task.nextTasks.length > 0 ? [...task.nextTasks] : [];
    const nameFor = (index: number, text: string): string =>
        task.name ? `${task.name}_${index + 1}` : text;

    const names = rows.map((text, i) => nameFor(i, text));

    return rows.map((text, i): TaskConfig => {
        const description = task.description ? `${task.description}\n${text}` : text;
        const isLast = i === rows.length - 1;
        const nextTasks = isLast ? inherited : [names[i + 1]];
        const base: TaskConfig = {
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
