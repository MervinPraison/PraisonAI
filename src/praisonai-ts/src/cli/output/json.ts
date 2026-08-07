/**
 * JSON output formatting for CLI
 * Ensures byte-compatible output with Python CLI
 */

import { CLIOutput, SuccessOutput, ErrorOutput } from '../spec/cli-spec';

export function formatSuccess<T>(data: T, meta?: SuccessOutput<T>['meta']): SuccessOutput<T> {
  const output: SuccessOutput<T> = {
    success: true,
    data
  };
  if (meta) {
    output.meta = meta;
  }
  return output;
}

export function formatError(code: string, message: string, details?: Record<string, unknown>): ErrorOutput {
  const output: ErrorOutput = {
    success: false,
    error: {
      code,
      message
    }
  };
  if (details) {
    output.error.details = details;
  }
  return output;
}

export function outputJson<T>(output: CLIOutput<T>): void {
  // Use 2-space indentation for readability (matches Python json.dumps default)
  console.log(JSON.stringify(output, null, 2));
}

export function outputJsonCompact<T>(output: CLIOutput<T>): void {
  console.log(JSON.stringify(output));
}

/**
 * Create a success response and output it
 */
export function printSuccess<T>(data: T, meta?: SuccessOutput<T>['meta']): void {
  outputJson(formatSuccess(data, meta));
}

/**
 * Create an error response and output it
 */
export function printError(code: string, message: string, details?: Record<string, unknown>): void {
  outputJson(formatError(code, message, details));
}
