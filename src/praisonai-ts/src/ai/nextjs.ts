/**
 * Next.js Integration - AI SDK Wrapper
 * 
 * Provides route handlers and React hooks for Next.js applications.
 */

export interface RouteHandlerConfig {
  /** Agent or handler function */
  handler: (input: any) => Promise<any>;
  /** Enable streaming (default: true) */
  streaming?: boolean;
  /** Maximum duration in seconds */
  maxDuration?: number;
  /** CORS configuration */
  cors?: boolean | {
    origin?: string | string[];
    methods?: string[];
  };
}

/**
 * Create a Next.js App Router route handler.
 * 
 * @example app/api/chat/route.ts
 * ```typescript
 * import { createRouteHandler } from 'praisonai/ai';
 * import { streamText } from 'praisonai/ai';
 * 
 * export const POST = createRouteHandler({
 *   handler: async (input) => {
 *     return await streamText({
 *       model: 'gpt-4o',
 *       messages: input.messages
 *     });
 *   }
 * });
 * ```
 * 
 * @example With Agent
 * ```typescript
 * import { createRouteHandler } from 'praisonai/ai';
 * import { Agent } from 'praisonai';
 * 
 * const agent = new Agent({ instructions: 'You are helpful' });
 * 
 * export const POST = createRouteHandler({
 *   handler: async (input) => {
 *     return await agent.chat(input.message);
 *   }
 * });
 * ```
 */
export function createRouteHandler(config: RouteHandlerConfig) {
  return async (request: Request): Promise<Response> => {
    try {
      // Parse request body
      const body = await request.json();

      // Execute handler
      const result = await config.handler(body);

      // Handle streaming response
      if (config.streaming !== false && result.textStream) {
        const stream = new ReadableStream({
          async start(controller) {
            const encoder = new TextEncoder();
            
            try {
              for await (const chunk of result.textStream) {
                const data = JSON.stringify({ text: chunk });
                controller.enqueue(encoder.encode(`data: ${data}\n\n`));
              }
              controller.enqueue(encoder.encode('data: [DONE]\n\n'));
            } catch (error) {
              controller.error(error);
            } finally {
              controller.close();
            }
          },
        });

        return new Response(stream, {
          headers: {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            ...getCorsHeaders(config.cors),
          },
        });
      }

      // Handle toDataStreamResponse if available (AI SDK)
      if (result.toDataStreamResponse) {
        return result.toDataStreamResponse();
      }

      // Handle regular response
      const responseData = typeof result === 'string' 
        ? { text: result }
        : result.text 
          ? { text: result.text, usage: result.usage }
          : result;

      return new Response(JSON.stringify(responseData), {
        headers: {
          'Content-Type': 'application/json',
          ...getCorsHeaders(config.cors),
        },
      });
    } catch (error: any) {
      console.error('Route handler error:', error);
      return new Response(
        JSON.stringify({ error: error.message || 'Internal server error' }),
        {
          status: 500,
          headers: {
            'Content-Type': 'application/json',
            ...getCorsHeaders(config.cors),
          },
        }
      );
    }
  };
}

/**
 * Create a Next.js Pages Router API handler.
 * 
 * @example pages/api/chat.ts
 * ```typescript
 * import { createPagesHandler } from 'praisonai/ai';
 * import { streamText } from 'praisonai/ai';
 * 
 * export default createPagesHandler({
 *   handler: async (input) => {
 *     return await streamText({
 *       model: 'gpt-4o',
 *       messages: input.messages
 *     });
 *   }
 * });
 * ```
 */
export function createPagesHandler(config: RouteHandlerConfig) {
  return async (req: any, res: any): Promise<void> => {
    try {
      // Set CORS headers
      if (config.cors) {
        const headers = getCorsHeaders(config.cors);
        for (const [key, value] of Object.entries(headers)) {
          res.setHeader(key, value);
        }
      }

      // Handle preflight
      if (req.method === 'OPTIONS') {
        res.status(204).end();
        return;
      }

      // Execute handler
      const result = await config.handler(req.body);

      // Handle streaming response
      if (config.streaming !== false && result.textStream) {
        res.setHeader('Content-Type', 'text/event-stream');
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader('Connection', 'keep-alive');

        for await (const chunk of result.textStream) {
          res.write(`data: ${JSON.stringify({ text: chunk })}\n\n`);
        }
        res.write('data: [DONE]\n\n');
        res.end();
        return;
      }

      // Handle regular response
      const responseData = typeof result === 'string' 
        ? { text: result }
        : result.text 
          ? { text: result.text, usage: result.usage }
          : result;

      res.status(200).json(responseData);
    } catch (error: any) {
      console.error('Pages handler error:', error);
      res.status(500).json({ error: error.message || 'Internal server error' });
    }
  };
}

/**
 * Get CORS headers based on configuration.
 */
function getCorsHeaders(cors?: boolean | { origin?: string | string[]; methods?: string[] }): Record<string, string> {
  if (!cors) return {};

  const config = typeof cors === 'boolean' 
    ? { origin: '*', methods: ['GET', 'POST', 'OPTIONS'] }
    : cors;

  const origin = Array.isArray(config.origin) 
    ? config.origin.join(', ') 
    : (config.origin || '*');

  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': (config.methods || ['GET', 'POST', 'OPTIONS']).join(', '),
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
  };
}

/**
 * Configuration for useChat hook wrapper.
 */
export interface UseChatConfig {
  /** API endpoint */
  api?: string;
  /** Initial messages */
  initialMessages?: Array<{ role: string; content: string }>;
  /** On error callback */
  onError?: (error: Error) => void;
  /** On finish callback */
  onFinish?: (message: any) => void;
  /** Custom headers */
  headers?: Record<string, string>;
  /** Custom body */
  body?: Record<string, any>;
}

/**
 * Note: For React hooks (useChat, useCompletion, useObject), 
 * use the AI SDK React package directly:
 * 
 * ```typescript
 * import { useChat } from 'ai/react';
 * 
 * function ChatComponent() {
 *   const { messages, input, handleInputChange, handleSubmit } = useChat({
 *     api: '/api/chat'
 *   });
 *   
 *   return (
 *     <form onSubmit={handleSubmit}>
 *       {messages.map(m => <div key={m.id}>{m.content}</div>)}
 *       <input value={input} onChange={handleInputChange} />
 *     </form>
 *   );
 * }
 * ```
 * 
 * The praisonai package focuses on server-side functionality.
 * For client-side React hooks, install and use 'ai/react' directly.
 */

/**
 * Export runtime configuration for Next.js edge runtime.
 */
export const runtime = 'edge';

/**
 * Export max duration configuration.
 */
export const maxDuration = 30;
