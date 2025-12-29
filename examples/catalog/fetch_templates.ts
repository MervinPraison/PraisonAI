#!/usr/bin/env npx ts-node
/**
 * Example: Fetch and search PraisonAI templates from the catalog.
 * 
 * This TypeScript example demonstrates how to:
 * - Fetch templates.json from the deployed catalog
 * - Search templates by keyword
 * - Filter by tags and requirements
 * - Generate CLI commands
 */

const CATALOG_URL = "https://mervinpraison.github.io/praisonai-template-catalog/data/templates.json";

interface Template {
  name: string;
  version: string;
  description: string;
  author?: string;
  license?: string;
  tags?: string[];
  category?: string;
  difficulty?: "beginner" | "intermediate" | "advanced";
  requires?: {
    tools?: string[];
    packages?: string[];
    env?: string[];
  };
}

interface Catalog {
  version: string;
  generated_at: string;
  count: number;
  templates: Template[];
}

async function fetchCatalog(url: string = CATALOG_URL): Promise<Catalog> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch catalog: ${response.statusText}`);
  }
  return response.json();
}

function searchTemplates(templates: Template[], query: string): Template[] {
  const q = query.toLowerCase();
  return templates.filter(t =>
    t.name.toLowerCase().includes(q) ||
    t.description?.toLowerCase().includes(q) ||
    t.tags?.some(tag => tag.toLowerCase().includes(q))
  );
}

function filterByTags(templates: Template[], tags: string[]): Template[] {
  return templates.filter(t =>
    tags.every(tag => t.tags?.includes(tag))
  );
}

function filterByTool(templates: Template[], toolName: string): Template[] {
  return templates.filter(t =>
    t.requires?.tools?.includes(toolName)
  );
}

function getTemplate(templates: Template[], name: string): Template | undefined {
  return templates.find(t => t.name === name);
}

function generateCLICommand(template: Template, action: string = "run"): string {
  const name = template.name;
  switch (action) {
    case "run":
      return `praisonai templates run ${name}`;
    case "info":
      return `praisonai templates info ${name}`;
    case "init":
      return `praisonai templates init my-project --template ${name}`;
    default:
      return `praisonai templates ${action} ${name}`;
  }
}

function printTemplateSummary(template: Template): void {
  console.log("\n" + "=".repeat(60));
  console.log(`Name: ${template.name}`);
  console.log(`Version: ${template.version}`);
  console.log(`Description: ${template.description?.slice(0, 100)}...`);
  console.log(`Tags: ${template.tags?.join(", ") || "none"}`);
  
  const requires = template.requires;
  if (requires?.tools?.length) {
    console.log(`Tools: ${requires.tools.join(", ")}`);
  }
  if (requires?.packages?.length) {
    console.log(`Packages: ${requires.packages.join(", ")}`);
  }
  if (requires?.env?.length) {
    console.log(`Env vars: ${requires.env.join(", ")}`);
  }
  
  console.log(`\nRun: ${generateCLICommand(template, "run")}`);
  console.log("=".repeat(60));
}

async function main(): Promise<void> {
  console.log("PraisonAI Template Catalog - TypeScript Example");
  console.log("-".repeat(45));
  
  // Fetch catalog
  console.log("\n1. Fetching template catalog...");
  let catalog: Catalog;
  try {
    catalog = await fetchCatalog();
  } catch (error) {
    console.log(`   Failed to fetch: ${error}`);
    console.log("   The catalog may not be deployed yet.");
    return;
  }
  
  const templates = catalog.templates;
  console.log(`   Catalog version: ${catalog.version}`);
  console.log(`   Total templates: ${templates.length}`);
  
  if (templates.length === 0) {
    console.log("   No templates found.");
    return;
  }
  
  // List all templates
  console.log("\n2. Available templates:");
  templates.forEach(t => {
    console.log(`   - ${t.name} (v${t.version})`);
  });
  
  // Search for video templates
  console.log("\n3. Searching for 'video' templates...");
  const videoTemplates = searchTemplates(templates, "video");
  console.log(`   Found ${videoTemplates.length} video templates:`);
  videoTemplates.forEach(t => {
    console.log(`   - ${t.name}: ${t.description?.slice(0, 50)}...`);
  });
  
  // Filter by tool
  console.log("\n4. Templates using 'shell_tool':");
  const shellTemplates = filterByTool(templates, "shell_tool");
  shellTemplates.forEach(t => {
    console.log(`   - ${t.name}`);
  });
  
  // Get specific template details
  if (templates.length > 0) {
    const firstTemplate = templates[0];
    console.log(`\n5. Template details for '${firstTemplate.name}':`);
    printTemplateSummary(firstTemplate);
  }
  
  // Generate CLI commands
  console.log("\n6. CLI commands for all templates:");
  templates.slice(0, 5).forEach(t => {
    console.log(`   ${generateCLICommand(t, "run")}`);
  });
  
  console.log("\nDone!");
}

main().catch(console.error);
