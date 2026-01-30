/**
 * Flow Display - Textual DAG visualization for workflows
 */

export interface FlowNode {
  id: string;
  name: string;
  type: 'agent' | 'tool' | 'condition' | 'parallel' | 'start' | 'end';
  status?: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  children?: string[];
  metadata?: Record<string, any>;
}

export interface FlowGraph {
  nodes: Map<string, FlowNode>;
  edges: Array<{ from: string; to: string; label?: string }>;
}

export interface FlowDisplayConfig {
  showStatus?: boolean;
  showMetadata?: boolean;
  compact?: boolean;
  maxWidth?: number;
}

/**
 * Flow Display class for DAG visualization
 */
export class FlowDisplay {
  private graph: FlowGraph;
  private config: FlowDisplayConfig;

  constructor(config: FlowDisplayConfig = {}) {
    this.config = {
      showStatus: true,
      showMetadata: false,
      compact: false,
      maxWidth: 80,
      ...config
    };
    this.graph = {
      nodes: new Map(),
      edges: []
    };
  }

  /**
   * Add a node to the graph
   */
  addNode(node: FlowNode): void {
    this.graph.nodes.set(node.id, node);
  }

  /**
   * Add an edge between nodes
   */
  addEdge(from: string, to: string, label?: string): void {
    this.graph.edges.push({ from, to, label });
  }

  /**
   * Update node status
   */
  updateStatus(id: string, status: FlowNode['status']): void {
    const node = this.graph.nodes.get(id);
    if (node) {
      node.status = status;
    }
  }

  /**
   * Build graph from workflow steps
   */
  fromTasks(steps: Array<{ name: string; type?: string; condition?: string }>): void {
    this.graph.nodes.clear();
    this.graph.edges = [];

    // Add start node
    this.addNode({ id: 'start', name: 'Start', type: 'start' });

    let prevId = 'start';
    for (let i = 0; i < steps.length; i++) {
      const step = steps[i];
      const id = `step_${i}`;
      
      this.addNode({
        id,
        name: step.name,
        type: (step.type as FlowNode['type']) || 'agent',
        status: 'pending'
      });

      this.addEdge(prevId, id, step.condition);
      prevId = id;
    }

    // Add end node
    this.addNode({ id: 'end', name: 'End', type: 'end' });
    this.addEdge(prevId, 'end');
  }

  /**
   * Render the graph as text
   */
  render(): string {
    const lines: string[] = [];
    const visited = new Set<string>();

    // Find root nodes (nodes with no incoming edges)
    const hasIncoming = new Set(this.graph.edges.map(e => e.to));
    const roots = Array.from(this.graph.nodes.keys()).filter(id => !hasIncoming.has(id));

    if (roots.length === 0 && this.graph.nodes.size > 0) {
      const firstKey = this.graph.nodes.keys().next().value;
      if (firstKey) roots.push(firstKey);
    }

    for (const root of roots) {
      this.renderNode(root, '', true, lines, visited);
    }

    return lines.join('\n');
  }

  /**
   * Render a single node and its children
   */
  private renderNode(
    id: string,
    prefix: string,
    isLast: boolean,
    lines: string[],
    visited: Set<string>
  ): void {
    if (visited.has(id)) {
      lines.push(`${prefix}${isLast ? '└── ' : '├── '}(cycle: ${id})`);
      return;
    }
    visited.add(id);

    const node = this.graph.nodes.get(id);
    if (!node) return;

    const connector = isLast ? '└── ' : '├── ';
    const nodeStr = this.formatNode(node);
    lines.push(`${prefix}${connector}${nodeStr}`);

    // Find children
    const childEdges = this.graph.edges.filter(e => e.from === id);
    const childPrefix = prefix + (isLast ? '    ' : '│   ');

    for (let i = 0; i < childEdges.length; i++) {
      const edge = childEdges[i];
      const isLastChild = i === childEdges.length - 1;

      if (edge.label) {
        lines.push(`${childPrefix}${isLastChild ? '└' : '├'}─[${edge.label}]─┐`);
        this.renderNode(edge.to, childPrefix + (isLastChild ? '  ' : '│ '), true, lines, visited);
      } else {
        this.renderNode(edge.to, childPrefix, isLastChild, lines, visited);
      }
    }
  }

  /**
   * Format a node for display
   */
  private formatNode(node: FlowNode): string {
    const parts: string[] = [];

    // Status indicator
    if (this.config.showStatus && node.status) {
      const statusIcons: Record<string, string> = {
        pending: '○',
        running: '◐',
        completed: '●',
        failed: '✗',
        skipped: '◌'
      };
      parts.push(statusIcons[node.status] || '?');
    }

    // Type indicator
    const typeIcons: Record<string, string> = {
      agent: '🤖',
      tool: '🔧',
      condition: '❓',
      parallel: '⫘',
      start: '▶',
      end: '■'
    };
    
    if (!this.config.compact) {
      parts.push(typeIcons[node.type] || '□');
    }

    // Name
    parts.push(node.name);

    // Metadata
    if (this.config.showMetadata && node.metadata) {
      const meta = Object.entries(node.metadata)
        .map(([k, v]) => `${k}=${v}`)
        .join(', ');
      if (meta) {
        parts.push(`(${meta})`);
      }
    }

    return parts.join(' ');
  }

  /**
   * Render as simple ASCII box diagram
   */
  renderBoxes(): string {
    const lines: string[] = [];
    const nodeList = Array.from(this.graph.nodes.values());

    for (let i = 0; i < nodeList.length; i++) {
      const node = nodeList[i];
      const box = this.createBox(node);
      lines.push(...box);

      if (i < nodeList.length - 1) {
        lines.push('    │');
        lines.push('    ▼');
      }
    }

    return lines.join('\n');
  }

  /**
   * Create a box for a node
   */
  private createBox(node: FlowNode): string[] {
    const name = node.name;
    const width = Math.max(name.length + 4, 20);
    const padding = Math.floor((width - name.length - 2) / 2);

    const statusChar = this.config.showStatus ? this.getStatusChar(node.status) : '';
    const top = '┌' + '─'.repeat(width) + '┐';
    const middle = '│' + ' '.repeat(padding) + statusChar + name + ' '.repeat(width - padding - name.length - statusChar.length) + '│';
    const bottom = '└' + '─'.repeat(width) + '┘';

    return [top, middle, bottom];
  }

  /**
   * Get status character
   */
  private getStatusChar(status?: string): string {
    const chars: Record<string, string> = {
      pending: '○ ',
      running: '◐ ',
      completed: '● ',
      failed: '✗ ',
      skipped: '◌ '
    };
    return status ? (chars[status] || '') : '';
  }

  /**
   * Clear the graph
   */
  clear(): void {
    this.graph.nodes.clear();
    this.graph.edges = [];
  }

  /**
   * Get graph data
   */
  getGraph(): FlowGraph {
    return this.graph;
  }

  /**
   * Export to DOT format (for Graphviz)
   */
  toDot(): string {
    const lines: string[] = ['digraph workflow {'];
    lines.push('  rankdir=TB;');
    lines.push('  node [shape=box];');

    for (const [id, node] of this.graph.nodes) {
      const label = node.name.replace(/"/g, '\\"');
      const style = node.status === 'completed' ? 'filled' : '';
      const fillcolor = node.status === 'completed' ? 'lightgreen' : 
                        node.status === 'failed' ? 'lightcoral' : 'white';
      lines.push(`  "${id}" [label="${label}" style="${style}" fillcolor="${fillcolor}"];`);
    }

    for (const edge of this.graph.edges) {
      const label = edge.label ? ` [label="${edge.label}"]` : '';
      lines.push(`  "${edge.from}" -> "${edge.to}"${label};`);
    }

    lines.push('}');
    return lines.join('\n');
  }
}

/**
 * Create a flow display instance
 */
export function createFlowDisplay(config?: FlowDisplayConfig): FlowDisplay {
  return new FlowDisplay(config);
}

/**
 * Quick render workflow steps
 */
export function renderWorkflow(steps: Array<{ name: string; type?: string }>): string {
  const display = createFlowDisplay();
  display.fromTasks(steps);
  return display.render();
}
