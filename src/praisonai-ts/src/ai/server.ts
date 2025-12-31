/**
 * Server Adapters - AI SDK Wrapper
 * 
 * Provides server adapters for HTTP, Express, Hono, Fastify, and Nest.js.
 */

import type { IncomingMessage, ServerResponse } from 'http';

export interface ServerHandler {
  /** Handle a request */
  handle(req: any, res: any): Promise<void>;
}

export interface ServerHandlerConfig {
  /** Agent or generateText/streamText function */
  handler: (input: any) => Promise<any>;
  /** Enable streaming (default: true) */
  streaming?: boolean;
  /** CORS headers */
  cors?: boolean | CorsConfig;
  /** Request body parser */
  bodyParser?: (req: any) => Promise<any>;
  /** Response formatter */
  responseFormatter?: (result: any) => any;
  /** Error handler */
  onError?: (error: Error, req: any, res: any) => void;
}

export interface CorsConfig {
  origin?: string | string[];
  methods?: string[];
  headers?: string[];
  credentials?: boolean;
}

/**
 * Create an HTTP server handler.
 * 
 * @example
 * ```typescript
 * import { createServer } from 'http';
 * import { createHttpHandler } from 'praisonai/ai';
 * 
 * const handler = createHttpHandler({
 *   handler: async (input) => {
 *     return await generateText({ model: 'gpt-4o', prompt: input.prompt });
 *   }
 * });
 * 
 * createServer(handler.handle).listen(3000);
 * ```
 */
export function createHttpHandler(config: ServerHandlerConfig): ServerHandler {
  return {
    handle: async (req: IncomingMessage, res: ServerResponse) => {
      try {
        // Set CORS headers
        if (config.cors) {
          setCorsHeaders(res, config.cors);
        }

        // Handle preflight
        if (req.method === 'OPTIONS') {
          res.writeHead(204);
          res.end();
          return;
        }

        // Parse body
        const body = config.bodyParser 
          ? await config.bodyParser(req)
          : await parseJsonBody(req);

        // Execute handler
        const result = await config.handler(body);

        // Format response
        const response = config.responseFormatter 
          ? config.responseFormatter(result)
          : result;

        // Send response
        if (config.streaming && result.textStream) {
          res.writeHead(200, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
          });

          for await (const chunk of result.textStream) {
            res.write(`data: ${JSON.stringify({ text: chunk })}\n\n`);
          }
          res.write('data: [DONE]\n\n');
          res.end();
        } else {
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify(response));
        }
      } catch (error: any) {
        if (config.onError) {
          config.onError(error, req, res);
        } else {
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: error.message }));
        }
      }
    },
  };
}

/**
 * Create an Express handler.
 * 
 * @example
 * ```typescript
 * import express from 'express';
 * import { createExpressHandler } from 'praisonai/ai';
 * 
 * const app = express();
 * app.use(express.json());
 * 
 * app.post('/api/chat', createExpressHandler({
 *   handler: async (input) => {
 *     return await streamText({ model: 'gpt-4o', messages: input.messages });
 *   }
 * }));
 * ```
 */
export function createExpressHandler(config: ServerHandlerConfig): (req: any, res: any) => Promise<void> {
  return async (req: any, res: any) => {
    try {
      // Set CORS headers
      if (config.cors) {
        setCorsHeaders(res, config.cors);
      }

      // Execute handler
      const result = await config.handler(req.body);

      // Format response
      const response = config.responseFormatter 
        ? config.responseFormatter(result)
        : result;

      // Send response
      if (config.streaming && result.textStream) {
        res.setHeader('Content-Type', 'text/event-stream');
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader('Connection', 'keep-alive');

        for await (const chunk of result.textStream) {
          res.write(`data: ${JSON.stringify({ text: chunk })}\n\n`);
        }
        res.write('data: [DONE]\n\n');
        res.end();
      } else {
        res.json(response);
      }
    } catch (error: any) {
      if (config.onError) {
        config.onError(error, req, res);
      } else {
        res.status(500).json({ error: error.message });
      }
    }
  };
}

/**
 * Create a Hono handler.
 * 
 * @example
 * ```typescript
 * import { Hono } from 'hono';
 * import { createHonoHandler } from 'praisonai/ai';
 * 
 * const app = new Hono();
 * 
 * app.post('/api/chat', createHonoHandler({
 *   handler: async (input) => {
 *     return await streamText({ model: 'gpt-4o', messages: input.messages });
 *   }
 * }));
 * ```
 */
export function createHonoHandler(config: ServerHandlerConfig): (c: any) => Promise<Response> {
  return async (c: any) => {
    try {
      const body = await c.req.json();
      const result = await config.handler(body);

      const response = config.responseFormatter 
        ? config.responseFormatter(result)
        : result;

      if (config.streaming && result.textStream) {
        const stream = new ReadableStream({
          async start(controller) {
            for await (const chunk of result.textStream) {
              controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify({ text: chunk })}\n\n`));
            }
            controller.enqueue(new TextEncoder().encode('data: [DONE]\n\n'));
            controller.close();
          },
        });

        return new Response(stream, {
          headers: {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
          },
        });
      }

      return c.json(response);
    } catch (error: any) {
      return c.json({ error: error.message }, 500);
    }
  };
}

/**
 * Create a Fastify handler.
 * 
 * @example
 * ```typescript
 * import Fastify from 'fastify';
 * import { createFastifyHandler } from 'praisonai/ai';
 * 
 * const fastify = Fastify();
 * 
 * fastify.post('/api/chat', createFastifyHandler({
 *   handler: async (input) => {
 *     return await streamText({ model: 'gpt-4o', messages: input.messages });
 *   }
 * }));
 * ```
 */
export function createFastifyHandler(config: ServerHandlerConfig): (request: any, reply: any) => Promise<void> {
  return async (request: any, reply: any) => {
    try {
      const result = await config.handler(request.body);

      const response = config.responseFormatter 
        ? config.responseFormatter(result)
        : result;

      if (config.streaming && result.textStream) {
        reply.raw.writeHead(200, {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        });

        for await (const chunk of result.textStream) {
          reply.raw.write(`data: ${JSON.stringify({ text: chunk })}\n\n`);
        }
        reply.raw.write('data: [DONE]\n\n');
        reply.raw.end();
      } else {
        reply.send(response);
      }
    } catch (error: any) {
      if (config.onError) {
        config.onError(error, request, reply);
      } else {
        reply.status(500).send({ error: error.message });
      }
    }
  };
}

/**
 * Create a Nest.js controller method decorator config.
 * 
 * @example
 * ```typescript
 * import { Controller, Post, Body, Res } from '@nestjs/common';
 * import { createNestHandler } from 'praisonai/ai';
 * 
 * @Controller('api')
 * export class ChatController {
 *   private handler = createNestHandler({
 *     handler: async (input) => {
 *       return await streamText({ model: 'gpt-4o', messages: input.messages });
 *     }
 *   });
 * 
 *   @Post('chat')
 *   async chat(@Body() body: any, @Res() res: any) {
 *     return this.handler(body, res);
 *   }
 * }
 * ```
 */
export function createNestHandler(config: ServerHandlerConfig): (body: any, res: any) => Promise<void> {
  return async (body: any, res: any) => {
    try {
      const result = await config.handler(body);

      const response = config.responseFormatter 
        ? config.responseFormatter(result)
        : result;

      if (config.streaming && result.textStream) {
        res.setHeader('Content-Type', 'text/event-stream');
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader('Connection', 'keep-alive');

        for await (const chunk of result.textStream) {
          res.write(`data: ${JSON.stringify({ text: chunk })}\n\n`);
        }
        res.write('data: [DONE]\n\n');
        res.end();
      } else {
        res.json(response);
      }
    } catch (error: any) {
      if (config.onError) {
        config.onError(error, body, res);
      } else {
        res.status(500).json({ error: error.message });
      }
    }
  };
}

/**
 * Parse JSON body from HTTP request.
 */
async function parseJsonBody(req: IncomingMessage): Promise<any> {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (e) {
        reject(new Error('Invalid JSON body'));
      }
    });
    req.on('error', reject);
  });
}

/**
 * Set CORS headers on response.
 */
function setCorsHeaders(res: any, cors: boolean | CorsConfig): void {
  const config: CorsConfig = typeof cors === 'boolean' 
    ? { origin: '*', methods: ['GET', 'POST', 'OPTIONS'], headers: ['Content-Type'] }
    : cors;

  const origin = Array.isArray(config.origin) ? config.origin.join(', ') : (config.origin || '*');
  
  if (res.setHeader) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Access-Control-Allow-Methods', (config.methods || ['GET', 'POST', 'OPTIONS']).join(', '));
    res.setHeader('Access-Control-Allow-Headers', (config.headers || ['Content-Type']).join(', '));
    if (config.credentials) {
      res.setHeader('Access-Control-Allow-Credentials', 'true');
    }
  } else if (res.set) {
    res.set('Access-Control-Allow-Origin', origin);
    res.set('Access-Control-Allow-Methods', (config.methods || ['GET', 'POST', 'OPTIONS']).join(', '));
    res.set('Access-Control-Allow-Headers', (config.headers || ['Content-Type']).join(', '));
    if (config.credentials) {
      res.set('Access-Control-Allow-Credentials', 'true');
    }
  }
}
