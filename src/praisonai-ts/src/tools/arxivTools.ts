import axios from 'axios';
import { XMLParser } from 'fast-xml-parser';
import { BaseTool } from './base';

export interface ArxivPaper {
  id: string;
  title: string;
  authors: string[];
  summary: string;
  published: string;
  updated: string;
  link: string;
}

export class ArxivSearchTool extends BaseTool<{ query: string; maxResults?: number }, ArxivPaper[]> {
  name = 'arxiv-search';
  description = 'Search for academic papers on arXiv';
  private parser: XMLParser;

  constructor() {
    super();
    this.parser = new XMLParser({
      ignoreAttributes: false,
      attributeNamePrefix: '@_'
    });
  }

  async run(params: { query: string; maxResults?: number }): Promise<ArxivPaper[]> {
    const { query, maxResults = 10 } = params;
    try {
      const response = await axios.get(`http://export.arxiv.org/api/query`, {
        params: {
          search_query: encodeURIComponent(query),
          max_results: maxResults,
          sortBy: 'lastUpdatedDate',
          sortOrder: 'descending'
        }
      });

      const parsed = this.parser.parse(response.data);
      const entries = parsed.feed.entry;

      if (!entries) {
        return [];
      }

      // Handle both single and multiple entries
      const entriesArray = Array.isArray(entries) ? entries : [entries];

      return entriesArray.map((entry: any) => ({
        id: entry.id.split('/abs/')[1],
        title: entry.title.replace(/\s+/g, ' ').trim(),
        authors: Array.isArray(entry.author) 
          ? entry.author.map((a: any) => a.name)
          : [entry.author.name],
        summary: entry.summary.replace(/\s+/g, ' ').trim(),
        published: entry.published,
        updated: entry.updated,
        link: entry.id
      }));
    } catch (error) {
      if (error instanceof Error) {
        throw new Error(`Failed to search arXiv: ${error.message}`);
      }
      throw new Error('Failed to search arXiv: Unknown error');
    }
  }
}

export class ArxivDownloadTool extends BaseTool<{ paperId: string }, Buffer> {
  name = 'arxiv-download';
  description = 'Download PDF of an arXiv paper';

  async run(params: { paperId: string }): Promise<Buffer> {
    const { paperId } = params;
    try {
      const response = await axios.get(`https://arxiv.org/pdf/${paperId}.pdf`, {
        responseType: 'arraybuffer'
      });
      return Buffer.from(response.data);
    } catch (error) {
      if (error instanceof Error) {
        throw new Error(`Failed to download paper: ${error.message}`);
      }
      throw new Error('Failed to download paper: Unknown error');
    }
  }
}