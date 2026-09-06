#!/usr/bin/env node
// Public-member lister for the method-inventory parity check.
//
// The signature checker compares one function per surface -- almost always
// `__init__`. Everything else a class offers is invisible to it, which is how
// `Agent.execute(task)` (Python: run THIS task) and `execute(previousResult?)`
// (TypeScript: run the agent's OWN instructions) sat side by side under a green
// gate. This script lists what a TypeScript class publicly offers so the
// comparator can hold it against the Python class.
//
// It reports NAMES, not signatures. A name present on both sides says only that
// `x.foo(...)` resolves in both SDKs.
//
// Usage:
//   node ts_members.mjs --repo-root <repo> [--ts-root src/praisonai-ts/src] [--targets '<json>' | < targets.json]
//
// A target: { "cls": "Agent", "file": "agent/simple.ts" }
//
// Output: JSON array of { cls, file, location, found, members[], bases[], implements[] }.
// `found: false` (class absent from that file) is DATA, not an error: a missing
// class is exactly the finding the caller is looking for. Only a broken
// toolchain -- no typescript, unreadable target list -- exits 2.
//
// Limit, stated so it is not mistaken for a guarantee: members inherited from a
// base class declared in another file are not listed. `bases` names every
// `extends` clause so the caller can say so out loud rather than silently
// reporting an inherited member as missing. `implements` is reported
// separately: it contributes no members, so it needs no such caveat.

import { createRequire } from 'node:module';
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const DEFAULT_TS_ROOT = 'src/praisonai-ts/src';

function fail(message) {
  process.stderr.write(`ts_members: ${message}\n`);
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

// ---------------------------------------------------------------- extraction

function hasModifier(ts, node, kind) {
  return !!(node.modifiers || []).find((m) => m.kind === kind);
}

// `#secret()` and `private foo()` are unreachable from outside the class, and a
// leading underscore is the convention both SDKs use for "internal". None of
// them is public API, so none is compared.
function isPublic(ts, member, name) {
  if (hasModifier(ts, member, ts.SyntaxKind.PrivateKeyword)) return false;
  if (hasModifier(ts, member, ts.SyntaxKind.ProtectedKeyword)) return false;
  if (member.name && ts.isPrivateIdentifier(member.name)) return false;
  return !name.startsWith('_');
}

// A callable member: a method, a getter/setter (a Python method may legitimately
// be a TypeScript accessor), or a property initialised to a function.
function memberKind(ts, member) {
  if (ts.isMethodDeclaration(member)) return 'method';
  if (ts.isGetAccessorDeclaration(member)) return 'getter';
  if (ts.isSetAccessorDeclaration(member)) return 'setter';
  if (ts.isPropertyDeclaration(member) && member.initializer
      && (ts.isArrowFunction(member.initializer) || ts.isFunctionExpression(member.initializer))) {
    return 'method';
  }
  return null;
}

function listMembers(ts, sf, cls, location) {
  const members = [];
  const seen = new Set();
  for (const member of cls.members) {
    const kind = memberKind(ts, member);
    if (!kind || !member.name) continue;
    const name = member.name.getText(sf);
    if (name === 'constructor' || !isPublic(ts, member, name)) continue;
    if (seen.has(name)) continue;   // overloads declare the same name twice
    seen.add(name);
    members.push({
      name,
      kind,
      is_static: hasModifier(ts, member, ts.SyntaxKind.StaticKeyword),
      line: sf.getLineAndCharacterOfPosition(member.getStart(sf)).line + 1,
    });
  }
  // `extends` brings members with it; `implements` brings none. Reporting the
  // two together made every `class Knowledge implements KnowledgeStoreProtocol`
  // carry an "inherited members are not listed" caveat that did not apply.
  const bases = [];
  const implemented = [];
  for (const clause of cls.heritageClauses || []) {
    const into = clause.token === ts.SyntaxKind.ExtendsKeyword ? bases : implemented;
    for (const type of clause.types) into.push(type.expression.getText(sf));
  }
  return {
    found: true,
    location: `${location}:${sf.getLineAndCharacterOfPosition(cls.getStart(sf)).line + 1}`,
    members,
    bases,
    implements: implemented,
  };
}

function findClass(ts, sf, name) {
  let found = null;
  const walk = (node) => {
    if (found) return;
    if (ts.isClassDeclaration(node) && node.name && node.name.text === name) {
      found = node;
      return;
    }
    ts.forEachChild(node, walk);
  };
  walk(sf);
  return found;
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(opts.repoRoot);
  const ts = loadTypescript(repoRoot);
  const targets = readTargets(opts);
  const tsRoot = path.join(repoRoot, opts.tsRoot);
  const cache = new Map();
  const results = [];

  for (const target of targets) {
    for (const key of ['cls', 'file']) {
      if (!target[key]) fail(`target ${JSON.stringify(target)} is missing "${key}"`);
    }
    const file = path.join(tsRoot, target.file);
    const location = path.relative(repoRoot, file).split(path.sep).join('/');
    const base = { cls: target.cls, file: target.file, location, found: false, members: [], bases: [] };
    if (!existsSync(file)) {
      results.push({ ...base, absent: `file not found: ${target.file}` });
      continue;
    }
    if (!cache.has(file)) {
      cache.set(file, ts.createSourceFile(file, readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true));
    }
    const sf = cache.get(file);
    const cls = findClass(ts, sf, target.cls);
    if (!cls) {
      results.push({ ...base, absent: `class ${target.cls} not declared in ${target.file}` });
      continue;
    }
    results.push({ cls: target.cls, file: target.file, ...listMembers(ts, sf, cls, location) });
  }

  process.stdout.write(JSON.stringify(results, null, 2) + '\n');
}

main();
