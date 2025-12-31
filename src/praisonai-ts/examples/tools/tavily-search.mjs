/**
 * Tavily Search Tool Example
 * 
 * Demonstrates using Tavily search with PraisonAI agents.
 * 
 * Run with: 
 *   TAVILY_API_KEY=your-key node examples/tools/tavily-search.mjs
 */

import { tavilySearch } from '@tavily/ai-sdk';

async function main() {
  console.log('=== Tavily Search Example ===\n');
  
  // Check for API key
  if (!process.env.TAVILY_API_KEY) {
    console.error('ERROR: TAVILY_API_KEY environment variable is required');
    console.error('Get your API key at: https://tavily.com');
    process.exit(1);
  }

  // Create the Tavily search tool
  const searchTool = tavilySearch({
    apiKey: process.env.TAVILY_API_KEY,
    searchDepth: 'basic',
    maxResults: 5,
    includeAnswer: true,
  });

  console.log('Tool:', searchTool.description);
  console.log('\nSearching for: "latest AI agent frameworks 2024"\n');

  try {
    // Execute the search
    const result = await searchTool.execute(
      { query: 'latest AI agent frameworks 2024' },
      { toolCallId: 'search-1', messages: [] }
    );

    console.log('=== Results ===\n');
    console.log('Query:', result.query);
    console.log('Response Time:', result.responseTime, 'ms');
    
    if (result.answer) {
      console.log('\nAI Answer:', result.answer);
    }

    console.log('\nTop Results:');
    for (const r of result.results || []) {
      console.log(`\n• ${r.title}`);
      console.log(`  URL: ${r.url}`);
      console.log(`  Score: ${r.score?.toFixed(3)}`);
      console.log(`  ${r.content.substring(0, 150)}...`);
    }

    console.log('\n✅ Search completed successfully!');
  } catch (error) {
    console.error('❌ Search failed:', error.message);
    process.exit(1);
  }
}

main();
