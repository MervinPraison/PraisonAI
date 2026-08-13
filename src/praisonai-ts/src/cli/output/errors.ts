/**
 * Error normalization for CLI
 * Ensures consistent error codes and messages across implementations
 */

import { EXIT_CODES } from '../spec/cli-spec';
import { formatError } from './json';

export const ERROR_CODES = {
  // General errors
  UNKNOWN: 'UNKNOWN_ERROR',
  INVALID_ARGS: 'INVALID_ARGUMENTS',
  MISSING_ARG: 'MISSING_ARGUMENT',
  INVALID_FLAG: 'INVALID_FLAG',
  
  // Config errors
  CONFIG_NOT_FOUND: 'CONFIG_NOT_FOUND',
  CONFIG_PARSE_ERROR: 'CONFIG_PARSE_ERROR',
  INVALID_PROFILE: 'INVALID_PROFILE',
  
  // Auth errors
  MISSING_API_KEY: 'MISSING_API_KEY',
  INVALID_API_KEY: 'INVALID_API_KEY',
  
  // Network errors
  NETWORK_TIMEOUT: 'NETWORK_TIMEOUT',
  NETWORK_UNREACHABLE: 'NETWORK_UNREACHABLE',
  
  // Runtime errors
  RUNTIME_ERROR: 'RUNTIME_ERROR',
  PROVIDER_ERROR: 'PROVIDER_ERROR',
  MODEL_NOT_FOUND: 'MODEL_NOT_FOUND',
  TOOL_NOT_FOUND: 'TOOL_NOT_FOUND',
  WORKFLOW_ERROR: 'WORKFLOW_ERROR',
  AGENT_ERROR: 'AGENT_ERROR'
} as const;

export type ErrorCode = typeof ERROR_CODES[keyof typeof ERROR_CODES];

export interface CLIError extends Error {
  code: ErrorCode;
  exitCode: number;
  details?: Record<string, unknown>;
}

export function createError(
  code: ErrorCode,
  message: string,
  exitCode: number = EXIT_CODES.RUNTIME_ERROR,
  details?: Record<string, unknown>
): CLIError {
  const error = new Error(message) as CLIError;
  error.code = code;
  error.exitCode = exitCode;
  error.details = details;
  return error;
}

export function isCLIError(error: unknown): error is CLIError {
  return error instanceof Error && 'code' in error && 'exitCode' in error;
}

export function normalizeError(error: unknown): CLIError {
  if (isCLIError(error)) {
    return error;
  }
  
  if (error instanceof Error) {
    // Try to categorize common errors
    const message = error.message.toLowerCase();
    
    if (message.includes('api key') || message.includes('unauthorized') || message.includes('401')) {
      return createError(ERROR_CODES.MISSING_API_KEY, error.message, EXIT_CODES.AUTH_ERROR);
    }
    
    if (message.includes('timeout') || message.includes('timed out')) {
      return createError(ERROR_CODES.NETWORK_TIMEOUT, error.message, EXIT_CODES.NETWORK_ERROR);
    }
    
    if (message.includes('network') || message.includes('econnrefused') || message.includes('enotfound')) {
      return createError(ERROR_CODES.NETWORK_UNREACHABLE, error.message, EXIT_CODES.NETWORK_ERROR);
    }
    
    if (message.includes('config') || message.includes('configuration')) {
      return createError(ERROR_CODES.CONFIG_PARSE_ERROR, error.message, EXIT_CODES.CONFIG_ERROR);
    }
    
    return createError(ERROR_CODES.UNKNOWN, error.message);
  }
  
  return createError(ERROR_CODES.UNKNOWN, String(error));
}

export function formatCLIError(error: CLIError) {
  return formatError(error.code, error.message, error.details);
}
