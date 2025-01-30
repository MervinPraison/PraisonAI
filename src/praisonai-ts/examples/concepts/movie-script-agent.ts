import { Agent, PraisonAIAgents } from 'praisonai';

async function main() {
    // Create a script writing agent
    const scriptAgent = new Agent({
        name: "ScriptWriter",
        role: "Professional Screenwriter",
        goal: "Write an engaging and creative movie script",
        backstory: "You are an experienced screenwriter who specializes in science fiction scripts",
        instructions: `Write a compelling movie script about a robot stranded on Mars.
The script should include:
1. Scene descriptions
2. Character dialogue
3. Emotional moments
4. Scientific accuracy where possible
5. A clear three-act structure

Format the output in proper screenplay format.`,
        verbose: true,
        markdown: true
    });

    // Create PraisonAI instance with our agent
    const praisonAI = new PraisonAIAgents({
        agents: [scriptAgent],
        tasks: ["Write a movie script about a robot stranded on Mars"],
        verbose: true
    });

    try {
        console.log('Starting script writing agent...');
        const results = await praisonAI.start();
        console.log('\nMovie Script:');
        console.log(results[0]); // First result contains our script
    } catch (error) {
        console.error('Error:', error);
    }
}

// Run the example
if (require.main === module) {
    main();
}
