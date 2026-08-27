// FIXTURE — deliberately violates the layer rule.
// A file under core/ may not reach the UI shell. depgraph must report this.
// It lives under tools/fixtures (not core/) so it cannot break the real build.
import { invoke } from "@tauri-apps/api/core";

export const bad = () => invoke("anything");
