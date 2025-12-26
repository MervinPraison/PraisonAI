/**
 * Planning command - Task planning and todo management
 */

import { createPlan, createTodoList, TodoItem, type PlanConfig, type TodoItemConfig } from '../../planning';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface PlanningOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

export async function execute(args: string[], options: PlanningOptions): Promise<void> {
  const action = args[0] || 'help';
  const actionArgs = args.slice(1);
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    switch (action) {
      case 'create':
        await createNewPlan(actionArgs, outputFormat);
        break;
      case 'todo':
        await manageTodo(actionArgs, outputFormat);
        break;
      case 'help':
      default:
        await showHelp(outputFormat);
        break;
    }
  } catch (error) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, error instanceof Error ? error.message : String(error)));
    } else {
      await pretty.error(error instanceof Error ? error.message : String(error));
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }
}

async function createNewPlan(args: string[], outputFormat: string): Promise<void> {
  const name = args.join(' ');
  if (!name) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a name for the plan'));
    } else {
      await pretty.error('Please provide a name for the plan');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const plan = createPlan({
    name,
    description: name
  });

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      id: plan.id,
      name: plan.name,
      status: plan.status
    }));
  } else {
    await pretty.success(`Plan created: ${plan.id}`);
    await pretty.plain(`Name: ${name}`);
  }
}

async function manageTodo(args: string[], outputFormat: string): Promise<void> {
  const subAction = args[0] || 'list';
  const todoArgs = args.slice(1);

  const todoList = createTodoList();

  switch (subAction) {
    case 'add':
      const content = todoArgs.join(' ');
      if (!content) {
        if (outputFormat === 'json') {
          outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide todo content'));
        } else {
          await pretty.error('Please provide todo content');
        }
        process.exit(EXIT_CODES.INVALID_ARGUMENTS);
      }
      const newItem = new TodoItem({ content });
      todoList.add(newItem);
      if (outputFormat === 'json') {
        outputJson(formatSuccess({ added: true, id: newItem.id, content: newItem.content }));
      } else {
        await pretty.success(`Todo added: ${content}`);
      }
      break;
    case 'list':
    default:
      const items = todoList.items;
      if (outputFormat === 'json') {
        outputJson(formatSuccess({ items, count: items.length }));
      } else {
        await pretty.heading('Todo List');
        if (items.length === 0) {
          await pretty.info('No todos');
        } else {
          for (const todo of items) {
            const status = todo.status === 'completed' ? '✓' : '○';
            await pretty.plain(`  ${status} ${todo.content}`);
          }
        }
      }
      break;
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'planning',
    subcommands: [
      { name: 'create <goal>', description: 'Create a new plan' },
      { name: 'todo add <title>', description: 'Add a todo item' },
      { name: 'todo list', description: 'List todo items' },
      { name: 'help', description: 'Show this help' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Planning Command');
    await pretty.plain('Task planning and todo management\n');
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(25)} ${cmd.description}`);
    }
  }
}
