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
 *
 * It does NOT need praisonai-ts's dependencies installed, which matters
 * because they do not install cleanly (`npm install` there fails with an
 * ERESOLVE peer conflict on bedrock-agentcore -> @strands-agents/sdk). Every
 * member this checks -- `streamEvents`, `lastStopReason` and their types -- is
 * declared locally in simple.ts, so unresolved third-party imports degrade
 * only unrelated members. That is asserted, not assumed: with praisonai-ts's
 * node_modules moved aside, injecting a member the real Agent lacks still
 * produces `TS2741 Property 'renamedUpstream' is missing in type 'Agent'`.
 *
 * Consequently tsc runs from THIS package (which has typescript) and errors
 * outside the generated parity file are ignored -- they are unresolved-module
 * and implicit-any noise from praisonai-ts's own sources, not drift.
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
/** The structural interface the real Agent must satisfy.
 *
 *  Overridable so the CLI can be driven against a deliberately-incompatible
 *  interface in a test. Two mutations survived here -- `process.exitCode = 1`
 *  becoming 0, so drift is PRINTED and the job passes anyway, and `--strict`
 *  being dropped, so null-safety drift stops being detected. Neither is
 *  observable without being able to provoke real drift. */
const AGENT_API =
  process.env["PARITY_AGENT_API"] ??
  resolve(import.meta.dirname, "../engines/src/praisonai-ts/agent-api.ts");

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

const HERE = resolve(import.meta.dirname, "..");

let output = "";
/** Did the compiler actually run? A checker that reports a clean pass because
 *  it never executed is worse than no checker -- this file's own header says
 *  so. With `npx` off PATH the throw was `spawn npx ENOENT`, whose message
 *  contains no "parity.ts", so the drift filter below found nothing and the
 *  run printed success. */
let compilerRan = false;
try {
  // Run from THIS package: it has typescript, and praisonai-ts's own
  // dependencies are neither needed nor installable (see the header).
  await run("npx", [
    "tsc", "--noEmit", "--strict", "--skipLibCheck",
    "--target", "es2022", "--module", "esnext", "--moduleResolution", "bundler",
    file,
  ], { cwd: HERE });
  compilerRan = true; // exit 0: tsc ran and found nothing to say
} catch (error) {
  output = error.stdout || "";
  // A tsc that genuinely ran and failed prints diagnostics. A spawn failure,
  // a missing binary or a killed process prints none.
  compilerRan = /error TS\d+/.test(output);
  if (!compilerRan) {
    await rm(dir, { recursive: true, force: true });
    console.error(
      "upstream-parity: FAILED -- the typechecker did not run, so NOTHING was checked.\n" +
      `  ${error.message || "no diagnostics and a non-zero exit"}\n` +
      "  This is not a pass. Fix the invocation rather than trusting the green.",
    );
    process.exit(1);
  }
}

// Only errors AT the generated file are drift. An assignability failure always
// reports at the assignment site, so nothing real is lost by this filter --
// while TS2307 (unresolved module) and TS7006 (implicit any) from
// praisonai-ts's own sources would otherwise fail every run.
const drift = output
  .split("\n")
  .filter((line) => line.includes("parity.ts") && line.includes("error TS"));

await rm(dir, { recursive: true, force: true });

if (drift.length > 0) {
  console.error("upstream-parity: FAILED -- praisonai-ts has drifted from agent-api.ts\n");
  for (const line of drift) console.error("  " + line.replace(/^.*parity\.ts/, "parity.ts"));
  console.error(
    "\n  Fix agent-api.ts to match upstream, then re-check the mappings in\n" +
    "  engines/src/praisonai-ts/engine.ts that depend on the changed member.",
  );
  process.exitCode = 1;
} else {
  console.log("upstream-parity: the real Agent still satisfies PraisonAgent");
}
