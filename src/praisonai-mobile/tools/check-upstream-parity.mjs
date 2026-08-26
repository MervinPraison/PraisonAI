/**
 * Does the real praisonai-ts `Agent` still satisfy the interface the mobile
 * engine is written against?
 *
 * `engines/src/praisonai-ts/agent-api.ts` declares that coupling structurally
 * rather than importing `praisonai`, which is what keeps the engine tests free
 * of a provider, a network and an API key. The cost of that choice is that
 * nothing would notice upstream drifting -- `streamEvents` gaining a required
 * parameter, `lastStopReason` being renamed -- until a device failed at
 * runtime. This is the check that pays that cost back.
 *
 * It is deliberately NOT part of `npm test`: it needs the sibling praisonai-ts
 * checkout, which is present in the monorepo and absent in a standalone clone.
 * Run it via `npm run check:upstream`. If the sibling is missing it SKIPS
 * loudly rather than passing quietly -- a check that silently stops covering
 * anything is worse than no check.
 */
import { execFile } from "node:child_process";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { access } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { promisify } from "node:util";

const run = promisify(execFile);

const UPSTREAM = resolve(import.meta.dirname, "../../praisonai-ts");
const AGENT_SRC = join(UPSTREAM, "src/agent/simple.ts");
const AGENT_API = resolve(import.meta.dirname, "../engines/src/praisonai-ts/agent-api.ts");

const exists = async (p) => {
  try {
    await access(p);
    return true;
  } catch {
    return false;
  }
};

if (!(await exists(AGENT_SRC))) {
  console.log(`upstream-parity: SKIPPED -- no praisonai-ts at ${UPSTREAM}`);
  console.log("  (expected in a standalone clone; run this from the monorepo)");
  process.exit(0);
}

if (!(await exists(join(UPSTREAM, "node_modules")))) {
  // tsc has to resolve praisonai-ts's OWN imports to typecheck its Agent, so
  // without its dependencies this cannot run. Skipped loudly rather than
  // failed: a missing install is an environment problem, and reporting it as
  // upstream drift would send someone looking in the wrong file entirely.
  console.log("upstream-parity: SKIPPED -- praisonai-ts has no node_modules");
  console.log(`  run: (cd ${UPSTREAM} && npm install)`);
  process.exit(0);
}

const dir = await mkdtemp(join(tmpdir(), "praison-parity-"));
const file = join(dir, "parity.ts");

// The whole check is one assignment. If the real class no longer satisfies the
// structural interface, tsc reports exactly which member diverged.
await writeFile(
  file,
  [
    `import { Agent } from ${JSON.stringify(AGENT_SRC.replace(/\.ts$/, ""))};`,
    `import type { PraisonAgent } from ${JSON.stringify(AGENT_API.replace(/\.ts$/, ""))};`,
    "",
    "declare const real: Agent;",
    "const asPort: PraisonAgent = real;",
    "export const ok = asPort;",
    "",
  ].join("\n"),
);

try {
  await run("npx", [
    "tsc", "--noEmit", "--strict", "--skipLibCheck",
    "--target", "es2022", "--module", "esnext", "--moduleResolution", "bundler",
    file,
  ], { cwd: UPSTREAM });
  console.log("upstream-parity: the real Agent still satisfies PraisonAgent");
} catch (error) {
  console.error("upstream-parity: FAILED -- praisonai-ts has drifted from agent-api.ts\n");
  console.error(error.stdout || error.message);
  console.error(
    "\n  Fix agent-api.ts to match upstream, then re-check the mappings in\n" +
    "  engines/src/praisonai-ts/engine.ts that depend on the changed member.",
  );
  process.exitCode = 1;
} finally {
  await rm(dir, { recursive: true, force: true });
}
