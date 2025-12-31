/**
 * Exa Web Search Tool Example
 * 
 * Demonstrates semantic web search with Exa AI.
 * 
 * Prerequisites:
 *   npm install praisonai-ts @exalabs/ai-sdk
 *   export EXA_API_KEY=your-api-key
 *   export OPENAI_API_KEY=your-api-key
 */

// For local development, use relative imports
// For production, use: import { Agent, exaSearch } from 'praisonai-ts'
import { Agent } from '../../../src/praisonai-ts/src';
import { exaSearch } from '../../../src/praisonai-ts/src/tools/builtins';

async function main() {
  console.log('=== Exa Web Search Tool Example ===\n');

  // Example 1: Basic Semantic Search
  console.log('1. Basic Semantic Search');
  console.log('------------------------');
  
  const searchAgent = new Agent({
    name: 'SemanticSearcher',
    instructions: 'You search the web using semantic search and provide detailed summaries.',
    tools: [exaSearch({ numResults: 5, type: 'auto' })],
  });

  const searchResult = await searchAgent.chat('Find the latest AI research breakthroughs');
  console.log('Search Result:', searchResult);
  console.log();

  // Example 2: Company Research
  console.log('2. Company Research');
  console.log('-------------------');
  
  const companyAgent = new Agent({
    name: 'CompanyResearcher',
    instructions: 'You research companies and provide analysis.',
    tools: [
      exaSearch({
        type: 'auto',
        numResults: 5,
        category: 'company',
        contents: {
          text: { maxCharacters: 1000 },
          summary: true,
          livecrawl: 'preferred',
        },
      }),
    ],
  });

  const companyResult = await companyAgent.chat(
    'Find AI startups in Europe founded after 2020'
  );
  console.log('Company Result:', companyResult);
  console.log();

  // Example 3: Academic Paper Search
  console.log('3. Academic Paper Search');
  console.log('------------------------');
  
  const academicAgent = new Agent({
    name: 'AcademicResearcher',
    instructions: 'You search for academic papers and summarize findings.',
    tools: [
      exaSearch({
        type: 'neural',
        category: 'research paper',
        numResults: 5,
        includeDomains: ['arxiv.org', 'nature.com', 'science.org'],
      }),
    ],
  });

  const academicResult = await academicAgent.chat(
    'Find recent papers on transformer architectures and attention mechanisms'
  );
  console.log('Academic Result:', academicResult);
}

main().catch(console.error);
