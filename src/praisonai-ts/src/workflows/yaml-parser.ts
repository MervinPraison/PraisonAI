/**
 * YAML Workflow Parser
 * Parse YAML workflow definitions into executable workflows
 */

import { AgentFlow, Task, TaskConfig, type WorkflowContext } from './index';
import * as path from 'path';

export interface YAMLWorkflowDefinition {
  name: string;
  description?: string;
  version?: string;
  steps: YAMLStepDefinition[];
  metadata?: Record<string, any>;
}

export interface YAMLStepDefinition {
  name: string;
  type: 'agent' | 'tool' | 'condition' | 'parallel' | 'loop';
  agent?: string;
  tool?: string;
  input?: string | Record<string, any>;
  output?: string;
  condition?: string;
  onError?: 'fail' | 'skip' | 'retry';
  maxRetries?: number;
  timeout?: number;
  steps?: YAMLStepDefinition[]; // For parallel/loop
  loopCondition?: string;
  maxIterations?: number;
}

export interface ParsedWorkflow {
  workflow: AgentFlow;
  definition: YAMLWorkflowDefinition;
  errors: string[];
}

// Whitelist of allowed step keys to prevent injection
const ALLOWED_STEP_KEYS = new Set([
  'type', 'agent', 'tool', 'input', 'output', 'condition',
  'onError', 'maxRetries', 'timeout', 'loopCondition', 'maxIterations',
]);

/**
 * Parse YAML string into workflow definition
 */
export function parseYAMLWorkflow(yamlContent: string): YAMLWorkflowDefinition {
  // SECURITY: If migrating to js-yaml, you MUST use:
  //   yaml.load(content, { schema: yaml.JSON_SCHEMA })
  // Never use yaml.load() with DEFAULT_SCHEMA — it enables arbitrary JS execution.
  const lines = yamlContent.split('\n');
  const result: YAMLWorkflowDefinition = {
    name: '',
    steps: []
  };

  let currentStep: Partial<YAMLStepDefinition> | null = null;
  let indent = 0;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    const currentIndent = line.search(/\S/);
    
    // Parse key-value pairs
    const colonIndex = trimmed.indexOf(':');
    if (colonIndex === -1) continue;

    const key = trimmed.substring(0, colonIndex).trim();
    const value = trimmed.substring(colonIndex + 1).trim();

    if (currentIndent === 0) {
      // Top-level keys
      if (key === 'name') result.name = value;
      else if (key === 'description') result.description = value;
      else if (key === 'version') result.version = value;
      else if (key === 'steps') {
        // Steps array starts
        indent = currentIndent;
      }
    } else if (trimmed.startsWith('- name:')) {
      // New step
      if (currentStep && currentStep.name) {
        result.steps.push(currentStep as YAMLStepDefinition);
      }
      currentStep = {
        name: value,
        type: 'agent'
      };
    } else if (currentStep) {
      // Step properties — whitelist allowed keys to prevent injection
      if (!ALLOWED_STEP_KEYS.has(key)) {
        // Ignore unknown keys — do not allow arbitrary property injection
        continue;
      }
      if (key === 'type') currentStep.type = value as any;
      else if (key === 'agent') currentStep.agent = value;
      else if (key === 'tool') currentStep.tool = value;
      else if (key === 'input') currentStep.input = value;
      else if (key === 'output') currentStep.output = value;
      else if (key === 'condition') currentStep.condition = value;
      else if (key === 'onError') currentStep.onError = value as any;
      else if (key === 'maxRetries') currentStep.maxRetries = parseInt(value);
      else if (key === 'timeout') currentStep.timeout = parseInt(value);
      else if (key === 'loopCondition') currentStep.loopCondition = value;
      else if (key === 'maxIterations') currentStep.maxIterations = parseInt(value);
    }
  }

  // Add last step
  if (currentStep && currentStep.name) {
    result.steps.push(currentStep as YAMLStepDefinition);
  }

  return result;
}

/**
 * Create executable workflow from YAML definition
 */
export function createWorkflowFromYAML(
  definition: YAMLWorkflowDefinition,
  agents: Record<string, any> = {},
  tools: Record<string, any> = {}
): ParsedWorkflow {
  const errors: string[] = [];
  const workflow = new AgentFlow(definition.name);

  for (const stepDef of definition.steps) {
    try {
      const stepConfig = createStepConfig(stepDef, agents, tools, errors);
      if (stepConfig) {
        workflow.addStep(stepConfig);
      }
    } catch (error: any) {
      errors.push(`Error creating step ${stepDef.name}: ${error.message}`);
    }
  }

  return { workflow, definition, errors };
}

function createStepConfig(
  stepDef: YAMLStepDefinition,
  agents: Record<string, any>,
  tools: Record<string, any>,
  errors: string[]
): TaskConfig | null {
  const { name, type, agent, tool, onError, maxRetries, timeout, condition } = stepDef;

  let execute: any;

  switch (type) {
    case 'agent':
      if (!agent) {
        errors.push(`Step ${name}: agent type requires 'agent' field`);
        return null;
      }
      const agentInstance = agents[agent];
      if (!agentInstance) {
        errors.push(`Step ${name}: agent '${agent}' not found`);
        return null;
      }
      execute = async (input: any) => {
        if (typeof agentInstance.chat === 'function') {
          return agentInstance.chat(typeof input === 'string' ? input : JSON.stringify(input));
        }
        return agentInstance(input);
      };
      break;

    case 'tool':
      if (!tool) {
        errors.push(`Step ${name}: tool type requires 'tool' field`);
        return null;
      }
      const toolInstance = tools[tool];
      if (!toolInstance) {
        errors.push(`Step ${name}: tool '${tool}' not found`);
        return null;
      }
      execute = async (input: any) => {
        if (typeof toolInstance.execute === 'function') {
          return toolInstance.execute(input);
        }
        if (typeof toolInstance.run === 'function') {
          return toolInstance.run(input);
        }
        return toolInstance(input);
      };
      break;

    case 'condition':
      execute = async (input: any, context: any) => {
        // Evaluate condition and return input or skip
        if (condition) {
          // Simple condition evaluation
          const result = evaluateCondition(condition, input, context);
          return result ? input : null;
        }
        return input;
      };
      break;

    default:
      execute = async (input: any) => input;
  }

  return {
    name,
    execute,
    onError,
    maxRetries,
    timeout,
    condition: condition ? (context) => evaluateCondition(condition, null, context) : undefined
  };
}

function evaluateCondition(condition: string, input: any, context: any): boolean {
  // Simple condition evaluation
  // Supports: "result.success", "input.length > 0", etc.
  try {
    // Create a safe evaluation context
    const evalContext = {
      input,
      context,
      result: context?.get?.('lastResult'),
      ...context?.metadata
    };

    // Simple expression evaluation
    if (condition.includes('===')) {
      const [left, right] = condition.split('===').map(s => s.trim());
      return getNestedValue(evalContext, left) === parseValue(right);
    }
    if (condition.includes('!==')) {
      const [left, right] = condition.split('!==').map(s => s.trim());
      return getNestedValue(evalContext, left) !== parseValue(right);
    }
    if (condition.includes('>')) {
      const [left, right] = condition.split('>').map(s => s.trim());
      return getNestedValue(evalContext, left) > parseValue(right);
    }
    if (condition.includes('<')) {
      const [left, right] = condition.split('<').map(s => s.trim());
      return getNestedValue(evalContext, left) < parseValue(right);
    }

    // Boolean check
    return !!getNestedValue(evalContext, condition);
  } catch {
    return false;
  }
}

function getNestedValue(obj: any, path: string): any {
  return path.split('.').reduce((current, key) => current?.[key], obj);
}

function parseValue(value: string): any {
  value = value.trim();
  if (value === 'true') return true;
  if (value === 'false') return false;
  if (value === 'null') return null;
  if (value.startsWith('"') && value.endsWith('"')) return value.slice(1, -1);
  if (value.startsWith("'") && value.endsWith("'")) return value.slice(1, -1);
  const num = Number(value);
  if (!isNaN(num)) return num;
  return value;
}

/**
 * Load workflow from YAML file
 */
export async function loadWorkflowFromFile(
  filePath: string,
  agents: Record<string, any> = {},
  tools: Record<string, any> = {},
  options: { basePath?: string; maxFileSizeBytes?: number } = {}
): Promise<ParsedWorkflow> {
  const fs = await import('fs/promises');

  // SECURITY: Prevent path traversal
  const normalizedPath = path.normalize(filePath);
  // Check for '..' as path segments (not just substring)
  const pathSegments = normalizedPath.split(path.sep);
  if (pathSegments.includes('..')) {
    throw new Error('Path traversal detected: ".." path segments are not allowed');
  }

  let effectivePath: string;
  // If basePath is specified, ensure resolvedPath stays within it
  if (options.basePath) {
    const resolvedBase = path.resolve(options.basePath);
    const resolvedFile = path.resolve(options.basePath, normalizedPath);
    if (!resolvedFile.startsWith(resolvedBase + path.sep) && resolvedFile !== resolvedBase) {
      throw new Error(`File path must be within base directory: ${options.basePath}`);
    }
    effectivePath = resolvedFile;
  } else {
    effectivePath = path.resolve(normalizedPath);
  }

  // SECURITY: Enforce file size limit (default 1 MB)
  const maxSize = options.maxFileSizeBytes ?? 1_048_576;
  const stat = await fs.stat(effectivePath);
  if (stat.size > maxSize) {
    throw new Error(`File too large: ${stat.size} bytes exceeds limit of ${maxSize} bytes`);
  }

  const content = await fs.readFile(effectivePath, 'utf-8');
  const definition = parseYAMLWorkflow(content);
  return createWorkflowFromYAML(definition, agents, tools);
}

/**
 * Validate YAML workflow definition
 */
export function validateWorkflowDefinition(definition: YAMLWorkflowDefinition): string[] {
  const errors: string[] = [];

  if (!definition.name) {
    errors.push('Workflow must have a name');
  }

  if (!definition.steps || definition.steps.length === 0) {
    errors.push('Workflow must have at least one step');
  }

  const stepNames = new Set<string>();
  for (const step of definition.steps) {
    if (!step.name) {
      errors.push('Each step must have a name');
    } else if (stepNames.has(step.name)) {
      errors.push(`Duplicate step name: ${step.name}`);
    } else {
      stepNames.add(step.name);
    }

    if (!step.type) {
      errors.push(`Step ${step.name}: must have a type`);
    }

    if (step.type === 'agent' && !step.agent) {
      errors.push(`Step ${step.name}: agent type requires 'agent' field`);
    }

    if (step.type === 'tool' && !step.tool) {
      errors.push(`Step ${step.name}: tool type requires 'tool' field`);
    }
  }

  return errors;
}


// ============================================================================
// Python parity: YAMLWorkflowParser class
// (praisonaiagents/workflows/yaml_parser.py)
// ============================================================================

import { Agent } from '../agent/simple';
import { Loop } from './loop';
import { Repeat, type RepeatContext } from './repeat';
import {
  If, Parallel, Route, Include,
  substituteWorkflowVariables,
  type FlowStep, type ParallelOnFailure, type AgentLikeStep,
} from './patterns';

// ----------------------------------------------------------------------------
// Minimal block-YAML reader
//
// praisonai-ts has no YAML dependency, and the line-based parser above only
// understands the flat `- name:` step list. Workflow YAML needs nested maps and
// sequences (if/then/else, route tables, loop steps), so this reader covers the
// commonly used YAML subset: block maps and sequences, plain/quoted scalars,
// flow `[a, b]` / `{k: v}` collections, `|` / `>` block scalars, comments and
// document markers. Anchors, tags and multi-document streams are not supported.
// ----------------------------------------------------------------------------

interface YamlLine {
  /** 1-based line number for error messages. */
  no: number;
  indent: number;
  /** Content with trailing comment removed and whitespace trimmed. */
  text: string;
  /** Original line (used for block scalars). */
  raw: string;
  blank: boolean;
}

function stripYamlComment(line: string): string {
  let inSingle = false;
  let inDouble = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === "'" && !inDouble) inSingle = !inSingle;
    else if (ch === '"' && !inSingle && line[i - 1] !== '\\') inDouble = !inDouble;
    else if (ch === '#' && !inSingle && !inDouble && (i === 0 || /\s/.test(line[i - 1]))) {
      return line.slice(0, i);
    }
  }
  return line;
}

function isSequenceItem(text: string): boolean {
  return text === '-' || text.startsWith('- ');
}

/** Split `key: value` at the first unquoted `: ` (or trailing `:`). */
function splitYamlKeyValue(text: string): [string, string] | null {
  if (text.startsWith('[') || text.startsWith('{')) return null;
  let inSingle = false;
  let inDouble = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === "'" && !inDouble) inSingle = !inSingle;
    else if (ch === '"' && !inSingle && text[i - 1] !== '\\') inDouble = !inDouble;
    else if (ch === ':' && !inSingle && !inDouble) {
      const next = text[i + 1];
      if (next === undefined || next === ' ' || next === '\t') {
        return [text.slice(0, i).trim(), text.slice(i + 1).trim()];
      }
    }
  }
  return null;
}

function unquoteYaml(value: string): string {
  if (value.length >= 2 && value.startsWith('"') && value.endsWith('"')) {
    return value.slice(1, -1).replace(/\\(.)/g, (_, c: string) => {
      switch (c) {
        case 'n': return '\n';
        case 't': return '\t';
        case 'r': return '\r';
        case '"': return '"';
        case '\\': return '\\';
        default: return c;
      }
    });
  }
  if (value.length >= 2 && value.startsWith("'") && value.endsWith("'")) {
    return value.slice(1, -1).replace(/''/g, "'");
  }
  return value;
}

/** Split a flow collection body on top-level commas (respects quotes and nesting). */
function splitFlowItems(body: string): string[] {
  const items: string[] = [];
  let current = '';
  let depth = 0;
  let inSingle = false;
  let inDouble = false;
  for (let i = 0; i < body.length; i++) {
    const ch = body[i];
    if (ch === "'" && !inDouble) inSingle = !inSingle;
    else if (ch === '"' && !inSingle && body[i - 1] !== '\\') inDouble = !inDouble;
    if (!inSingle && !inDouble) {
      if (ch === '[' || ch === '{') depth++;
      else if (ch === ']' || ch === '}') depth--;
      else if (ch === ',' && depth === 0) {
        items.push(current.trim());
        current = '';
        continue;
      }
    }
    current += ch;
  }
  if (current.trim().length > 0) items.push(current.trim());
  return items;
}

function parseYamlScalar(value: string): any {
  const v = value.trim();
  if (v === '' || v === '~' || v === 'null' || v === 'Null' || v === 'NULL') return null;
  if (v === 'true' || v === 'True' || v === 'TRUE') return true;
  if (v === 'false' || v === 'False' || v === 'FALSE') return false;
  if (/^-?\d+$/.test(v)) return parseInt(v, 10);
  if (/^-?\d+\.\d+$/.test(v)) return parseFloat(v);
  if (v.startsWith('"') || v.startsWith("'")) return unquoteYaml(v);
  if (v.startsWith('[') && v.endsWith(']')) {
    const body = v.slice(1, -1).trim();
    return body === '' ? [] : splitFlowItems(body).map(parseYamlScalar);
  }
  if (v.startsWith('{') && v.endsWith('}')) {
    const body = v.slice(1, -1).trim();
    const obj: Record<string, any> = {};
    if (body === '') return obj;
    for (const item of splitFlowItems(body)) {
      const kv = splitYamlKeyValue(item);
      if (!kv) throw new Error(`Invalid flow mapping entry: ${item}`);
      obj[unquoteYaml(kv[0])] = parseYamlScalar(kv[1]);
    }
    return obj;
  }
  return v;
}

class YamlReader {
  private readonly lines: YamlLine[];

  constructor(text: string) {
    this.lines = text.split(/\r?\n/).map((raw, i) => {
      if (/^\t/.test(raw)) {
        throw new Error(`YAML parse error at line ${i + 1}: tabs are not allowed for indentation`);
      }
      const stripped = stripYamlComment(raw);
      const text = stripped.trim();
      const blank = text === '' || text === '---' || text === '...';
      return { no: i + 1, indent: raw.search(/\S|$/), text, raw, blank };
    });
  }

  parse(): any {
    const start = this.skipBlank(0);
    if (start >= this.lines.length) return null;
    const [value, next] = this.parseNode(start, this.lines[start].indent);
    const trailing = this.skipBlank(next);
    if (trailing < this.lines.length) {
      const line = this.lines[trailing];
      throw new Error(`YAML parse error at line ${line.no}: unexpected content '${line.text}'`);
    }
    return value;
  }

  private skipBlank(idx: number): number {
    while (idx < this.lines.length && this.lines[idx].blank) idx++;
    return idx;
  }

  private parseNode(idx: number, indent: number): [any, number] {
    const line = this.lines[idx];
    if (isSequenceItem(line.text)) return this.parseSequence(idx, indent);
    return this.parseMapping(idx, indent);
  }

  private parseChild(idx: number, parentIndent: number): [any, number] {
    const j = this.skipBlank(idx);
    if (j >= this.lines.length) return [null, j];
    const next = this.lines[j];
    if (next.indent > parentIndent) return this.parseNode(j, next.indent);
    // YAML allows a sequence at the same indent as its parent key.
    if (next.indent === parentIndent && isSequenceItem(next.text)) return this.parseSequence(j, parentIndent);
    return [null, j];
  }

  private parseMapping(idx: number, indent: number): [Record<string, any>, number] {
    const obj: Record<string, any> = {};
    while (true) {
      idx = this.skipBlank(idx);
      if (idx >= this.lines.length) break;
      const line = this.lines[idx];
      if (line.indent < indent) break;
      if (line.indent > indent) {
        throw new Error(`YAML parse error at line ${line.no}: bad indentation`);
      }
      if (isSequenceItem(line.text)) break;

      const kv = splitYamlKeyValue(line.text);
      if (!kv) {
        throw new Error(`YAML parse error at line ${line.no}: expected 'key: value', got '${line.text}'`);
      }
      const key = unquoteYaml(kv[0]);
      const rawValue = kv[1];

      if (rawValue === '') {
        const [child, next] = this.parseChild(idx + 1, indent);
        obj[key] = child;
        idx = next;
      } else if (/^[|>][+-]?$/.test(rawValue)) {
        const [scalar, next] = this.parseBlockScalar(idx + 1, indent, rawValue);
        obj[key] = scalar;
        idx = next;
      } else {
        obj[key] = parseYamlScalar(rawValue);
        idx += 1;
      }
    }
    return [obj, idx];
  }

  private parseSequence(idx: number, indent: number): [any[], number] {
    const arr: any[] = [];
    while (true) {
      idx = this.skipBlank(idx);
      if (idx >= this.lines.length) break;
      const line = this.lines[idx];
      if (line.indent !== indent || !isSequenceItem(line.text)) break;

      const rest = line.text === '-' ? '' : line.text.slice(1).trimStart();
      if (rest === '') {
        const [child, next] = this.parseChild(idx + 1, indent);
        arr.push(child);
        idx = next;
        continue;
      }

      if (/^[|>][+-]?$/.test(rest)) {
        const [scalar, next] = this.parseBlockScalar(idx + 1, indent, rest);
        arr.push(scalar);
        idx = next;
        continue;
      }

      const inlineNode = isSequenceItem(rest) || splitYamlKeyValue(rest) !== null;
      if (inlineNode) {
        // `- key: value` starts a nested node whose indent is the column of `key`.
        const column = indent + (line.text.length - rest.length);
        this.lines[idx] = { ...line, indent: column, text: rest, raw: ' '.repeat(column) + rest };
        const [child, next] = this.parseNode(idx, column);
        arr.push(child);
        idx = next;
        continue;
      }

      arr.push(parseYamlScalar(rest));
      idx += 1;
    }
    return [arr, idx];
  }

  private parseBlockScalar(idx: number, parentIndent: number, header: string): [string, number] {
    const folded = header[0] === '>';
    const chomp = header[1] ?? '';
    const collected: string[] = [];
    let blockIndent = -1;

    while (idx < this.lines.length) {
      const line = this.lines[idx];
      const rawBlank = line.raw.trim() === '';
      if (!rawBlank && line.indent <= parentIndent) break;
      if (!rawBlank && blockIndent === -1) blockIndent = line.indent;
      collected.push(rawBlank ? '' : line.raw.slice(blockIndent));
      idx++;
    }

    while (collected.length > 0 && collected[collected.length - 1] === '') collected.pop();

    let text: string;
    if (folded) {
      text = collected
        .map(l => (l === '' ? '\n' : l))
        .join(' ')
        .replace(/ ?\n ?/g, '\n');
    } else {
      text = collected.join('\n');
    }
    if (chomp !== '-' && text.length > 0) text += '\n';
    return [text, idx];
  }
}

/**
 * Parse a YAML document into plain data (maps, arrays, scalars).
 *
 * Supports the block-YAML subset workflow files use; see {@link YamlReader}.
 * Python: yaml.safe_load
 */
export function parseYamlDocument(text: string): any {
  return new YamlReader(text).parse();
}

// ----------------------------------------------------------------------------
// Parser class
// ----------------------------------------------------------------------------

type ToolFn = (...args: any[]) => any;

/**
 * Parser for YAML workflow definitions (Python parity: YAMLWorkflowParser).
 *
 * @example
 * ```typescript
 * const parser = new YAMLWorkflowParser();
 * parser.registerAgent('writer', writerAgent);   // or let `agents:` create real Agents
 * const flow = parser.parseString(`
 * name: review
 * variables:
 *   score: 90
 * steps:
 *   - agent: writer
 *   - if:
 *       condition: "{{score}} > 80"
 *       then:
 *         - agent: writer
 *           action: "Approve: {{previous_output}}"
 * `);
 * await flow.run('Draft');
 * ```
 */
export class YAMLWorkflowParser {
  /** Tool functions referenced by name from `agents.<id>.tools`. */
  toolRegistry: Record<string, ToolFn>;
  private _agents: Record<string, AgentLikeStep> = {};
  private _callbacks: Record<string, ToolFn | null> = {};
  private _registeredAgents: Record<string, AgentLikeStep> = {};

  constructor(toolRegistry: Record<string, ToolFn> | null = null) {
    this.toolRegistry = toolRegistry ?? {};
  }

  /** Agents from the most recent parse, keyed by their YAML id. */
  get agents(): Record<string, AgentLikeStep> {
    return { ...this._agents };
  }

  /** Callbacks registered via {@link registerCallback} or declared in `callbacks:`. */
  get callbacks(): Record<string, ToolFn | null> {
    return { ...this._callbacks };
  }

  /**
   * Parse a YAML workflow file (synchronously, like Python).
   * @throws Error when the file does not exist.
   */
  parseFile(filePath: string, extraVars: Record<string, any> | null = null): AgentFlow {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const fs = require('fs') as typeof import('fs');
    const resolved = path.resolve(String(filePath));
    if (!fs.existsSync(resolved)) {
      throw new Error(`Workflow file not found: ${filePath}`);
    }
    return this.parseString(fs.readFileSync(resolved, 'utf-8'), extraVars);
  }

  /** Parse a YAML workflow string into an executable `AgentFlow`. */
  parseString(yamlContent: string, extraVars: Record<string, any> | null = null): AgentFlow {
    const data = parseYamlDocument(yamlContent);
    const normalized = this.normalizeYamlConfig(data);
    return this.parseWorkflowData(normalized, extraVars);
  }

  /** Register a tool for use in workflows. */
  registerTool(name: string, tool: ToolFn): void {
    this.toolRegistry[name] = tool;
  }

  /** Register a callback function. */
  registerCallback(name: string, callback: ToolFn): void {
    this._callbacks[name] = callback;
  }

  /**
   * Pre-register an agent (anything with `chat()`) under a YAML id. Steps that
   * reference the id use it instead of constructing a new `Agent`.
   */
  registerAgent(name: string, agent: AgentLikeStep): void {
    this._registeredAgents[name] = agent;
    this._agents[name] = agent;
  }

  // --------------------------------------------------------------------------
  // Normalisation (Python: _normalize_yaml_config)
  // --------------------------------------------------------------------------

  /** Accept both agents.yaml and workflow.yaml field names; return canonical data. */
  normalizeYamlConfig(data: Record<string, any> | null | undefined): Record<string, any> {
    if (!data || typeof data !== 'object') return {};
    const normalized: Record<string, any> = { ...data };

    if ('topic' in normalized && !('name' in normalized) && !('input' in normalized)) {
      normalized.name = normalized.topic ?? 'Unnamed Workflow';
    }
    if (!('input' in normalized) && 'topic' in normalized) {
      normalized.input = normalized.topic;
    }

    if (normalized.roles && !normalized.agents) {
      normalized.agents = this.convertRolesToAgents(normalized.roles);
      if (!normalized.steps) {
        normalized.steps = this.extractStepsFromRoles(normalized.roles);
      }
    }

    if (Array.isArray(normalized.includes)) {
      normalized.steps = [...(normalized.steps ?? [])];
      for (const item of normalized.includes) {
        if (typeof item === 'string' || (item && typeof item === 'object')) {
          normalized.steps.push({ include: item });
        }
      }
    }

    if (normalized.agents && typeof normalized.agents === 'object') {
      const agents: Record<string, any> = {};
      for (const [id, cfg] of Object.entries<any>(normalized.agents)) {
        if (cfg && typeof cfg === 'object') {
          const copy = { ...cfg };
          if ('backstory' in copy && !('instructions' in copy)) copy.instructions = copy.backstory;
          agents[id] = copy;
        } else {
          agents[id] = cfg;
        }
      }
      normalized.agents = agents;
    }

    if (Array.isArray(normalized.steps)) {
      normalized.steps = normalized.steps.map((step: any) => {
        if (!step || typeof step !== 'object') return step;
        const copy = { ...step };
        if ('description' in copy && !('action' in copy)) copy.action = copy.description;
        if (Array.isArray(copy.parallel)) {
          copy.parallel = copy.parallel.map((p: any) => {
            if (p && typeof p === 'object' && 'description' in p && !('action' in p)) {
              return { ...p, action: p.description };
            }
            return p;
          });
        }
        return copy;
      });
    }

    return normalized;
  }

  /** Python: _extract_steps_from_roles */
  private extractStepsFromRoles(roles: Record<string, any>): Record<string, any>[] {
    const steps: Record<string, any>[] = [];
    const copied = [
      'expected_output', 'context', 'output_file', 'output_json', 'create_directory',
      'callback', 'async_execution', 'guardrail', 'max_retries', 'skip_on_failure', 'retry_delay',
    ];
    for (const [roleId, roleConfig] of Object.entries<any>(roles ?? {})) {
      const tasks = roleConfig?.tasks;
      if (!tasks || typeof tasks !== 'object') continue;
      for (const [taskId, taskConfig] of Object.entries<any>(tasks)) {
        const step: Record<string, any> = { name: taskId, agent: roleId };
        if (taskConfig?.description !== undefined) step.action = taskConfig.description;
        else if (taskConfig?.action !== undefined) step.action = taskConfig.action;
        for (const field of copied) {
          if (taskConfig && field in taskConfig) step[field] = taskConfig[field];
        }
        steps.push(step);
      }
    }
    return steps;
  }

  /** Python: _convert_roles_to_agents */
  private convertRolesToAgents(roles: Record<string, any>): Record<string, any> {
    const agents: Record<string, any> = {};
    for (const [roleId, roleConfig] of Object.entries<any>(roles ?? {})) {
      const cfg = roleConfig ?? {};
      const agent: Record<string, any> = {
        name: cfg.role ?? roleId,
        role: cfg.role ?? roleId,
        goal: cfg.goal ?? '',
        instructions: cfg.backstory ?? '',
      };
      if ('llm' in cfg) {
        agent.llm = cfg.llm && typeof cfg.llm === 'object' ? (cfg.llm.model ?? 'gpt-4o-mini') : cfg.llm;
      }
      if (Array.isArray(cfg.tools)) agent.tools = cfg.tools.filter(Boolean);
      for (const key of ['max_iter', 'planning', 'reasoning']) {
        if (key in cfg) agent[key] = cfg[key];
      }
      agents[roleId] = agent;
    }
    return agents;
  }

  // --------------------------------------------------------------------------
  // Workflow assembly (Python: _parse_workflow_data)
  // --------------------------------------------------------------------------

  parseWorkflowData(data: Record<string, any>, extraVars: Record<string, any> | null = null): AgentFlow {
    const name = data.name ?? 'Unnamed Workflow';
    const description = data.description ?? '';

    let variables: Record<string, any> = { ...(data.variables ?? {}) };
    if (extraVars) variables = { ...variables, ...extraVars };

    const topic = data.topic;
    if (topic && !('topic' in variables)) {
      variables.topic = typeof topic === 'string' && topic.includes('{{')
        ? substituteWorkflowVariables(topic, variables)
        : topic;
    }

    this._agents = this.parseAgents(data.agents ?? {});
    this.parseCallbacks(data.callbacks ?? {});
    const steps = this.parseSteps(Array.isArray(data.steps) ? data.steps : []);

    return new AgentFlow({ name, description, steps, variables });
  }

  private parseAgents(agentsData: Record<string, any>): Record<string, AgentLikeStep> {
    const agents: Record<string, AgentLikeStep> = {};
    for (const [id, config] of Object.entries<any>(agentsData ?? {})) {
      agents[id] = this.createAgent(id, config ?? {});
    }
    // Registered agents are always addressable, even without an `agents:` entry.
    for (const [id, agent] of Object.entries(this._registeredAgents)) {
      if (!(id in agents)) agents[id] = agent;
    }
    return agents;
  }

  /** Python: _create_agent — a pre-registered agent wins over a fresh `Agent`. */
  private createAgent(agentId: string, config: Record<string, any>): AgentLikeStep {
    const registered = this._registeredAgents[agentId];
    if (registered) return registered;

    const llm = config.llm && typeof config.llm === 'object' ? config.llm.model : config.llm;
    const instructions = config.instructions || config.backstory || undefined;
    return new Agent({
      name: config.name ?? agentId,
      role: config.role ?? (instructions ? undefined : 'Assistant'),
      goal: config.goal ?? undefined,
      instructions,
      llm: llm ?? undefined,
      tools: this.resolveTools(config.tools ?? []),
      verbose: config.verbose ?? false,
    } as any) as unknown as AgentLikeStep;
  }

  /** Python: _resolve_tools — unknown names are skipped. */
  private resolveTools(toolsConfig: any[]): ToolFn[] {
    const tools: ToolFn[] = [];
    for (const entry of Array.isArray(toolsConfig) ? toolsConfig : []) {
      if (typeof entry === 'function') tools.push(entry);
      else if (typeof entry === 'string' && this.toolRegistry[entry]) tools.push(this.toolRegistry[entry]);
    }
    return tools;
  }

  /** Python: _parse_callbacks — names resolve to registered callbacks, else null. */
  private parseCallbacks(callbacksData: Record<string, any>): void {
    for (const [callbackName, funcName] of Object.entries<any>(callbacksData ?? {})) {
      const target = typeof funcName === 'string' ? this._callbacks[funcName] : undefined;
      if (!(callbackName in this._callbacks)) this._callbacks[callbackName] = target ?? null;
    }
  }

  // --------------------------------------------------------------------------
  // Steps (Python: _parse_steps / _parse_single_step / _parse_*_step)
  // --------------------------------------------------------------------------

  parseSteps(stepsData: any[]): FlowStep[] {
    const steps: FlowStep[] = [];
    for (const stepData of stepsData) {
      const step = this.parseSingleStep(stepData);
      if (step !== null && step !== undefined) steps.push(step);
    }
    return steps;
  }

  parseSingleStep(stepData: any): FlowStep | null {
    if (!stepData || typeof stepData !== 'object') return null;
    if ('route' in stepData) return this.parseRouteStep(stepData);
    if ('parallel' in stepData) return this.parseParallelStep(stepData);
    if ('loop' in stepData) return this.parseLoopStep(stepData);
    if ('repeat' in stepData) return this.parseRepeatStep(stepData);
    if ('include' in stepData) return this.parseIncludeStep(stepData);
    if ('if' in stepData) return this.parseIfStep(stepData);
    if ('agent' in stepData) return this.parseAgentStep(stepData);
    return this.parseGenericStep(stepData);
  }

  /**
   * Wrap an agent in a `Task` carrying the step's YAML options.
   *
   * Python mutates `agent._yaml_action` etc.; wrapping keeps one agent usable
   * in several steps with different actions.
   */
  private agentTask(agent: AgentLikeStep, agentId: string, stepData: Record<string, any>): Task {
    const action: string | undefined = stepData.action ?? undefined;
    const maxRetries = stepData.max_retries !== undefined ? Number(stepData.max_retries) : undefined;
    const retryDelay = stepData.retry_delay !== undefined ? Number(stepData.retry_delay) * 1000 : undefined;
    const skipOnFailure = stepData.skip_on_failure === true;
    const outputVariable: string | undefined = stepData.output_variable ?? undefined;
    const outputFile: string | undefined = stepData.output_file ?? undefined;

    return new Task({
      name: stepData.name ?? agent.name ?? agentId,
      execute: async (input: any, context: WorkflowContext) => {
        const prompt = action
          ? substituteWorkflowVariables(action, context.metadata, input, context.input)
          : typeof input === 'string' ? input : JSON.stringify(input);
        return agent.chat(prompt);
      },
      onError: skipOnFailure ? 'skip' : (maxRetries && maxRetries > 0 ? 'retry' : 'fail'),
      maxRetries,
      execution: retryDelay !== undefined ? { retryDelay } : undefined,
      output: outputVariable || outputFile ? { outputVariable, outputFile } : undefined,
    });
  }

  private requireAgent(agentId: string): AgentLikeStep {
    const agent = this._agents[agentId];
    if (!agent) throw new Error(`Agent '${agentId}' not defined in agents section`);
    return agent;
  }

  /** Python: _parse_agent_step */
  parseAgentStep(stepData: Record<string, any>): Task {
    const agentId = String(stepData.agent);
    return this.agentTask(this.requireAgent(agentId), agentId, stepData);
  }

  /** Python: _parse_include_step — `include: name` or `include: {recipe, input}`. */
  parseIncludeStep(stepData: Record<string, any>): Include {
    const cfg = stepData.include;
    if (typeof cfg === 'string') return new Include(cfg, null, null);
    const recipe: string = cfg?.recipe ?? '';
    const input: string | null = cfg?.input ?? null;
    const workflow = cfg?.workflow && typeof cfg.workflow === 'object' ? cfg.workflow : null;
    return new Include(recipe, workflow, input);
  }

  /** Python: _parse_if_step */
  parseIfStep(stepData: Record<string, any>): If {
    const cfg = stepData.if ?? {};
    const condition: string = cfg.condition ?? '';
    const thenSteps = this.parseSteps(Array.isArray(cfg.then) ? cfg.then : []);
    const elseSteps = this.parseSteps(Array.isArray(cfg.else) ? cfg.else : []);
    return new If(condition, thenSteps, elseSteps.length > 0 ? elseSteps : null);
  }

  /** Python: _parse_route_step — values are agent ids (or lists of ids); unknown ids are dropped. */
  parseRouteStep(stepData: Record<string, any>): Route {
    const cfg = stepData.route ?? {};
    const routes: Record<string, FlowStep[]> = {};
    for (const [key, target] of Object.entries<any>(cfg)) {
      const ids: any[] = Array.isArray(target) ? target : [target];
      const steps: FlowStep[] = [];
      for (const entry of ids) {
        if (typeof entry === 'string' && this._agents[entry]) {
          steps.push(this.agentTask(this._agents[entry], entry, { agent: entry }));
        } else if (entry && typeof entry === 'object') {
          const parsed = this.parseSingleStep(entry);
          if (parsed) steps.push(parsed);
        }
      }
      if (Array.isArray(target) || steps.length > 0) routes[key] = steps;
    }
    return new Route(routes);
  }

  /**
   * Python: _parse_parallel_step — a list of `{agent, action}` items.
   * TS extension: `parallel: {steps: [...], max_workers, on_failure}`.
   */
  parseParallelStep(stepData: Record<string, any>): Parallel {
    const cfg = stepData.parallel;
    let items: any[];
    let maxWorkers: number | null = null;
    let onFailure: ParallelOnFailure = 'partial_ok';
    if (Array.isArray(cfg)) {
      items = cfg;
    } else if (cfg && typeof cfg === 'object') {
      items = Array.isArray(cfg.steps) ? cfg.steps : [];
      if (cfg.max_workers !== undefined && cfg.max_workers !== null) {
        const n = Number(cfg.max_workers);
        maxWorkers = Number.isFinite(n) ? n : null;
      }
      if (cfg.on_failure) onFailure = cfg.on_failure;
    } else {
      items = [];
    }

    const steps: FlowStep[] = [];
    for (const item of items) {
      if (item && typeof item === 'object' && 'agent' in item) {
        const agentId = String(item.agent);
        if (this._agents[agentId]) steps.push(this.agentTask(this._agents[agentId], agentId, item));
      } else if (item && typeof item === 'object') {
        const parsed = this.parseSingleStep(item);
        if (parsed) steps.push(parsed);
      }
    }
    return new Parallel(steps, maxWorkers, onFailure);
  }

  /** Python: _parse_loop_step — supports agent / step / steps / include forms. */
  parseLoopStep(stepData: Record<string, any>): Loop {
    const cfg = stepData.loop ?? {};
    const over: string | undefined = cfg.over ?? undefined;
    const fromCsv: string | undefined = cfg.from_csv ?? undefined;
    const fromFile: string | undefined = cfg.from_file ?? undefined;
    const varName: string = cfg.var_name ?? 'item';
    const parallel = cfg.parallel === true;
    let maxWorkers: number | undefined;
    if (cfg.max_workers !== undefined && cfg.max_workers !== null) {
      const n = Number(cfg.max_workers);
      maxWorkers = Number.isFinite(n) ? n : undefined;
    }
    const outputVariable: string | undefined = stepData.output_variable ?? undefined;
    const loopConfig = { over, fromCsv, fromFile, varName, parallel, maxWorkers, outputVariable };

    const nestedSteps = stepData.steps ?? cfg.steps;
    if (Array.isArray(nestedSteps) && nestedSteps.length > 0) {
      const parsed = this.parseSteps(nestedSteps);
      if (parsed.length > 0) return new Loop(parsed, loopConfig);
    }

    let stepToRun: FlowStep | null = null;

    if (typeof stepData.agent === 'string' && this._agents[stepData.agent]) {
      stepToRun = this.agentTask(this._agents[stepData.agent], stepData.agent, stepData);
    }

    if ('step' in stepData) {
      const def = stepData.step;
      if (def && typeof def === 'object' && 'agent' in def && this._agents[def.agent]) {
        stepToRun = this.agentTask(this._agents[def.agent], def.agent, def);
      } else if (typeof def === 'string' && this._agents[def]) {
        stepToRun = this.agentTask(this._agents[def], def, { agent: def });
      }
    }

    if (typeof cfg.step === 'string' && this._agents[cfg.step]) {
      stepToRun = this.agentTask(this._agents[cfg.step], cfg.step, { agent: cfg.step });
    }

    if (stepToRun === null && 'include' in stepData) {
      const inc = stepData.include;
      if (typeof inc === 'string') stepToRun = new Include(inc);
      else if (inc && typeof inc === 'object') stepToRun = new Include(inc.recipe ?? '', null, inc.input ?? null);
    }

    if (stepToRun === null) {
      throw new Error('Loop step requires an agent, include, or steps');
    }
    return new Loop(stepToRun, loopConfig);
  }

  /** Python: _parse_repeat_step — `until` string means "previous output contains". */
  parseRepeatStep(stepData: Record<string, any>): Repeat {
    const cfg = stepData.repeat ?? {};
    const agentId = stepData.agent;
    if (typeof agentId === 'string' && this._agents[agentId]) {
      const task = this.agentTask(this._agents[agentId], agentId, stepData);
      const until = cfg.until;
      const maxIterations = cfg.max_iterations !== undefined ? Number(cfg.max_iterations) : 5;
      const condition = typeof until === 'string'
        ? this.createConditionFromString(until)
        : (typeof until === 'function' ? until : undefined);
      return new Repeat(task, { until: condition, maxIterations });
    }
    throw new Error('Repeat step requires an agent');
  }

  /** Python: _create_condition_from_string */
  private createConditionFromString(conditionStr: string): (ctx: RepeatContext) => boolean {
    const needle = conditionStr.toLowerCase();
    return (ctx: RepeatContext) => String(ctx.lastResult).toLowerCase().includes(needle);
  }

  /**
   * Python: _parse_generic_step — a step with neither agent nor pattern.
   * A `tool:` from the registry is executed; otherwise running the step throws.
   */
  parseGenericStep(stepData: Record<string, any>): Task {
    const name: string = stepData.name ?? 'step';
    const action: string = stepData.action ?? '';
    const toolName: string | undefined = stepData.tool;
    const tool = toolName ? this.toolRegistry[toolName] : undefined;

    return new Task({
      name,
      execute: async (input: any, context: WorkflowContext) => {
        if (tool) {
          const arg = action ? substituteWorkflowVariables(action, context.metadata, input, context.input) : input;
          return tool(arg, context);
        }
        throw new Error(
          `Step '${name}' has no agent, tool or pattern to execute` +
          (action ? ` (action: '${action.slice(0, 60)}')` : '')
        );
      },
    });
  }
}
