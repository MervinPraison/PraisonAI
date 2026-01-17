/**
 * LLM Command - AI SDK provider management and testing
 * 
 * Subcommands:
 * - providers: List available AI SDK providers
 * - test: Test connectivity to a provider
 * - validate: Validate provider configuration
 * - run: Run a prompt with a specific model
 */

import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { ERROR_CODES } from '../output/errors';

export interface LLMOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  model?: string;
  stream?: boolean;
  timeout?: number;
  provider?: string;
  schema?: string;
  tool?: string;
}

// Exit codes specific to LLM commands
const LLM_EXIT_CODES = {
  SUCCESS: 0,
  GENERAL_ERROR: 1,
  INVALID_ARGS: 2,
  AUTH_ERROR: 3,
  PROVIDER_NOT_FOUND: 4,
  NETWORK_ERROR: 5,
  TIMEOUT: 6,
} as const;

export async function execute(args: string[], options: LLMOptions): Promise<void> {
  const subcommand = args[0] || 'providers';
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  switch (subcommand) {
    case 'providers':
      await providersCommand(args.slice(1), options, outputFormat);
      break;
    case 'test':
      await testCommand(args.slice(1), options, outputFormat);
      break;
    case 'validate':
      await validateCommand(args.slice(1), options, outputFormat);
      break;
    case 'run':
      await runCommand(args.slice(1), options, outputFormat);
      break;
    case 'models':
      await modelsCommand(args.slice(1), options, outputFormat);
      break;
    case 'config':
      await configCommand(args.slice(1), options, outputFormat);
      break;
    case 'trace':
      await traceCommand(args.slice(1), options, outputFormat);
      break;
    case 'tools':
      await toolsCommand(args.slice(1), options, outputFormat);
      break;
    case 'json':
      await jsonCommand(args.slice(1), options, outputFormat);
      break;
    case 'help':
      await helpCommand(outputFormat);
      break;
    default:
      if (outputFormat === 'json') {
        outputJson(formatError(ERROR_CODES.INVALID_ARGS, `Unknown subcommand: ${subcommand}`));
      } else {
        await pretty.error(`Unknown subcommand: ${subcommand}`);
        await pretty.info('Available subcommands: providers, test, validate, run, models, config, trace, tools, json');
      }
      process.exit(LLM_EXIT_CODES.INVALID_ARGS);
  }
}

/**
 * List available AI SDK providers
 */
async function providersCommand(args: string[], options: LLMOptions, outputFormat: string): Promise<void> {
  try {
    const {
      listSupportedProviders,
      AISDK_PROVIDERS,
      validateProviderApiKey,
      isAISDKAvailable,
      getAISDKVersion
    } = await import('../../llm/providers/ai-sdk');

    const providers = listSupportedProviders();
    const aiSdkAvailable = await isAISDKAvailable();
    const aiSdkVersion = await getAISDKVersion();

    const providerDetails = providers.map((id: string) => {
      const info = AISDK_PROVIDERS[id as keyof typeof AISDK_PROVIDERS];
      const hasApiKey = validateProviderApiKey(id);
      return {
        id,
        package: info?.package || 'custom',
        envKey: info?.envKey || 'N/A',
        hasApiKey,
        status: hasApiKey ? 'ready' : 'missing_key'
      };
    });

    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        ai_sdk_available: aiSdkAvailable,
        ai_sdk_version: aiSdkVersion,
        providers: providerDetails,
        total: providers.length
      }));
    } else {
      await pretty.heading('AI SDK Providers');

      if (aiSdkAvailable) {
        await pretty.success(`AI SDK: ${aiSdkVersion || 'installed'}`);
      } else {
        await pretty.warn('AI SDK not installed. Run: npm install ai');
      }

      await pretty.newline();
      await pretty.plain('  Available Providers:');

      for (const p of providerDetails) {
        const status = p.hasApiKey ? '✅' : '⚠️';
        const keyInfo = p.hasApiKey ? '🔑' : `Missing ${p.envKey}`;
        await pretty.plain(`    ${status} ${p.id.padEnd(20)} ${keyInfo}`);

        if (options.verbose) {
          await pretty.dim(`        Package: ${p.package}`);
        }
      }

      await pretty.newline();
      await pretty.info('Set API keys via environment variables');
      await pretty.dim('  Example: export OPENAI_API_KEY=sk-...');
    }
  } catch (error) {
    handleError(error, outputFormat, 'Failed to list providers');
  }
}

/**
 * Test connectivity to a provider
 */
async function testCommand(args: string[], options: LLMOptions, outputFormat: string): Promise<void> {
  const providerId = args[0] || options.provider;

  if (!providerId) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Provider ID required'));
    } else {
      await pretty.error('Provider ID required. Usage: llm test <provider>');
      await pretty.dim('  Example: praisonai-ts llm test openai');
    }
    process.exit(LLM_EXIT_CODES.INVALID_ARGS);
    return;
  }

  try {
    const {
      createAISDKBackend,
      validateProviderApiKey,
      getMissingApiKeyMessage,
      isProviderSupported
    } = await import('../../llm/providers/ai-sdk');

    // Check if provider is supported
    if (!isProviderSupported(providerId)) {
      if (outputFormat === 'json') {
        outputJson(formatError('PROVIDER_NOT_FOUND', `Provider '${providerId}' is not supported`));
      } else {
        await pretty.error(`Provider '${providerId}' is not supported`);
      }
      process.exit(LLM_EXIT_CODES.PROVIDER_NOT_FOUND);
      return;
    }

    // Check API key
    if (!validateProviderApiKey(providerId)) {
      const msg = getMissingApiKeyMessage(providerId);
      if (outputFormat === 'json') {
        outputJson(formatError('AUTH_ERROR', msg));
      } else {
        await pretty.error(msg);
      }
      process.exit(LLM_EXIT_CODES.AUTH_ERROR);
      return;
    }

    // Determine test model based on provider
    const testModels: Record<string, string> = {
      openai: 'gpt-4o-mini',
      anthropic: 'claude-3-haiku-20240307',
      google: 'gemini-1.5-flash',
      groq: 'llama-3.1-8b-instant',
      mistral: 'mistral-small-latest',
      cohere: 'command-light',
      deepseek: 'deepseek-chat',
    };

    const modelId = options.model || testModels[providerId] || 'default';
    const modelString = `${providerId}/${modelId}`;

    if (outputFormat !== 'json') {
      await pretty.info(`Testing ${modelString}...`);
    }

    const startTime = Date.now();
    const backend = createAISDKBackend(modelString, {
      timeout: options.timeout || 30000,
      maxRetries: 0, // No retries for test
    });

    const result = await backend.generateText({
      messages: [
        { role: 'user', content: 'Say "OK" and nothing else.' }
      ],
      maxTokens: 10,
      temperature: 0,
    });

    const duration = Date.now() - startTime;

    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        provider: providerId,
        model: modelId,
        status: 'success',
        duration_ms: duration,
        response: result.text,
        usage: result.usage
      }));
    } else {
      await pretty.success(`Connection successful! (${duration}ms)`);
      await pretty.plain(`  Provider: ${providerId}`);
      await pretty.plain(`  Model: ${modelId}`);
      await pretty.plain(`  Response: ${result.text.trim()}`);
      if (result.usage) {
        await pretty.dim(`  Tokens: ${result.usage.totalTokens}`);
      }
    }
  } catch (error) {
    handleError(error, outputFormat, `Failed to test provider '${providerId}'`);
  }
}

/**
 * Validate provider configuration
 */
async function validateCommand(args: string[], options: LLMOptions, outputFormat: string): Promise<void> {
  const providerId = args[0] || options.provider;

  if (!providerId) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Provider ID required'));
    } else {
      await pretty.error('Provider ID required. Usage: llm validate --provider <id>');
    }
    process.exit(LLM_EXIT_CODES.INVALID_ARGS);
    return;
  }

  try {
    const {
      isProviderSupported,
      validateProviderApiKey,
      getProviderEnvKey,
      getProviderPackage,
      isAISDKAvailable
    } = await import('../../llm/providers/ai-sdk');

    const checks: Array<{ name: string; passed: boolean; message: string }> = [];

    // Check AI SDK availability
    const aiSdkAvailable = await isAISDKAvailable();
    checks.push({
      name: 'AI SDK Installed',
      passed: aiSdkAvailable,
      message: aiSdkAvailable ? 'AI SDK is installed' : 'AI SDK not found. Run: npm install ai'
    });

    // Check provider support
    const isSupported = isProviderSupported(providerId);
    checks.push({
      name: 'Provider Supported',
      passed: isSupported,
      message: isSupported ? `Provider '${providerId}' is supported` : `Provider '${providerId}' is not supported`
    });

    if (isSupported) {
      // Check provider package
      const pkg = getProviderPackage(providerId);
      if (pkg) {
        let pkgInstalled = false;
        try {
          require.resolve(pkg);
          pkgInstalled = true;
        } catch {
          pkgInstalled = false;
        }
        checks.push({
          name: 'Provider Package',
          passed: pkgInstalled,
          message: pkgInstalled ? `${pkg} is installed` : `${pkg} not found. Run: npm install ${pkg}`
        });
      }

      // Check API key
      const hasApiKey = validateProviderApiKey(providerId);
      const envKey = getProviderEnvKey(providerId);
      checks.push({
        name: 'API Key',
        passed: hasApiKey,
        message: hasApiKey
          ? `${envKey} is set`
          : `${envKey} is not set`
      });
    }

    const allPassed = checks.every(c => c.passed);

    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        provider: providerId,
        valid: allPassed,
        checks
      }));
    } else {
      await pretty.heading(`Validation: ${providerId}`);

      for (const check of checks) {
        const icon = check.passed ? '✅' : '❌';
        await pretty.plain(`  ${icon} ${check.name}: ${check.message}`);
      }

      await pretty.newline();
      if (allPassed) {
        await pretty.success('All checks passed!');
      } else {
        await pretty.warn('Some checks failed. Fix the issues above.');
        process.exit(LLM_EXIT_CODES.GENERAL_ERROR);
      }
    }
  } catch (error) {
    handleError(error, outputFormat, `Failed to validate provider '${providerId}'`);
  }
}

/**
 * Run a prompt with a specific model
 */
async function runCommand(args: string[], options: LLMOptions, outputFormat: string): Promise<void> {
  const prompt = args.join(' ');

  if (!prompt) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Prompt required'));
    } else {
      await pretty.error('Prompt required. Usage: llm run "<prompt>" --model <provider/model>');
      await pretty.dim('  Example: praisonai-ts llm run "Hello!" --model openai/gpt-4o-mini');
    }
    process.exit(LLM_EXIT_CODES.INVALID_ARGS);
    return;
  }

  const modelString = options.model || 'openai/gpt-4o-mini';

  try {
    const { createAISDKBackend } = await import('../../llm/providers/ai-sdk');

    const backend = createAISDKBackend(modelString, {
      timeout: options.timeout || 60000,
    });

    if (options.stream) {
      // Streaming mode
      if (outputFormat === 'json') {
        // JSON streaming - output each chunk as JSON line
        const stream = await backend.streamText({
          messages: [{ role: 'user', content: prompt }],
        });

        process.stdout.write('{"type":"stream_start"}\n');

        let fullText = '';
        for await (const chunk of stream) {
          if (chunk.text) {
            fullText += chunk.text;
            process.stdout.write(JSON.stringify({ type: 'text', text: chunk.text }) + '\n');
          }
          if (chunk.finishReason) {
            process.stdout.write(JSON.stringify({
              type: 'finish',
              finishReason: chunk.finishReason,
              usage: chunk.usage
            }) + '\n');
          }
        }

        process.stdout.write(JSON.stringify({ type: 'stream_end', fullText }) + '\n');
      } else {
        // Pretty streaming - output text directly
        const stream = await backend.streamText({
          messages: [{ role: 'user', content: prompt }],
        });

        for await (const chunk of stream) {
          if (chunk.text) {
            process.stdout.write(chunk.text);
          }
        }
        process.stdout.write('\n');
      }
    } else {
      // Non-streaming mode
      const startTime = Date.now();
      const result = await backend.generateText({
        messages: [{ role: 'user', content: prompt }],
      });
      const duration = Date.now() - startTime;

      if (outputFormat === 'json') {
        outputJson(formatSuccess({
          model: modelString,
          text: result.text,
          usage: result.usage,
          finishReason: result.finishReason,
          duration_ms: duration
        }));
      } else {
        await pretty.plain(result.text);

        if (options.verbose) {
          await pretty.newline();
          await pretty.dim(`Model: ${modelString}`);
          await pretty.dim(`Duration: ${duration}ms`);
          if (result.usage) {
            await pretty.dim(`Tokens: ${result.usage.totalTokens} (prompt: ${result.usage.promptTokens}, completion: ${result.usage.completionTokens})`);
          }
        }
      }
    }
  } catch (error) {
    handleError(error, outputFormat, `Failed to run prompt with model '${modelString}'`);
  }
}

/**
 * Handle errors with proper exit codes and formatting
 */
/**
 * List common models for each provider
 */
async function modelsCommand(args: string[], options: LLMOptions, outputFormat: string): Promise<void> {
  try {
    const { listSupportedProviders, AISDK_PROVIDERS } = await import('../../llm/providers/ai-sdk');

    // Common models per provider (not exhaustive)
    const commonModels: Record<string, string[]> = {
      openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo', 'o1', 'o1-mini'],
      anthropic: ['claude-3-5-sonnet-latest', 'claude-3-5-haiku-latest', 'claude-3-opus-latest'],
      google: ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash'],
      groq: ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'mixtral-8x7b-32768'],
      mistral: ['mistral-large-latest', 'mistral-small-latest', 'codestral-latest'],
      cohere: ['command-r-plus', 'command-r', 'command-light'],
      deepseek: ['deepseek-chat', 'deepseek-coder'],
      xai: ['grok-2', 'grok-2-mini'],
    };

    const providers = listSupportedProviders();
    const modelsData = providers.map((id: string) => ({
      provider: id,
      models: commonModels[id] || ['(check provider docs)'],
      package: AISDK_PROVIDERS[id as keyof typeof AISDK_PROVIDERS]?.package || 'custom'
    }));

    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        note: 'This is not an exhaustive list. Check provider documentation for all available models.',
        providers: modelsData
      }));
    } else {
      await pretty.heading('Common Models by Provider');
      await pretty.dim('Note: This is not exhaustive. Check provider docs for all models.\n');

      for (const p of modelsData) {
        await pretty.plain(`  ${p.provider}:`);
        for (const model of p.models) {
          await pretty.dim(`    - ${model}`);
        }
      }

      await pretty.newline();
      await pretty.info('Usage: praisonai-ts llm run "prompt" --model provider/model');
    }
  } catch (error) {
    handleError(error, outputFormat, 'Failed to list models');
  }
}

/**
 * Show resolved configuration (redacted)
 */
async function configCommand(args: string[], options: LLMOptions, outputFormat: string): Promise<void> {
  try {
    const { SAFE_DEFAULTS, AISDK_PROVIDERS, PROVIDER_ALIASES } = await import('../../llm/providers/ai-sdk');

    // Gather environment config (redacted)
    const envConfig: Record<string, string> = {};
    for (const [id, info] of Object.entries(AISDK_PROVIDERS)) {
      const envKey = (info as any).envKey;
      if (envKey && process.env[envKey]) {
        envConfig[envKey] = '****' + process.env[envKey]!.slice(-4);
      }
    }

    const config = {
      defaults: SAFE_DEFAULTS,
      aliases: PROVIDER_ALIASES,
      environment: envConfig,
      model: options.model || 'openai/gpt-4o-mini',
      timeout: options.timeout || SAFE_DEFAULTS.timeout,
    };

    if (outputFormat === 'json') {
      outputJson(formatSuccess(config));
    } else {
      await pretty.heading('AI SDK Configuration');

      await pretty.plain('  Defaults:');
      await pretty.dim(`    timeout: ${SAFE_DEFAULTS.timeout}ms`);
      await pretty.dim(`    maxRetries: ${SAFE_DEFAULTS.maxRetries}`);
      await pretty.dim(`    maxOutputTokens: ${SAFE_DEFAULTS.maxOutputTokens}`);
      await pretty.dim(`    redactLogs: ${SAFE_DEFAULTS.redactLogs}`);

      await pretty.newline();
      await pretty.plain('  Provider Aliases:');
      for (const [alias, target] of Object.entries(PROVIDER_ALIASES)) {
        await pretty.dim(`    ${alias} → ${target}`);
      }

      await pretty.newline();
      await pretty.plain('  Environment (redacted):');
      if (Object.keys(envConfig).length === 0) {
        await pretty.dim('    No API keys detected');
      } else {
        for (const [key, value] of Object.entries(envConfig)) {
          await pretty.dim(`    ${key}: ${value}`);
        }
      }
    }
  } catch (error) {
    handleError(error, outputFormat, 'Failed to show config');
  }
}

/**
 * Demo trace/attribution headers
 */
async function traceCommand(args: string[], options: LLMOptions, outputFormat: string): Promise<void> {
  try {
    const { createAISDKBackend, createAttributionMiddleware } = await import('../../llm/providers/ai-sdk');

    const modelString = options.model || 'openai/gpt-4o-mini';

    // Generate demo attribution context
    const attribution = {
      agentId: `agent-${Date.now().toString(36)}`,
      runId: `run-${Math.random().toString(36).slice(2, 10)}`,
      traceId: `trace-${Math.random().toString(36).slice(2, 10)}`,
      sessionId: options.verbose ? `session-demo` : undefined,
    };

    if (outputFormat !== 'json') {
      await pretty.heading('Attribution Trace Demo');
      await pretty.info(`Running with model: ${modelString}`);
      await pretty.newline();
      await pretty.plain('  Attribution Context:');
      await pretty.dim(`    agentId: ${attribution.agentId}`);
      await pretty.dim(`    runId: ${attribution.runId}`);
      await pretty.dim(`    traceId: ${attribution.traceId}`);
      if (attribution.sessionId) {
        await pretty.dim(`    sessionId: ${attribution.sessionId}`);
      }
      await pretty.newline();
      await pretty.plain('  Headers injected:');
      await pretty.dim(`    X-Agent-Id: ${attribution.agentId}`);
      await pretty.dim(`    X-Run-Id: ${attribution.runId}`);
      await pretty.dim(`    X-Trace-Id: ${attribution.traceId}`);
      await pretty.newline();
    }

    const backend = createAISDKBackend(modelString, {
      timeout: options.timeout || 30000,
      attribution,
    });

    const startTime = Date.now();
    const result = await backend.generateText({
      messages: [{ role: 'user', content: 'Say "Trace OK" and nothing else.' }],
      maxTokens: 10,
    });
    const duration = Date.now() - startTime;

    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        attribution,
        headers: {
          'X-Agent-Id': attribution.agentId,
          'X-Run-Id': attribution.runId,
          'X-Trace-Id': attribution.traceId,
        },
        response: result.text,
        duration_ms: duration,
      }));
    } else {
      await pretty.success(`Response: ${result.text.trim()} (${duration}ms)`);
      await pretty.newline();
      await pretty.info('Attribution headers are automatically injected into LLM requests.');
      await pretty.dim('Use --verbose for session ID.');
    }
  } catch (error) {
    handleError(error, outputFormat, 'Failed to run trace demo');
  }
}

/**
 * Demo tool calling - shows how tools work with AI SDK
 * Note: AI SDK requires Zod schemas for tools, which requires runtime setup
 */
async function toolsCommand(args: string[], options: LLMOptions, outputFormat: string): Promise<void> {
  try {
    const modelString = options.model || 'openai/gpt-4o-mini';

    if (outputFormat !== 'json') {
      await pretty.heading('Tool Calling Demo');
      await pretty.info(`Model: ${modelString}`);
      await pretty.newline();
      await pretty.plain('  AI SDK Tool Calling requires Zod schemas.');
      await pretty.newline();
      await pretty.plain('  Example code:');
      await pretty.dim(`    import { generateText, tool } from 'ai';`);
      await pretty.dim(`    import { openai } from '@ai-sdk/openai';`);
      await pretty.dim(`    import { z } from 'zod';`);
      await pretty.newline();
      await pretty.dim(`    const tools = {`);
      await pretty.dim(`      get_weather: tool({`);
      await pretty.dim(`        description: 'Get weather for a city',`);
      await pretty.dim(`        inputSchema: z.object({`);
      await pretty.dim(`          city: z.string().describe('City name'),`);
      await pretty.dim(`        }),`);
      await pretty.dim(`      }),`);
      await pretty.dim(`    };`);
      await pretty.newline();
      await pretty.dim(`    const result = await generateText({`);
      await pretty.dim(`      model: openai('gpt-4o-mini'),`);
      await pretty.dim(`      messages: [{ role: 'user', content: 'Weather in Paris?' }],`);
      await pretty.dim(`      tools,`);
      await pretty.dim(`    });`);
      await pretty.newline();
      await pretty.info('See examples/ai-sdk/tool-calling.ts for a complete example.');
    } else {
      outputJson(formatSuccess({
        model: modelString,
        note: 'AI SDK tool calling requires Zod schemas at runtime',
        example: {
          import: "import { generateText, tool } from 'ai'; import { z } from 'zod';",
          tool: "tool({ description: '...', inputSchema: z.object({ city: z.string() }) })",
        },
        docs: 'See examples/ai-sdk/tool-calling.ts',
      }));
    }
  } catch (error) {
    handleError(error, outputFormat, 'Failed to run tools demo');
  }
}

/**
 * Demo structured output (JSON schema) - shows how to use generateObject
 * Note: AI SDK requires Zod schemas for structured output
 */
async function jsonCommand(args: string[], options: LLMOptions, outputFormat: string): Promise<void> {
  try {
    const modelString = options.model || 'openai/gpt-4o-mini';

    if (outputFormat !== 'json') {
      await pretty.heading('Structured Output (JSON) Demo');
      await pretty.info(`Model: ${modelString}`);
      await pretty.newline();
      await pretty.plain('  AI SDK Structured Output requires Zod schemas.');
      await pretty.newline();
      await pretty.plain('  Example code:');
      await pretty.dim(`    import { generateObject } from 'ai';`);
      await pretty.dim(`    import { openai } from '@ai-sdk/openai';`);
      await pretty.dim(`    import { z } from 'zod';`);
      await pretty.newline();
      await pretty.dim(`    const schema = z.object({`);
      await pretty.dim(`      name: z.string(),`);
      await pretty.dim(`      age: z.number(),`);
      await pretty.dim(`      city: z.string(),`);
      await pretty.dim(`    });`);
      await pretty.newline();
      await pretty.dim(`    const result = await generateObject({`);
      await pretty.dim(`      model: openai('gpt-4o-mini'),`);
      await pretty.dim(`      schema,`);
      await pretty.dim(`      prompt: 'Generate a fictional person profile.',`);
      await pretty.dim(`    });`);
      await pretty.newline();
      await pretty.dim(`    console.log(result.object); // { name: '...', age: 25, city: '...' }`);
      await pretty.newline();
      await pretty.info('See examples/ai-sdk/structured-output.ts for a complete example.');
    } else {
      outputJson(formatSuccess({
        model: modelString,
        note: 'AI SDK structured output requires Zod schemas at runtime',
        example: {
          import: "import { generateObject } from 'ai'; import { z } from 'zod';",
          schema: "z.object({ name: z.string(), age: z.number(), city: z.string() })",
        },
        docs: 'See examples/ai-sdk/structured-output.ts',
      }));
    }
  } catch (error) {
    handleError(error, outputFormat, 'Failed to run JSON demo');
  }
}

/**
 * Show help for LLM subcommands
 */
async function helpCommand(outputFormat: string): Promise<void> {
  const help = {
    command: 'llm',
    description: 'AI SDK provider management and testing',
    subcommands: [
      { name: 'providers', description: 'List available AI SDK providers' },
      { name: 'test <provider>', description: 'Test connectivity to a provider' },
      { name: 'validate <provider>', description: 'Validate provider configuration' },
      { name: 'run "<prompt>"', description: 'Run a prompt with a specific model' },
      { name: 'models', description: 'List common models by provider' },
      { name: 'config', description: 'Show resolved configuration' },
      { name: 'trace', description: 'Demo attribution/trace headers' },
      { name: 'tools', description: 'Demo tool calling' },
      { name: 'json', description: 'Demo structured output' },
      { name: 'help', description: 'Show this help' }
    ],
    flags: [
      { name: '--model', description: 'Model to use (provider/model format)' },
      { name: '--stream', description: 'Enable streaming output' },
      { name: '--timeout', description: 'Request timeout in ms' },
      { name: '--verbose', description: 'Show detailed output' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('LLM Command');
    await pretty.plain(help.description + '\n');
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(25)} ${cmd.description}`);
    }
    await pretty.newline();
    await pretty.plain('Flags:');
    for (const flag of help.flags) {
      await pretty.plain(`  ${flag.name.padEnd(20)} ${flag.description}`);
    }
    await pretty.newline();
    await pretty.dim('Examples:');
    await pretty.dim('  praisonai-ts llm providers');
    await pretty.dim('  praisonai-ts llm test openai');
    await pretty.dim('  praisonai-ts llm run "Hello" --model openai/gpt-4o-mini');
  }
}

/**
 * Handle errors with proper exit codes and formatting
 */
async function handleError(error: unknown, outputFormat: string, context: string): Promise<never> {
  const { AISDKError } = await import('../../llm/providers/ai-sdk');

  let exitCode: number = LLM_EXIT_CODES.GENERAL_ERROR;
  let errorCode = 'UNKNOWN_ERROR';
  let message = context;

  if (error instanceof AISDKError) {
    message = `${context}: ${error.message}`;
    errorCode = error.code;

    switch (error.code) {
      case 'AUTHENTICATION':
        exitCode = 3; // AUTH_ERROR
        break;
      case 'PROVIDER_NOT_FOUND':
      case 'MODEL_NOT_FOUND':
        exitCode = 4; // PROVIDER_NOT_FOUND
        break;
      case 'NETWORK':
        exitCode = 5; // NETWORK_ERROR
        break;
      case 'TIMEOUT':
        exitCode = 6; // TIMEOUT
        break;
      case 'INVALID_REQUEST':
        exitCode = 2; // INVALID_ARGS
        break;
    }
  } else if (error instanceof Error) {
    message = `${context}: ${error.message}`;
  }

  if (outputFormat === 'json') {
    outputJson(formatError(errorCode, message));
  } else {
    await pretty.error(message);
  }

  process.exit(exitCode);
}
