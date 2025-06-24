import { ArxivSearchTool, ArxivDownloadTool } from '../src/tools/arxivTools';

async function main() {
    // Initialize tools
    const searchTool = new ArxivSearchTool();
    const downloadTool = new ArxivDownloadTool();

    try {
        // Search for papers about quantum computing
        console.log('Searching for quantum computing papers...');
        const papers = await searchTool.execute('quantum computing', 5);
        
        console.log('\nSearch Results:');
        papers.forEach((paper, index) => {
            console.log(`\n${index + 1}. ${paper.title}`);
            console.log(`   Authors: ${paper.authors.join(', ')}`);
            console.log(`   Published: ${paper.published}`);
            console.log(`   Summary: ${paper.summary.substring(0, 200)}...`);
        });

        // Download the first paper if any results found
        if (papers.length > 0) {
            console.log('\nDownloading the first paper...');
            const pdfBuffer = await downloadTool.execute(papers[0].id);
            console.log(`Downloaded PDF size: ${pdfBuffer.length} bytes`);
        }
    } catch (error: any) {
        console.error('Error:', error?.message || 'An unknown error occurred');
    }
}

main();
