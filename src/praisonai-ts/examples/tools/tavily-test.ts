/**
 * Tavily Search Tool Test
 * 
 * Tests the Tavily search tool with a real API key.
 * Run with: TAVILY_API_KEY=your-key npx ts-node examples/tools/tavily-test.ts
 */

import { tavilySearch } from '../../src/tools/builtins/tavily';

async function main() {
  console.log('Testing Tavily Search Tool...\n');
  
  // Check for API key
  if (!process.env.TAVILY_API_KEY) {
    console.error('ERROR: TAVILY_API_KEY environment variable is required');
    process.exit(1);
  }
  
  console.log('API Key found: ' + process.env.TAVILY_API_KEY.substring(0, 10) + '...\n');

  try {
    // Create the tool
    const tool = tavilySearch({ includeAnswer: true, maxResults: 3 });
    
    console.log('Tool created:', tool.name);
    console.log('Description:', tool.description);
    console.log('\nExecuting search for "latest AI developments 2024"...\n');
    
    // Execute the search
    const result = await tool.execute({ query: 'latest AI developments 2024' });
    
    console.log('=== Search Results ===\n');
    
    if (result.answer) {
      console.log('AI Answer:', result.answer.substring(0, 200) + '...\n');
    }
    
    console.log(`Found ${result.results.length} results:\n`);
    
    for (const r of result.results) {
      console.log(`- ${r.title}`);
      console.log(`  URL: ${r.url}`);
      console.log(`  Score: ${r.score}`);
      console.log(`  Content: ${r.content.substring(0, 100)}...`);
      console.log('');
    }
    
    console.log('Response time:', result.responseTime, 'ms');
    console.log('\n✅ Tavily search test PASSED!');
    
  } catch (error) {
    console.error('❌ Test FAILED:', error);
    process.exit(1);
  }
}

main();
