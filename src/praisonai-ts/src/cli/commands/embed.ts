/**
 * Embed Command - Generate embeddings using AI SDK (preferred) or native provider
 * 
 * Subcommands:
 * - text: Embed a single text or multiple texts
 * - file: Embed contents of a file
 * - query: Find similar texts using embeddings
 */

import { outputJson, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { ERROR_CODES } from '../output/errors';

// Simple success formatter for embed command
function formatEmbedSuccess(data: any, meta?: any): { success: true; data: any; meta?: any } {
  return {
    success: true as const,
    data,
    meta,
  };
}
import * as fs from 'fs';
import * as path from 'path';

export interface EmbedOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  model?: string;
  provider?: string;
  backend?: 'ai-sdk' | 'native' | 'auto';
  dimensions?: number;
  file?: string;
  save?: string;
}

const EXIT_CODES = {
  SUCCESS: 0,
  GENERAL_ERROR: 1,
  INVALID_ARGS: 2,
} as const;

export async function execute(args: string[], options: EmbedOptions): Promise<void> {
  const subcommand = args[0] || 'text';
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  switch (subcommand) {
    case 'text':
      await textCommand(args.slice(1), options, outputFormat);
      break;
    case 'file':
      await fileCommand(args.slice(1), options, outputFormat);
      break;
    case 'query':
      await queryCommand(args.slice(1), options, outputFormat);
      break;
    case 'models':
      await modelsCommand(args.slice(1), options, outputFormat);
      break;
    default:
      // If no subcommand, treat args[0] as text to embed
      if (args[0] && !['text', 'file', 'query', 'models'].includes(args[0])) {
        await textCommand(args, options, outputFormat);
      } else {
        if (outputFormat === 'json') {
          outputJson(formatError(ERROR_CODES.INVALID_ARGS, `Unknown subcommand: ${subcommand}`));
        } else {
          await pretty.error(`Unknown subcommand: ${subcommand}`);
          await pretty.info('Available subcommands: text, file, query, models');
        }
        process.exit(EXIT_CODES.INVALID_ARGS);
      }
  }
}

/**
 * Embed text(s)
 */
async function textCommand(args: string[], options: EmbedOptions, outputFormat: string): Promise<void> {
  const texts = args.filter(a => !a.startsWith('-'));
  
  if (texts.length === 0) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide text to embed'));
    } else {
      await pretty.error('Please provide text to embed');
      await pretty.info('Usage: praisonai-ts embed text "Hello world"');
    }
    process.exit(EXIT_CODES.INVALID_ARGS);
  }

  try {
    const { embed, embedMany, getDefaultEmbeddingModel, isAISDKAvailable } = await import('../../llm');
    
    const startTime = Date.now();
    const model = options.model || getDefaultEmbeddingModel(options.provider);
    const aiSdkAvailable = await isAISDKAvailable();
    
    let result: { embeddings: number[][]; usage?: { tokens: number } };
    
    if (texts.length === 1) {
      const single = await embed(texts[0], { 
        model, 
        backend: options.backend 
      });
      result = { 
        embeddings: [single.embedding], 
        usage: single.usage 
      };
    } else {
      result = await embedMany(texts, { 
        model, 
        backend: options.backend 
      });
    }
    
    const duration = Date.now() - startTime;
    
    // Save to file if requested
    if (options.save) {
      const saveData = {
        texts,
        embeddings: result.embeddings,
        model,
        backend: aiSdkAvailable ? 'ai-sdk' : 'native',
        timestamp: new Date().toISOString(),
      };
      fs.writeFileSync(options.save, JSON.stringify(saveData, null, 2));
    }
    
    if (outputFormat === 'json') {
      outputJson(formatEmbedSuccess({
        texts,
        embeddings: result.embeddings,
        dimensions: result.embeddings[0]?.length || 0,
        count: result.embeddings.length,
      }, {
        model,
        backend: aiSdkAvailable ? 'ai-sdk' : 'native',
        duration_ms: duration,
        tokens: result.usage?.tokens,
        saved_to: options.save,
      }));
    } else {
      await pretty.success(`Embedded ${texts.length} text(s)`);
      await pretty.info(`Model: ${model}`);
      await pretty.info(`Backend: ${aiSdkAvailable ? 'AI SDK' : 'Native'}`);
      await pretty.info(`Dimensions: ${result.embeddings[0]?.length || 0}`);
      await pretty.info(`Duration: ${duration}ms`);
      if (result.usage?.tokens) {
        await pretty.info(`Tokens: ${result.usage.tokens}`);
      }
      if (options.save) {
        await pretty.info(`Saved to: ${options.save}`);
      }
      if (options.verbose) {
        console.log('\nEmbeddings (first 5 values each):');
        result.embeddings.forEach((emb, i) => {
          console.log(`  [${i}]: [${emb.slice(0, 5).join(', ')}...]`);
        });
      }
    }
  } catch (error: any) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, error.message));
    } else {
      await pretty.error(`Embedding failed: ${error.message}`);
    }
    process.exit(EXIT_CODES.GENERAL_ERROR);
  }
}

/**
 * Embed file contents
 */
async function fileCommand(args: string[], options: EmbedOptions, outputFormat: string): Promise<void> {
  const filePath = args[0];
  
  if (!filePath) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a file path'));
    } else {
      await pretty.error('Please provide a file path');
      await pretty.info('Usage: praisonai-ts embed file ./document.txt');
    }
    process.exit(EXIT_CODES.INVALID_ARGS);
  }

  try {
    const absolutePath = path.resolve(filePath);
    
    if (!fs.existsSync(absolutePath)) {
      throw new Error(`File not found: ${absolutePath}`);
    }
    
    const content = fs.readFileSync(absolutePath, 'utf-8');
    const { embed, getDefaultEmbeddingModel, isAISDKAvailable } = await import('../../llm');
    
    const startTime = Date.now();
    const model = options.model || getDefaultEmbeddingModel(options.provider);
    const aiSdkAvailable = await isAISDKAvailable();
    
    const result = await embed(content, { 
      model, 
      backend: options.backend 
    });
    
    const duration = Date.now() - startTime;
    
    // Save to file if requested
    if (options.save) {
      const saveData = {
        file: absolutePath,
        embedding: result.embedding,
        model,
        backend: aiSdkAvailable ? 'ai-sdk' : 'native',
        timestamp: new Date().toISOString(),
      };
      fs.writeFileSync(options.save, JSON.stringify(saveData, null, 2));
    }
    
    if (outputFormat === 'json') {
      outputJson(formatEmbedSuccess({
        file: absolutePath,
        embedding: result.embedding,
        dimensions: result.embedding.length,
        content_length: content.length,
      }, {
        model,
        backend: aiSdkAvailable ? 'ai-sdk' : 'native',
        duration_ms: duration,
        tokens: result.usage?.tokens,
        saved_to: options.save,
      }));
    } else {
      await pretty.success(`Embedded file: ${filePath}`);
      await pretty.info(`Model: ${model}`);
      await pretty.info(`Backend: ${aiSdkAvailable ? 'AI SDK' : 'Native'}`);
      await pretty.info(`Dimensions: ${result.embedding.length}`);
      await pretty.info(`Content length: ${content.length} chars`);
      await pretty.info(`Duration: ${duration}ms`);
      if (options.save) {
        await pretty.info(`Saved to: ${options.save}`);
      }
    }
  } catch (error: any) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, error.message));
    } else {
      await pretty.error(`Embedding failed: ${error.message}`);
    }
    process.exit(EXIT_CODES.GENERAL_ERROR);
  }
}

/**
 * Query similar texts
 */
async function queryCommand(args: string[], options: EmbedOptions, outputFormat: string): Promise<void> {
  const query = args[0];
  const dataFile = options.file;
  
  if (!query) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a query'));
    } else {
      await pretty.error('Please provide a query');
      await pretty.info('Usage: praisonai-ts embed query "search text" --file embeddings.json');
    }
    process.exit(EXIT_CODES.INVALID_ARGS);
  }
  
  if (!dataFile) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide --file with embeddings data'));
    } else {
      await pretty.error('Please provide --file with embeddings data');
    }
    process.exit(EXIT_CODES.INVALID_ARGS);
  }

  try {
    const { embed, cosineSimilarity, getDefaultEmbeddingModel } = await import('../../llm');
    
    // Load embeddings data
    const data = JSON.parse(fs.readFileSync(dataFile, 'utf-8'));
    const texts: string[] = data.texts || [];
    const embeddings: number[][] = data.embeddings || [];
    
    if (embeddings.length === 0) {
      throw new Error('No embeddings found in data file');
    }
    
    // Embed the query
    const model = options.model || data.model || getDefaultEmbeddingModel(options.provider);
    const queryResult = await embed(query, { model, backend: options.backend });
    
    // Calculate similarities
    const similarities = embeddings.map((emb, i) => ({
      index: i,
      text: texts[i] || `[${i}]`,
      score: cosineSimilarity(queryResult.embedding, emb),
    }));
    
    // Sort by similarity (descending)
    similarities.sort((a, b) => b.score - a.score);
    
    // Take top 5
    const topResults = similarities.slice(0, 5);
    
    if (outputFormat === 'json') {
      outputJson(formatEmbedSuccess({
        query,
        results: topResults,
      }, {
        model,
        total_embeddings: embeddings.length,
      }));
    } else {
      await pretty.success(`Query: "${query}"`);
      console.log('\nTop results:');
      topResults.forEach((r, i) => {
        console.log(`  ${i + 1}. [${(r.score * 100).toFixed(1)}%] ${r.text.substring(0, 80)}${r.text.length > 80 ? '...' : ''}`);
      });
    }
  } catch (error: any) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, error.message));
    } else {
      await pretty.error(`Query failed: ${error.message}`);
    }
    process.exit(EXIT_CODES.GENERAL_ERROR);
  }
}

/**
 * List available embedding models
 */
async function modelsCommand(args: string[], options: EmbedOptions, outputFormat: string): Promise<void> {
  const models = [
    { provider: 'openai', model: 'text-embedding-3-small', dimensions: 1536, description: 'Fast, cost-effective' },
    { provider: 'openai', model: 'text-embedding-3-large', dimensions: 3072, description: 'Higher quality' },
    { provider: 'openai', model: 'text-embedding-ada-002', dimensions: 1536, description: 'Legacy model' },
    { provider: 'google', model: 'text-embedding-004', dimensions: 768, description: 'Google embedding' },
    { provider: 'cohere', model: 'embed-english-v3.0', dimensions: 1024, description: 'Cohere English' },
    { provider: 'cohere', model: 'embed-multilingual-v3.0', dimensions: 1024, description: 'Cohere Multilingual' },
  ];
  
  if (outputFormat === 'json') {
    outputJson(formatEmbedSuccess({ models }));
  } else {
    await pretty.success('Available Embedding Models');
    console.log('');
    console.log('Provider    Model                      Dimensions  Description');
    console.log('─'.repeat(75));
    models.forEach(m => {
      console.log(`${m.provider.padEnd(12)}${m.model.padEnd(27)}${String(m.dimensions).padEnd(12)}${m.description}`);
    });
    console.log('');
    await pretty.info('Usage: praisonai-ts embed text "Hello" --model openai/text-embedding-3-small');
  }
}
