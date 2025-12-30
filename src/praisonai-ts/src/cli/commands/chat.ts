/**
 * Chat command - Chat with an AI agent
 */

import { resolveBackend } from '../../llm/backend-resolver';
import { Session } from '../../session';
import { resolveConfig } from '../config/resolve';
import { printSuccess, printError, outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES, normalizeError } from '../output/errors';

export interface ChatOptions {
  model?: string;
  stream?: boolean;
  session?: string;
  verbose?: boolean;
  profile?: string;
  config?: string;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

export async function execute(args: string[], options: ChatOptions): Promise<void> {
  const prompt = args[0];
  
  if (!prompt) {
    if (options.json || options.output === 'json') {
      printError(ERROR_CODES.MISSING_ARG, 'Please provide a prompt');
    } else {
      await pretty.error('Please provide a prompt');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  // Resolve config with precedence
  const config = resolveConfig({
    configPath: options.config,
    profile: options.profile,
    model: options.model,
    verbose: options.verbose,
    stream: options.stream
  });

  const startTime = Date.now();
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    const { provider } = await resolveBackend(config.model);
    const session = new Session({ id: options.session });
    session.addMessage({ role: 'user', content: prompt });

    let responseText = '';
    let inputTokens = 0;
    let outputTokens = 0;

    if (config.stream && outputFormat !== 'json') {
      // Streaming mode (only for non-JSON output)
      const stream = await provider.streamText({
        messages: [{ role: 'user', content: prompt }],
        onToken: (token: string) => {
          process.stdout.write(token);
          responseText += token;
        }
      });

      for await (const chunk of stream) {
        // Stream is consumed by onToken
      }
      console.log(); // New line after streaming
    } else {
      // Non-streaming mode
      const result = await provider.generateText({
        messages: [{ role: 'user', content: prompt }]
      });
      responseText = result.text;
      inputTokens = result.usage?.promptTokens || 0;
      outputTokens = result.usage?.completionTokens || 0;

      if (outputFormat === 'json') {
        const duration = Date.now() - startTime;
        outputJson(formatSuccess(
          { response: responseText },
          {
            duration_ms: duration,
            model: config.model,
            tokens: {
              input: inputTokens,
              output: outputTokens
            }
          }
        ));
      } else {
        console.log(responseText);
      }
    }

    session.addMessage({ role: 'assistant', content: responseText });

  } catch (error) {
    const cliError = normalizeError(error);
    
    if (outputFormat === 'json') {
      outputJson(formatError(cliError.code, cliError.message, cliError.details));
    } else {
      await pretty.error(cliError.message);
      if (config.verbose && error instanceof Error && error.stack) {
        await pretty.dim(error.stack);
      }
    }
    
    process.exit(cliError.exitCode);
  }
}
