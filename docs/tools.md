# Tools

<iframe width="560" height="315" src="https://www.youtube.com/embed/XaQRgRpV7jo" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>

## Inbuild Tools

- CodeDocsSearchTool
- CSVSearchTool
- DirectorySearchTool
- DirectoryReadTool
- DOCXSearchTool
- FileReadTool
- GithubSearchTool
- SerperDevTool
- TXTSearchTool
- JSONSearchTool
- MDXSearchTool
- PDFSearchTool
- PGSearchTool
- RagTool
- ScrapeElementFromWebsiteTool
- ScrapeWebsiteTool
- SeleniumScrapingTool
- WebsiteSearchTool
- XMLSearchTool
- YoutubeChannelSearchTool
- YoutubeVideoSearchTool

## Example Usage

```yaml
framework: crewai
topic: research about the causes of lung disease
roles:
  research_analyst:
    backstory: Experienced in analyzing scientific data related to respiratory health.
    goal: Analyze data on lung diseases
    role: Research Analyst
    tasks:
      data_analysis:
        description: Gather and analyze data on the causes and risk factors of lung diseases.
        expected_output: Report detailing key findings on lung disease causes.
    tools:
    - WebsiteSearchTool
```