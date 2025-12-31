/**
 * Tavily Search Tool Example
 * 
 * Demonstrates web search, content extraction, and crawling with Tavily.
 * 
 * Prerequisites:
 *   npm install praisonai @tavily/ai-sdk
 *   export TAVILY_API_KEY=your-api-key
 *   export OPENAI_API_KEY=your-api-key
 */

// For local development, use relative imports
// For production, use: import { Agent, tavilySearch } from 'praisonai-ts'
import { Agent } from '../../../src/praisonai-ts/src';
import { tavilySearch, tavilyExtract, tavilyCrawl } from '../../../src/praisonai-ts/src/tools/builtins';

async function main() {
  console.log('=== Tavily Search Tool Example ===\n');

  // Example 1: Basic Web Search
  console.log('1. Basic Web Search');
  console.log('-------------------');
  
  const searchAgent = new Agent({
    name: 'WebSearcher',
    instructions: 'You search the web for information and provide concise summaries with sources.',
    tools: [tavilySearch({ maxResults: 5, includeAnswer: true })],
  });

  const searchResult = await searchAgent.chat('What are the latest developments in AI agents?');
  console.log('Search Result:', searchResult);
  console.log();

  // Example 2: News Search with Time Filter
  console.log('2. News Search with Time Filter');
  console.log('-------------------------------');
  
  const newsAgent = new Agent({
    name: 'NewsSearcher',
    instructions: 'You search for recent news and summarize key points.',
    tools: [
      tavilySearch({
        topic: 'news',
        timeRange: 'week',
        maxResults: 5,
      }),
    ],
  });

  const newsResult = await newsAgent.chat('Latest news about OpenAI');
  console.log('News Result:', newsResult);
  console.log();

  // Example 3: Content Extraction
  console.log('3. Content Extraction');
  console.log('--------------------');
  
  const extractAgent = new Agent({
    name: 'ContentExtractor',
    instructions: 'You extract and summarize content from web pages.',
    tools: [tavilyExtract()],
  });

  const extractResult = await extractAgent.chat(
    'Extract the main content from https://docs.tavily.com and summarize it'
  );
  console.log('Extract Result:', extractResult);
  console.log();

  // Example 4: Website Crawling
  console.log('4. Website Crawling');
  console.log('------------------');
  
  const crawlAgent = new Agent({
    name: 'WebCrawler',
    instructions: 'You crawl websites and analyze their structure and content.',
    tools: [tavilyCrawl({ maxDepth: 2 })],
  });

  const crawlResult = await crawlAgent.chat(
    'Crawl https://docs.tavily.com and list the main documentation sections'
  );
  console.log('Crawl Result:', crawlResult);
}

main().catch(console.error);
