import { Agent, PraisonAIAgents } from 'praisonai';

// Create research agent
const researchAgent = new Agent({
  instructions: `You are an AI research expert. Conduct comprehensive research about artificial intelligence,
focusing on:
1. Current state of AI technology
2. Major breakthroughs and developments
3. Key applications and use cases
4. Future trends and predictions
5. Ethical considerations

Format your response in markdown with clear sections and bullet points.`,
  name: "ResearchAgent",
  verbose: true
});

// Create summarize agent
const summarizeAgent = new Agent({
  instructions: `You are a professional technical writer. Create a concise executive summary of the research findings about AI.
The summary should:
1. Highlight key points and insights
2. Be clear and accessible to non-technical readers
3. Include actionable takeaways
4. Be no more than 500 words

Here is the research to summarize:
{previous_result}`,
  name: "SummarizeAgent",
  verbose: true
});

// Create PraisonAIAgents instance
const agents = new PraisonAIAgents({
  agents: [researchAgent, summarizeAgent],
  tasks: ["Research current state and future of AI", "Create executive summary"],
  verbose: true
});

// Chat with agents
agents.chat()
  .then(results => {
    console.log('\nFinal Results:');
    results.forEach((result, index) => {
      console.log(`\nAgent ${index + 1} Result:`);
      console.log(result);
    });
  })
  .catch(error => {
    console.error('Error:', error);
  });
