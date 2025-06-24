import { ArxivSearchTool, ArxivDownloadTool } from '../../src/tools/arxivTools';
import * as fs from 'fs';
import * as path from 'path';

async function searchPapers() {
    const searchTool = new ArxivSearchTool();
    const query = 'quantum computing';
    const maxResults = 5;

    console.log(`Searching for papers about "${query}"...`);
    const papers = await searchTool.execute(query, maxResults);
    
    console.log('\nSearch Results:');
    papers.forEach((paper, index) => {
        console.log(`\n${index + 1}. ${paper.title}`);
        console.log(`   Authors: ${paper.authors.join(', ')}`);
        console.log(`   Published: ${paper.published}`);
        console.log(`   Summary: ${paper.summary.substring(0, 200)}...`);
        console.log(`   ID: ${paper.id}`);
    });

    return papers;
}

async function downloadPaper(paperId: string) {
    const downloadTool = new ArxivDownloadTool();
    console.log(`\nDownloading paper ${paperId}...`);
    
    const pdfBuffer = await downloadTool.execute(paperId);
    
    // Create downloads directory if it doesn't exist
    const downloadDir = path.join(__dirname, '..', 'downloads');
    if (!fs.existsSync(downloadDir)) {
        fs.mkdirSync(downloadDir, { recursive: true });
    }

    // Save the PDF
    const pdfPath = path.join(downloadDir, `${paperId}.pdf`);
    fs.writeFileSync(pdfPath, pdfBuffer);
    
    console.log(`Downloaded PDF saved to: ${pdfPath}`);
    console.log(`File size: ${(pdfBuffer.length / 1024 / 1024).toFixed(2)} MB`);
}

async function main() {
    try {
        // Search for papers
        const papers = await searchPapers();

        // Download the first paper if any results found
        if (papers.length > 0) {
            await downloadPaper(papers[0].id);
        }
    } catch (error: any) {
        console.error('Error:', error?.message || 'An unknown error occurred');
    }
}

// Run the example if this file is executed directly
if (require.main === module) {
    main();
}
