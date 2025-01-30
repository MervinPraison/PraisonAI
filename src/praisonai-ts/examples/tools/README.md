# Tool Examples

This directory contains examples of using various tools from the PraisonAI package.

## Available Examples

### ArXiv Tools
File: `arxiv-tools.ts`

Demonstrates how to:
- Search for academic papers on ArXiv
- Display paper information (title, authors, summary)
- Download papers as PDF files

To run:
```bash
npx ts-node examples/tools/arxiv-tools.ts
```

The downloaded PDFs will be saved in the `examples/downloads` directory.

## Usage in Your Code

You can use these tools in your own code by importing them from the package:

```typescript
import { ArxivSearchTool, ArxivDownloadTool } from 'praisonai';

// Create tool instances
const searchTool = new ArxivSearchTool();
const downloadTool = new ArxivDownloadTool();

// Search for papers
const papers = await searchTool.execute('your search query', 5);

// Download a paper
const pdfBuffer = await downloadTool.execute(papers[0].id);
```
