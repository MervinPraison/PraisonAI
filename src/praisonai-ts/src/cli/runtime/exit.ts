/**
 * Exit code handling for CLI
 */

import { EXIT_CODES, ExitCode } from '../spec/cli-spec';

export function exit(code: ExitCode): never {
  process.exit(code);
}

export function exitSuccess(): never {
  exit(EXIT_CODES.SUCCESS);
}

export function exitError(message?: string): never {
  if (message) {
    console.error(message);
  }
  exit(EXIT_CODES.RUNTIME_ERROR);
}

export function exitInvalidArgs(message?: string): never {
  if (message) {
    console.error(`Error: ${message}`);
  }
  exit(EXIT_CODES.INVALID_ARGUMENTS);
}

export function exitConfigError(message?: string): never {
  if (message) {
    console.error(`Config Error: ${message}`);
  }
  exit(EXIT_CODES.CONFIG_ERROR);
}

export function exitNetworkError(message?: string): never {
  if (message) {
    console.error(`Network Error: ${message}`);
  }
  exit(EXIT_CODES.NETWORK_ERROR);
}

export function exitAuthError(message?: string): never {
  if (message) {
    console.error(`Auth Error: ${message}`);
  }
  exit(EXIT_CODES.AUTH_ERROR);
}
