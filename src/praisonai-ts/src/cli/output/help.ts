/**
 * Shared help-text renderers for CLI commands
 *
 * Both renderers print a command's help object verbatim in JSON mode and
 * reproduce the historical pretty/plain text layout otherwise.
 */

import { outputJson, formatSuccess } from './json';
import * as pretty from './pretty';

/** One titled section of plain help output: an optional key/description table and/or literal example lines. */
export interface PlainHelpSection {
  label: string;
  entries?: Record<string, string>;
  items?: string[];
  width?: number;
}

/**
 * Print a command's help in JSON mode or as the plain console layout:
 * heading, then one titled section per entry.
 */
export function printPlainHelp(isJson: boolean, help: unknown, heading: string, sections: PlainHelpSection[]): void {
  if (isJson) {
    console.log(JSON.stringify(help, null, 2));
    return;
  }
  console.log(heading);
  for (const section of sections) {
    console.log(`\n${section.label}`);
    for (const [name, description] of Object.entries(section.entries ?? {})) {
      console.log(`  ${name.padEnd(section.width ?? 12)} ${description}`);
    }
    for (const item of section.items ?? []) {
      console.log(`  ${item}`);
    }
  }
}

export interface HelpEntry {
  name: string;
  description: string;
}

export interface PrettyHelpLayout {
  heading: string;
  /** Literal description line; when omitted, `help.description` is printed followed by a blank line. */
  description?: string;
  /** Example lines printed dim under a dim "Examples:" heading. */
  examples?: string[];
}

/**
 * Print a command's help in JSON mode or with the pretty output layer
 * (heading, description, subcommands at width 25, flags at width 20, examples).
 */
export async function printCommandHelp(
  outputFormat: string,
  help: { description?: string; subcommands: HelpEntry[]; flags?: HelpEntry[] },
  layout: PrettyHelpLayout
): Promise<void> {
  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
    return;
  }
  await pretty.heading(layout.heading);
  if (layout.description !== undefined) {
    await pretty.plain(layout.description);
  } else if (help.description !== undefined) {
    await pretty.plain(help.description);
    await pretty.newline();
  }
  await pretty.plain('Subcommands:');
  for (const cmd of help.subcommands) {
    await pretty.plain(`  ${cmd.name.padEnd(25)} ${cmd.description}`);
  }
  if (help.flags && help.flags.length > 0) {
    await pretty.newline();
    await pretty.plain('Flags:');
    for (const flag of help.flags) {
      await pretty.plain(`  ${flag.name.padEnd(20)} ${flag.description}`);
    }
  }
  if (layout.examples) {
    await pretty.newline();
    await pretty.dim('Examples:');
    for (const example of layout.examples) {
      await pretty.dim(`  ${example}`);
    }
  }
}
