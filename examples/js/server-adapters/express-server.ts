/**
 * Express Server Adapter Example
 * 
 * Demonstrates deploying an AI agent as an Express HTTP server.
 * 
 * Prerequisites:
 *   npm install praisonai-ts express
 *   export OPENAI_API_KEY=your-api-key
 * 
 * Run:
 *   npx ts-node express-server.ts
 * 
 * Test:
 *   curl -X POST http://localhost:3000/api/chat \
 *     -H "Content-Type: application/json" \
 *     -d '{"message": "Hello!"}'
 */

import { Agent } from '../../../src/praisonai-ts/src';

// Simple HTTP server without Express dependency for this example
import http from 'http';

async function main() {
  console.log('=== Express Server Adapter Example ===\n');

  // Create an agent
  const agent = new Agent({
    name: 'APIAgent',
    instructions: 'You are a helpful API assistant. Keep responses concise.',
  });

  // Create HTTP server
  const server = http.createServer(async (req, res) => {
    // CORS headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
      res.writeHead(200);
      res.end();
      return;
    }

    if (req.method === 'POST' && req.url === '/api/chat') {
      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', async () => {
        try {
          const { message } = JSON.parse(body);
          const response = await agent.chat(message);
          
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ response }));
        } catch (error: any) {
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: error.message }));
        }
      });
    } else {
      res.writeHead(404);
      res.end('Not Found');
    }
  });

  const PORT = process.env.PORT || 3000;
  server.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
    console.log('\nTest with:');
    console.log(`  curl -X POST http://localhost:${PORT}/api/chat \\`);
    console.log('    -H "Content-Type: application/json" \\');
    console.log('    -d \'{"message": "Hello!"}\'');
  });
}

main().catch(console.error);
