/**
 * Image command - Image generation and analysis
 */

import { createImageAgent } from '../../agent/image';
import { resolveConfig } from '../config/resolve';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface ImageOptions {
  model?: string;
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  size?: string;
  quality?: string;
  style?: string;
}

export async function execute(args: string[], options: ImageOptions): Promise<void> {
  const action = args[0] || 'help';
  const actionArgs = args.slice(1);
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');
  const config = resolveConfig(options);

  try {
    switch (action) {
      case 'generate':
        await generateImage(actionArgs, options, config, outputFormat);
        break;
      case 'analyze':
        await analyzeImage(actionArgs, options, config, outputFormat);
        break;
      case 'help':
      default:
        await showHelp(outputFormat);
        break;
    }
  } catch (error) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, error instanceof Error ? error.message : String(error)));
    } else {
      await pretty.error(error instanceof Error ? error.message : String(error));
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }
}

async function generateImage(args: string[], options: ImageOptions, config: any, outputFormat: string): Promise<void> {
  const prompt = args.join(' ');
  if (!prompt) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a prompt for image generation'));
    } else {
      await pretty.error('Please provide a prompt for image generation');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const startTime = Date.now();

  if (outputFormat !== 'json') {
    await pretty.info(`Generating image: "${prompt}"`);
  }

  const agent = createImageAgent({
    llm: config.model,
    verbose: options.verbose
  });

  const result = await agent.generate({
    prompt,
    size: options.size as any,
    quality: options.quality as any,
    style: options.style as any
  });

  const duration = Date.now() - startTime;
  const urls = Array.isArray(result) ? result : [result];

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      prompt,
      urls
    }, {
      duration_ms: duration,
      model: config.model
    }));
  } else {
    await pretty.heading('Generated Image');
    for (const url of urls) {
      await pretty.plain(`URL: ${url}`);
    }
    await pretty.newline();
    await pretty.success(`Generated in ${duration}ms`);
  }
}

async function analyzeImage(args: string[], options: ImageOptions, config: any, outputFormat: string): Promise<void> {
  const imageUrl = args[0];
  const prompt = args.slice(1).join(' ') || 'Describe this image';

  if (!imageUrl) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide an image URL'));
    } else {
      await pretty.error('Please provide an image URL');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const startTime = Date.now();

  if (outputFormat !== 'json') {
    await pretty.info(`Analyzing image: ${imageUrl}`);
  }

  const agent = createImageAgent({
    llm: config.model,
    verbose: options.verbose
  });

  const result = await agent.analyze({
    imageUrl,
    prompt
  });

  const duration = Date.now() - startTime;

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      imageUrl,
      prompt,
      analysis: result
    }, {
      duration_ms: duration,
      model: config.model
    }));
  } else {
    await pretty.heading('Image Analysis');
    await pretty.plain(result);
    await pretty.newline();
    await pretty.success(`Analyzed in ${duration}ms`);
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'image',
    subcommands: [
      { name: 'generate <prompt>', description: 'Generate an image from text' },
      { name: 'analyze <url> [question]', description: 'Analyze an image' },
      { name: 'help', description: 'Show this help' }
    ],
    flags: [
      { name: '--size', description: 'Image size (1024x1024, 1792x1024, 1024x1792)' },
      { name: '--quality', description: 'Image quality (standard, hd)' },
      { name: '--style', description: 'Image style (vivid, natural)' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Image Command');
    await pretty.plain('Generate and analyze images\n');
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(30)} ${cmd.description}`);
    }
    await pretty.newline();
    await pretty.plain('Flags:');
    for (const flag of help.flags) {
      await pretty.plain(`  ${flag.name.padEnd(20)} ${flag.description}`);
    }
  }
}
