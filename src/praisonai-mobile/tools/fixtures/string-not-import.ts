// FIXTURE — an import specifier that appears only inside a string literal.
// A regex-based checker reports this and is therefore wrong. A real parse does not.
export const HELP_TEXT = 'import { invoke } from "@tauri-apps/api/core"';
export const ALSO = "praisonai";
export const NOT_AN_IMPORT = `import { Agent } from "praisonai"`;
