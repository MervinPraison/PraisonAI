/**
 * Repo Map - Repository structure visualization and symbol extraction
 */

export interface RepoMapConfig {
  rootPath: string;
  maxDepth?: number;
  ignorePatterns?: string[];
  includeSymbols?: boolean;
  maxFiles?: number;
}

export interface FileInfo {
  path: string;
  relativePath: string;
  size: number;
  isDirectory: boolean;
  children?: FileInfo[];
  symbols?: SymbolInfo[];
}

export interface SymbolInfo {
  name: string;
  type: 'function' | 'class' | 'method' | 'variable' | 'interface' | 'type' | 'export';
  line: number;
  exported?: boolean;
}

export interface RepoMapResult {
  root: string;
  tree: FileInfo;
  totalFiles: number;
  totalDirectories: number;
  symbols: SymbolInfo[];
  summary: string;
}

/**
 * Default ignore patterns
 */
export const DEFAULT_IGNORE_PATTERNS = [
  'node_modules',
  '.git',
  'dist',
  'build',
  '.next',
  '.nuxt',
  'coverage',
  '.cache',
  '__pycache__',
  '.pytest_cache',
  'venv',
  '.venv',
  '*.pyc',
  '*.pyo',
  '.DS_Store',
  'Thumbs.db',
  '*.log',
  '*.lock'
];

/**
 * RepoMap class for repository analysis
 */
export class RepoMap {
  private config: RepoMapConfig;
  private fs: any;
  private path: any;

  constructor(config: RepoMapConfig) {
    this.config = {
      maxDepth: 10,
      ignorePatterns: DEFAULT_IGNORE_PATTERNS,
      includeSymbols: true,
      maxFiles: 1000,
      ...config
    };
  }

  /**
   * Generate repository map
   */
  async generate(): Promise<RepoMapResult> {
    this.fs = await import('fs/promises');
    this.path = await import('path');

    const tree = await this.scanDirectory(this.config.rootPath, 0);
    const { files, directories } = this.countItems(tree);
    const symbols = this.config.includeSymbols ? this.collectSymbols(tree) : [];

    return {
      root: this.config.rootPath,
      tree,
      totalFiles: files,
      totalDirectories: directories,
      symbols,
      summary: this.generateSummary(tree, files, directories, symbols.length)
    };
  }

  /**
   * Scan a directory recursively
   */
  private async scanDirectory(dirPath: string, depth: number): Promise<FileInfo> {
    const relativePath = this.path.relative(this.config.rootPath, dirPath);
    const stats = await this.fs.stat(dirPath);

    const info: FileInfo = {
      path: dirPath,
      relativePath: relativePath || '.',
      size: stats.size,
      isDirectory: stats.isDirectory()
    };

    if (!stats.isDirectory() || depth >= (this.config.maxDepth || 10)) {
      return info;
    }

    const entries = await this.fs.readdir(dirPath, { withFileTypes: true });
    info.children = [];

    for (const entry of entries) {
      if (this.shouldIgnore(entry.name)) continue;

      const entryPath = this.path.join(dirPath, entry.name);
      
      if (entry.isDirectory()) {
        const child = await this.scanDirectory(entryPath, depth + 1);
        info.children.push(child);
      } else {
        const fileStats = await this.fs.stat(entryPath).catch(() => null);
        if (!fileStats) continue;

        const fileInfo: FileInfo = {
          path: entryPath,
          relativePath: this.path.relative(this.config.rootPath, entryPath),
          size: fileStats.size,
          isDirectory: false
        };

        if (this.config.includeSymbols && this.isCodeFile(entry.name)) {
          fileInfo.symbols = await this.extractSymbols(entryPath);
        }

        info.children.push(fileInfo);
      }
    }

    // Sort: directories first, then files alphabetically
    info.children.sort((a, b) => {
      if (a.isDirectory !== b.isDirectory) {
        return a.isDirectory ? -1 : 1;
      }
      return a.relativePath.localeCompare(b.relativePath);
    });

    return info;
  }

  /**
   * Check if path should be ignored
   */
  private shouldIgnore(name: string): boolean {
    for (const pattern of this.config.ignorePatterns || []) {
      if (pattern.startsWith('*')) {
        if (name.endsWith(pattern.slice(1))) return true;
      } else if (name === pattern) {
        return true;
      }
    }
    return false;
  }

  /**
   * Check if file is a code file
   */
  private isCodeFile(name: string): boolean {
    const codeExtensions = ['.ts', '.tsx', '.js', '.jsx', '.py', '.go', '.rs', '.java', '.rb', '.php'];
    return codeExtensions.some(ext => name.endsWith(ext));
  }

  /**
   * Extract symbols from a file
   */
  private async extractSymbols(filePath: string): Promise<SymbolInfo[]> {
    try {
      const content = await this.fs.readFile(filePath, 'utf-8');
      const ext = this.path.extname(filePath);

      switch (ext) {
        case '.ts':
        case '.tsx':
        case '.js':
        case '.jsx':
          return this.extractJSSymbols(content);
        case '.py':
          return this.extractPythonSymbols(content);
        default:
          return [];
      }
    } catch {
      return [];
    }
  }

  /**
   * Extract symbols from JavaScript/TypeScript
   */
  private extractJSSymbols(content: string): SymbolInfo[] {
    const symbols: SymbolInfo[] = [];
    const lines = content.split('\n');

    const patterns = [
      { regex: /^export\s+(?:async\s+)?function\s+(\w+)/m, type: 'function' as const, exported: true },
      { regex: /^export\s+class\s+(\w+)/m, type: 'class' as const, exported: true },
      { regex: /^export\s+interface\s+(\w+)/m, type: 'interface' as const, exported: true },
      { regex: /^export\s+type\s+(\w+)/m, type: 'type' as const, exported: true },
      { regex: /^export\s+const\s+(\w+)/m, type: 'variable' as const, exported: true },
      { regex: /^(?:async\s+)?function\s+(\w+)/m, type: 'function' as const },
      { regex: /^class\s+(\w+)/m, type: 'class' as const },
      { regex: /^interface\s+(\w+)/m, type: 'interface' as const },
      { regex: /^type\s+(\w+)/m, type: 'type' as const },
      { regex: /^const\s+(\w+)\s*=/m, type: 'variable' as const },
    ];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      for (const { regex, type, exported } of patterns) {
        const match = line.match(regex);
        if (match) {
          symbols.push({
            name: match[1],
            type,
            line: i + 1,
            exported
          });
          break;
        }
      }
    }

    return symbols;
  }

  /**
   * Extract symbols from Python
   */
  private extractPythonSymbols(content: string): SymbolInfo[] {
    const symbols: SymbolInfo[] = [];
    const lines = content.split('\n');

    const patterns = [
      { regex: /^def\s+(\w+)\s*\(/m, type: 'function' as const },
      { regex: /^async\s+def\s+(\w+)\s*\(/m, type: 'function' as const },
      { regex: /^class\s+(\w+)/m, type: 'class' as const },
    ];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      // Skip indented definitions (methods)
      if (line.startsWith(' ') || line.startsWith('\t')) continue;
      
      for (const { regex, type } of patterns) {
        const match = line.match(regex);
        if (match) {
          symbols.push({
            name: match[1],
            type,
            line: i + 1
          });
          break;
        }
      }
    }

    return symbols;
  }

  /**
   * Count files and directories
   */
  private countItems(tree: FileInfo): { files: number; directories: number } {
    let files = 0;
    let directories = 0;

    const count = (node: FileInfo) => {
      if (node.isDirectory) {
        directories++;
        for (const child of node.children || []) {
          count(child);
        }
      } else {
        files++;
      }
    };

    count(tree);
    return { files, directories };
  }

  /**
   * Collect all symbols from tree
   */
  private collectSymbols(tree: FileInfo): SymbolInfo[] {
    const symbols: SymbolInfo[] = [];

    const collect = (node: FileInfo) => {
      if (node.symbols) {
        symbols.push(...node.symbols);
      }
      for (const child of node.children || []) {
        collect(child);
      }
    };

    collect(tree);
    return symbols;
  }

  /**
   * Generate text summary
   */
  private generateSummary(tree: FileInfo, files: number, directories: number, symbolCount: number): string {
    const lines: string[] = [];
    lines.push(`Repository: ${this.config.rootPath}`);
    lines.push(`Files: ${files}, Directories: ${directories}, Symbols: ${symbolCount}`);
    lines.push('');
    lines.push(this.renderTree(tree, ''));
    return lines.join('\n');
  }

  /**
   * Render tree as text
   */
  private renderTree(node: FileInfo, prefix: string): string {
    const lines: string[] = [];
    const name = this.path.basename(node.path);
    
    if (node.isDirectory) {
      lines.push(`${prefix}${name}/`);
      const children = node.children || [];
      for (let i = 0; i < children.length; i++) {
        const isLast = i === children.length - 1;
        const childPrefix = prefix + (isLast ? '└── ' : '├── ');
        const nextPrefix = prefix + (isLast ? '    ' : '│   ');
        lines.push(this.renderTree(children[i], childPrefix).replace(childPrefix, ''));
        
        // Add children lines with proper prefix
        const childLines = this.renderTree(children[i], nextPrefix).split('\n').slice(1);
        lines.push(...childLines);
      }
    } else {
      const symbolCount = node.symbols?.length || 0;
      const symbolSuffix = symbolCount > 0 ? ` (${symbolCount} symbols)` : '';
      lines.push(`${prefix}${name}${symbolSuffix}`);
    }

    return lines.join('\n');
  }

  /**
   * Get tree as simple text format
   */
  async getTreeText(): Promise<string> {
    const result = await this.generate();
    return result.summary;
  }
}

/**
 * Create a repo map instance
 */
export function createRepoMap(config: RepoMapConfig): RepoMap {
  return new RepoMap(config);
}

/**
 * Quick function to get repo tree
 */
export async function getRepoTree(rootPath: string, maxDepth?: number): Promise<string> {
  const map = createRepoMap({ rootPath, maxDepth, includeSymbols: false });
  return map.getTreeText();
}
