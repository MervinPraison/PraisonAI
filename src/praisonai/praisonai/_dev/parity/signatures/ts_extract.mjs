#!/usr/bin/env node
// TypeScript signature extractor for the signature parity checker.
//
// Uses the TypeScript compiler API (no type-checker, no emit) to read interface
// members, constructor fallbacks (`config.x ?? v`, `config.x || v`, ternaries,
// destructuring defaults) and method parameters. Output follows the shared
// schema documented in schema.py.
//
// Usage:
//   node ts_extract.mjs --repo-root <repo> [--ts-root src/praisonai-ts/src] [--targets '<json>' | < targets.json]
//
// A target: { "surface": key, "file": "agent/simple.ts", "kind": "interface"|"method",
//             "name": "SimpleAgentConfig", "ctorClass": "Agent" (optional), "cls": "Agent" (optional) }
//
// `typescript` is resolved from PARITY_TS_NODE_MODULES when that env var is set
// (explicit override: if it does not resolve there we fail rather than silently
// falling back), else <repo>/src/praisonai-ts/node_modules, else normal Node
// resolution. On any tooling failure: message on stderr, exit 2, never an
// empty result with exit 0.

import { createRequire } from 'node:module';
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const DEFAULT_TS_ROOT = 'src/praisonai-ts/src';

function fail(message) {
  process.stderr.write(`ts_extract: ${message}\n`);
  process.exit(2);
}

function parseArgs(argv) {
  const opts = { repoRoot: null, tsRoot: DEFAULT_TS_ROOT, targets: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--repo-root') opts.repoRoot = argv[++i];
    else if (a === '--ts-root') opts.tsRoot = argv[++i];
    else if (a === '--targets') opts.targets = argv[++i];
    else if (a.startsWith('--')) fail(`unknown option ${a}`);
    else opts.targets = a;
  }
  if (!opts.repoRoot) fail('--repo-root is required');
  return opts;
}

function loadTypescript(repoRoot) {
  const require = createRequire(import.meta.url);
  const tried = [];
  const override = process.env.PARITY_TS_NODE_MODULES;
  const candidates = override
    ? [path.join(override, 'typescript')]
    : [path.join(repoRoot, 'src', 'praisonai-ts', 'node_modules', 'typescript'), 'typescript'];
  for (const candidate of candidates) {
    try {
      const ts = require(candidate);
      if (!ts || typeof ts.createSourceFile !== 'function') throw new Error('module has no createSourceFile');
      return ts;
    } catch (err) {
      tried.push(`${candidate}: ${err && err.message ? err.message.split('\n')[0] : err}`);
    }
  }
  fail(
    `cannot load the "typescript" module.\n` +
      `  tried:\n    ${tried.join('\n    ')}\n` +
      (override
        ? `  PARITY_TS_NODE_MODULES=${override} is set and does not contain typescript/.`
        : `  Install praisonai-ts dependencies (pnpm install in src/praisonai-ts) or set PARITY_TS_NODE_MODULES.`)
  );
}

function readTargets(opts) {
  let text = opts.targets;
  if (text == null) {
    try {
      text = readFileSync(0, 'utf8');
    } catch (err) {
      fail(`no targets given and stdin unreadable: ${err.message}`);
    }
  }
  let targets;
  try {
    targets = JSON.parse(text);
  } catch (err) {
    fail(`targets are not valid JSON: ${err.message}`);
  }
  if (!Array.isArray(targets)) fail('targets must be a JSON array');
  return targets;
}

// ------------------------------------------------------------------ type class

function splitTopLevel(text, sep) {
  const parts = [];
  let depth = 0;
  let quote = null;
  let current = '';
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quote) {
      current += ch;
      if (ch === '\\' && i + 1 < text.length) { current += text[++i]; }
      else if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'" || ch === '`') {
      quote = ch; current += ch;
    } else if ('([{<'.includes(ch)) {
      depth++; current += ch;
    } else if (')]}>'.includes(ch)) {
      depth = Math.max(0, depth - 1); current += ch;
    } else if (depth === 0 && text.startsWith(sep, i)) {
      parts.push(current); current = ''; i += sep.length - 1;
    } else {
      current += ch;
    }
  }
  parts.push(current);
  return parts;
}

function hasTopLevelArrow(text) {
  let depth = 0; let quote = null;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quote) { if (ch === '\\') i++; else if (ch === quote) quote = null; continue; }
    if (ch === '"' || ch === "'" || ch === '`') quote = ch;
    else if ('([{<'.includes(ch)) depth++;
    else if (')]}>'.includes(ch)) depth = Math.max(0, depth - 1);
    else if (depth === 0 && text.startsWith('=>', i)) return true;
  }
  return false;
}

function singleTypeClass(raw) {
  const t = raw.trim();
  if (!t) return 'unknown';
  if (hasTopLevelArrow(t) || t === 'Function') return 'callable';
  if (/^['"`]/.test(t)) return 'string';
  if (/^-?\d/.test(t)) return 'number';
  if (t === 'true' || t === 'false') return 'boolean';
  if (t === 'string' || t === 'symbol') return 'string';
  if (t === 'number' || t === 'bigint') return 'number';
  if (t === 'boolean') return 'boolean';
  if (t === 'any' || t === 'unknown' || t === 'void' || t === 'never' || t === 'undefined' || t === 'null') return 'unknown';
  if (t.endsWith('[]') || /^(Array|ReadonlyArray|Set|Iterable)</.test(t) || t.startsWith('[')) return 'array';
  if (/^(Record|Map|Partial|Readonly|Pick|Omit|Promise)</.test(t) || t.startsWith('{') || t === 'object') return 'object';
  if (/^[A-Z]/.test(t)) return 'object';
  return 'unknown';
}

function typeClass(text) {
  const t = (text || '').trim();
  if (!t) return 'unknown';
  if (hasTopLevelArrow(t)) return 'callable';
  const members = splitTopLevel(t, '|').map((s) => s.trim()).filter((s) => s && s !== 'undefined' && s !== 'null');
  if (members.length === 0) return 'unknown';
  const classes = new Set(members.map(singleTypeClass));
  return classes.size === 1 ? [...classes][0] : 'union';
}

// ------------------------------------------------------------------- defaults

function compact(text) { return text.replace(/\s+/g, ' ').trim(); }

function literalOf(ts, node, sf) {
  if (!node) return { default: null, default_kind: null };
  if (ts.isParenthesizedExpression(node)) return literalOf(ts, node.expression, sf);
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return { default: node.text, default_kind: 'literal' };
  if (ts.isNumericLiteral(node)) return { default: Number(node.text), default_kind: 'literal' };
  if (ts.isPrefixUnaryExpression(node) && node.operator === ts.SyntaxKind.MinusToken && ts.isNumericLiteral(node.operand)) {
    return { default: -Number(node.operand.text), default_kind: 'literal' };
  }
  if (node.kind === ts.SyntaxKind.TrueKeyword) return { default: true, default_kind: 'literal' };
  if (node.kind === ts.SyntaxKind.FalseKeyword) return { default: false, default_kind: 'literal' };
  if (node.kind === ts.SyntaxKind.NullKeyword) return { default: null, default_kind: 'literal' };
  if (ts.isArrayLiteralExpression(node) && node.elements.length === 0) return { default: [], default_kind: 'literal' };
  if (ts.isObjectLiteralExpression(node) && node.properties.length === 0) return { default: {}, default_kind: 'literal' };
  return { default: compact(node.getText(sf)), default_kind: 'expr' };
}

function isConfigAccess(ts, node, paramName) {
  return ts.isPropertyAccessExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === paramName;
}

// Flatten `a ?? b ?? c` / `a || b || c` into operands (left-assoc parse tree).
function flattenChain(ts, node, opKind) {
  if (ts.isBinaryExpression(node) && node.operatorToken.kind === opKind) {
    return [...flattenChain(ts, node.left, opKind), node.right];
  }
  return [node];
}

// Pick the constructor parameter that carries the options object: the one whose
// type annotation names the target interface, else the first object-typed one,
// else the first parameter. Anything else is a positional parameter in its own
// right (e.g. `constructor(message: string, options: FooOptions = {})`), which
// `positionalCtorParams` reports so a Python positional argument can match it.
function pickConfigParam(ts, ctor, sf, interfaceName) {
  const params = ctor.parameters;
  if (!params.length) return { config: undefined, positional: [] };
  let idx = -1;
  if (interfaceName) {
    idx = params.findIndex((prm) => prm.type && compact(prm.type.getText(sf)).includes(interfaceName));
  }
  if (idx < 0) {
    idx = params.findIndex((prm) => {
      if (!prm.type) return false;
      const t = compact(prm.type.getText(sf));
      return /^\{|Options$|Config$|Record</.test(t);
    });
  }
  if (idx < 0) idx = 0;
  return { config: params[idx], positional: params.filter((_, i) => i !== idx) };
}

function positionalCtorParams(ts, ctor, sf, positional) {
  return positional.map((prm) => {
    const name = prm.name.getText(sf);
    const typeText = prm.type ? compact(prm.type.getText(sf)) : 'any';
    const d = prm.initializer
      ? literalOf(ts, prm.initializer, sf)
      : { default: null, default_kind: null };
    return {
      name,
      canonical: name,
      kind: 'positional',
      required: !prm.questionToken && !prm.initializer,
      default: d.default,
      default_kind: d.default_kind,
      type_text: typeText,
      type_class: typeClass(typeText),
    };
  });
}

function collectCtorDefaults(ts, cls, sf, interfaceName) {
  const ctor = cls.members.find((m) => ts.isConstructorDeclaration(m) && m.body);
  if (!ctor) return { defaults: new Map(), line: null, positional: [] };
  const { config, positional } = pickConfigParam(ts, ctor, sf, interfaceName);
  const info = collectDefaultsFrom(ts, ctor, sf, config);
  // Report the options parameter under its own name too: its interface members are
  // flattened below, but TypeScript really does expose a parameter of that name, so
  // a Python parameter called e.g. `config` matches it instead of reading as missing.
  const selfNamed = config ? positionalCtorParams(ts, ctor, sf, [config]) : [];
  info.positional = [...positionalCtorParams(ts, ctor, sf, positional), ...selfNamed];
  return info;
}

// Defaults read from `<param>.x ?? v`, `<param>.x || v`, ternaries on
// `<param>.x`, and destructuring `{ x = v } = <param>` inside a function body.
// Used for constructors (config object) and for methods that take an options
// object (see extractMethod), so both surfaces report defaults the same way.
function collectDefaultsFrom(ts, fnLike, sf, param) {
  const ctor = fnLike;
  if (!ctor || !ctor.body) return { defaults: new Map(), line: null };
  const paramName = param && ts.isIdentifier(param.name) ? param.name.text : 'config';
  const defaults = new Map();
  const record = (name, value) => { if (!defaults.has(name)) defaults.set(name, value); };

  const visit = (node) => {
    if (ts.isBinaryExpression(node)) {
      const kind = node.operatorToken.kind;
      if (kind === ts.SyntaxKind.QuestionQuestionToken || kind === ts.SyntaxKind.BarBarToken) {
        const operands = flattenChain(ts, node, kind);
        if (isConfigAccess(ts, operands[0], paramName) && operands.length > 1) {
          const name = operands[0].name.text;
          if (operands.length === 2) record(name, literalOf(ts, operands[1], sf));
          else record(name, { default: compact(operands.slice(1).map((o) => o.getText(sf)).join(kind === ts.SyntaxKind.QuestionQuestionToken ? ' ?? ' : ' || ')), default_kind: 'expr' });
        }
      }
    } else if (ts.isConditionalExpression(node)) {
      const cond = node.condition;
      if (isConfigAccess(ts, cond, paramName)) {
        record(cond.name.text, literalOf(ts, node.whenFalse, sf));
      } else if (ts.isBinaryExpression(cond) && isConfigAccess(ts, cond.left, paramName)) {
        const rhs = cond.right.getText(sf);
        const op = cond.operatorToken.kind;
        const isUndef = rhs === 'undefined' || rhs === 'null';
        if (isUndef && (op === ts.SyntaxKind.ExclamationEqualsEqualsToken || op === ts.SyntaxKind.ExclamationEqualsToken)) {
          record(cond.left.name.text, literalOf(ts, node.whenFalse, sf));
        } else if (isUndef && (op === ts.SyntaxKind.EqualsEqualsEqualsToken || op === ts.SyntaxKind.EqualsEqualsToken)) {
          record(cond.left.name.text, literalOf(ts, node.whenTrue, sf));
        }
      }
    } else if (ts.isVariableDeclaration(node) && node.initializer && ts.isIdentifier(node.initializer)
      && node.initializer.text === paramName && ts.isObjectBindingPattern(node.name)) {
      for (const el of node.name.elements) {
        const key = el.propertyName ? el.propertyName.getText(sf) : el.name.getText(sf);
        if (el.initializer) record(key, literalOf(ts, el.initializer, sf));
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(ctor.body);
  return { defaults, line: lineOf(sf, ctor) };
}

// ------------------------------------------------------------------ extraction

function lineOf(sf, node) { return sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1; }

function findAll(ts, root, predicate) {
  const found = [];
  const visit = (n) => { if (predicate(n)) found.push(n); ts.forEachChild(n, visit); };
  visit(root);
  return found;
}

function enclosingClassName(ts, node) {
  let p = node.parent;
  while (p) { if (ts.isClassDeclaration(p)) return p.name ? p.name.text : null; p = p.parent; }
  return null;
}

function extractInterface(ts, sf, target, location) {
  const decl = findAll(ts, sf, (n) => ts.isInterfaceDeclaration(n) && n.name.text === target.name)[0];
  if (!decl) return { error: `${target.surface}: interface ${target.name} not found in ${target.file}` };
  let ctorInfo = { defaults: new Map(), line: null };
  const extra = {};
  if (target.ctorClass) {
    const cls = findAll(ts, sf, (n) => ts.isClassDeclaration(n) && n.name && n.name.text === target.ctorClass)[0];
    if (!cls) return { error: `${target.surface}: ctor class ${target.ctorClass} not found in ${target.file}` };
    ctorInfo = collectCtorDefaults(ts, cls, sf, target.name);
    if (ctorInfo.line) extra.ctor_location = `${location}:${ctorInfo.line}`;
  }
  if (decl.heritageClauses && decl.heritageClauses.length) {
    extra.extends = decl.heritageClauses.flatMap((h) => h.types.map((t) => compact(t.getText(sf))));
  }
  // Positional constructor parameters come first: they precede the options object.
  const params = [...(ctorInfo.positional || [])];
  for (const m of decl.members) {
    if (!ts.isPropertySignature(m) && !ts.isMethodSignature(m)) continue;
    const name = m.name.getText(sf);
    const optional = !!m.questionToken;
    const typeText = ts.isMethodSignature(m)
      ? compact(m.getText(sf).replace(/^[^(]*/, '')) // method signature -> its "(params): ret" part
      : (m.type ? compact(m.type.getText(sf)) : 'any');
    const d = ctorInfo.defaults.get(name) || { default: null, default_kind: null };
    params.push({
      name,
      canonical: name,
      kind: 'property',
      required: !optional,
      default: d.default,
      default_kind: d.default_kind,
      type_text: typeText,
      type_class: ts.isMethodSignature(m) ? 'callable' : typeClass(typeText),
    });
  }
  return {
    surface: target.surface,
    language: 'typescript',
    location: `${location}:${lineOf(sf, decl)}`,
    params,
    extra,
  };
}

// `name: constructor` addresses a class's constructor declaration, which has no
// `name` node of its own. Used for ported classes whose constructor takes plain
// positional parameters and no options interface (e.g. `constructor(stateFile:
// string | null = null)`), so they are checked like any other method.
const CONSTRUCTOR_NAME = 'constructor';

function extractMethod(ts, sf, target, location) {
  const wantsCtor = target.name === CONSTRUCTOR_NAME;
  const matches = findAll(ts, sf, (n) =>
    wantsCtor
      ? ts.isConstructorDeclaration(n) && (!target.cls || enclosingClassName(ts, n) === target.cls)
      : (ts.isMethodDeclaration(n) || ts.isFunctionDeclaration(n)) && n.name && n.name.getText(sf) === target.name
        && (!target.cls || enclosingClassName(ts, n) === target.cls));
  // For a constructor the implementation is the real signature: TypeScript forbids
  // parameter initializers on overload signatures, so a bodyless match would report
  // every parameter as having no default. Named methods keep the long-standing
  // first-match rule: their leading overload is the documented public signature
  // (AgentTeam.start declares `options?: AgentTeamStartOptions` there and widens to
  // a union type alias in the implementation, which has no interface to flatten).
  const decl = wantsCtor ? (matches.find((m) => m.body) || matches[0]) : matches[0];
  if (!decl) {
    if (wantsCtor) {
      if (target.cls
        && !findAll(ts, sf, (n) => ts.isClassDeclaration(n) && n.name && n.name.text === target.cls)[0]) {
        return { error: `${target.surface}: class ${target.cls} not found in ${target.file}` };
      }
      return {
        error: target.cls
          ? `${target.surface}: class ${target.cls} declares no constructor in ${target.file}`
          : `${target.surface}: no class in ${target.file} declares a constructor`,
      };
    }
    const where = target.cls ? `${target.cls}.${target.name}` : target.name;
    return { error: `${target.surface}: method ${where} not found in ${target.file}` };
  }
  const params = decl.parameters.map((p) => {
    const d = literalOf(ts, p.initializer, sf);
    const rest = !!p.dotDotDotToken;
    const optional = rest || !!p.questionToken || !!p.initializer;
    const typeText = p.type ? compact(p.type.getText(sf)) : 'any';
    return {
      name: p.name.getText(sf),
      canonical: p.name.getText(sf),
      kind: rest ? 'var_positional' : 'positional',
      required: !optional,
      default: d.default,
      default_kind: d.default_kind,
      type_text: typeText,
      type_class: typeClass(typeText),
    };
  });
  const extra = {};
  // An options object (`options?: FooOptions`) declared as an interface in the
  // same file is flattened: its members count as parameters of the method, the
  // way Python spells them out as keyword arguments. Defaults are read from
  // `options.x ?? v` / `options?.x ?? v` in the method body.
  const flattened = [];
  for (const p of decl.parameters) {
    if (!p.type || !ts.isTypeReferenceNode(p.type) || !ts.isIdentifier(p.type.typeName)) continue;
    const ifaceName = p.type.typeName.text;
    const iface = findAll(ts, sf, (n) => ts.isInterfaceDeclaration(n) && n.name.text === ifaceName)[0];
    if (!iface) continue;
    const optName = p.name.getText(sf);
    const optIsOptional = !!p.questionToken || !!p.initializer;
    const defaults = collectDefaultsFrom(ts, decl, sf, p).defaults;
    for (const m of iface.members) {
      if (!ts.isPropertySignature(m) && !ts.isMethodSignature(m)) continue;
      const name = m.name.getText(sf);
      const typeText = ts.isMethodSignature(m)
        ? compact(m.getText(sf).replace(/^[^(]*/, ''))
        : (m.type ? compact(m.type.getText(sf)) : 'any');
      const d = defaults.get(name) || { default: null, default_kind: null };
      flattened.push({
        name,
        canonical: name,
        kind: 'property',
        required: optIsOptional ? false : !m.questionToken,
        default: d.default,
        default_kind: d.default_kind,
        type_text: typeText,
        type_class: ts.isMethodSignature(m) ? 'callable' : typeClass(typeText),
        via: optName,
      });
    }
    (extra.options_interfaces = extra.options_interfaces || []).push(`${optName}: ${ifaceName}`);
  }
  params.push(...flattened);
  const cls = enclosingClassName(ts, decl);
  if (cls) extra.resolved_class = cls;
  return {
    surface: target.surface,
    language: 'typescript',
    location: `${location}:${lineOf(sf, decl)}`,
    params,
    extra,
  };
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(opts.repoRoot);
  const ts = loadTypescript(repoRoot);
  const targets = readTargets(opts);
  const tsRoot = path.join(repoRoot, opts.tsRoot);
  const results = [];
  const errors = [];
  const cache = new Map();

  for (const target of targets) {
    for (const key of ['surface', 'file', 'kind', 'name']) {
      if (!target[key]) errors.push(`target ${JSON.stringify(target)} is missing "${key}"`);
    }
    if (errors.length) continue;
    const file = path.join(tsRoot, target.file);
    if (!existsSync(file)) { errors.push(`${target.surface}: file not found: ${file}`); continue; }
    if (!cache.has(file)) {
      cache.set(file, ts.createSourceFile(file, readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true));
    }
    const sf = cache.get(file);
    const location = path.relative(repoRoot, file).split(path.sep).join('/');
    const out = target.kind === 'interface'
      ? extractInterface(ts, sf, target, location)
      : target.kind === 'method'
        ? extractMethod(ts, sf, target, location)
        : { error: `${target.surface}: unknown kind "${target.kind}" (expected interface|method)` };
    if (out.error) errors.push(out.error); else results.push(out);
  }

  if (errors.length) fail(`${errors.length} surface(s) could not be extracted:\n  ${errors.join('\n  ')}`);
  if (targets.length === 0) fail('no targets given: nothing was extracted');
  process.stdout.write(JSON.stringify(results, null, 2) + '\n');
}

main();
