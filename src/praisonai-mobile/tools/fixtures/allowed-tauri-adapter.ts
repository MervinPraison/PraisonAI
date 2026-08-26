// FIXTURE — the SAME import as violating-core.ts, from the one place it is allowed.
// If depgraph reports this it is over-reporting, and an over-reporting rule
// gets switched off, which is how a rule stops protecting anything.
import { invoke } from "@tauri-apps/api/core";

export const ok = () => invoke("plugin:secrets|get");
