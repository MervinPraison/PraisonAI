/**
 * Graph RAG - Graph-based Retrieval Augmented Generation
 * Inspired by mastra's graph-rag module
 */

export interface GraphNode {
  id: string;
  type: string;
  content: string;
  metadata?: Record<string, any>;
  embedding?: number[];
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  weight?: number;
  metadata?: Record<string, any>;
}

export interface GraphQueryResult {
  nodes: GraphNode[];
  edges: GraphEdge[];
  paths: GraphNode[][];
  score: number;
}

export interface GraphRAGConfig {
  maxDepth?: number;
  maxNodes?: number;
  minScore?: number;
  includeEdges?: boolean;
}

/**
 * In-memory Graph Store for Graph RAG
 */
export class GraphStore {
  private nodes: Map<string, GraphNode> = new Map();
  private edges: Map<string, GraphEdge> = new Map();
  private adjacencyList: Map<string, Set<string>> = new Map();
  private reverseAdjacencyList: Map<string, Set<string>> = new Map();

  /**
   * Add a node to the graph
   */
  addNode(node: GraphNode): void {
    this.nodes.set(node.id, node);
    if (!this.adjacencyList.has(node.id)) {
      this.adjacencyList.set(node.id, new Set());
    }
    if (!this.reverseAdjacencyList.has(node.id)) {
      this.reverseAdjacencyList.set(node.id, new Set());
    }
  }

  /**
   * Add an edge to the graph
   */
  addEdge(edge: GraphEdge): void {
    this.edges.set(edge.id, edge);
    
    // Update adjacency lists
    if (!this.adjacencyList.has(edge.source)) {
      this.adjacencyList.set(edge.source, new Set());
    }
    this.adjacencyList.get(edge.source)!.add(edge.target);

    if (!this.reverseAdjacencyList.has(edge.target)) {
      this.reverseAdjacencyList.set(edge.target, new Set());
    }
    this.reverseAdjacencyList.get(edge.target)!.add(edge.source);
  }

  /**
   * Get a node by ID
   */
  getNode(id: string): GraphNode | undefined {
    return this.nodes.get(id);
  }

  /**
   * Get all nodes
   */
  getAllNodes(): GraphNode[] {
    return Array.from(this.nodes.values());
  }

  /**
   * Get neighbors of a node
   */
  getNeighbors(nodeId: string, direction: 'outgoing' | 'incoming' | 'both' = 'both'): GraphNode[] {
    const neighborIds = new Set<string>();

    if (direction === 'outgoing' || direction === 'both') {
      const outgoing = this.adjacencyList.get(nodeId);
      if (outgoing) {
        outgoing.forEach(id => neighborIds.add(id));
      }
    }

    if (direction === 'incoming' || direction === 'both') {
      const incoming = this.reverseAdjacencyList.get(nodeId);
      if (incoming) {
        incoming.forEach(id => neighborIds.add(id));
      }
    }

    return Array.from(neighborIds)
      .map(id => this.nodes.get(id))
      .filter((n): n is GraphNode => n !== undefined);
  }

  /**
   * Get edges between two nodes
   */
  getEdgesBetween(sourceId: string, targetId: string): GraphEdge[] {
    return Array.from(this.edges.values()).filter(
      e => (e.source === sourceId && e.target === targetId) ||
           (e.source === targetId && e.target === sourceId)
    );
  }

  /**
   * Find paths between two nodes using BFS
   */
  findPaths(startId: string, endId: string, maxDepth: number = 3): GraphNode[][] {
    const paths: GraphNode[][] = [];
    const queue: Array<{ path: string[]; visited: Set<string> }> = [
      { path: [startId], visited: new Set([startId]) }
    ];

    while (queue.length > 0) {
      const { path, visited } = queue.shift()!;
      const currentId = path[path.length - 1];

      if (currentId === endId) {
        paths.push(path.map(id => this.nodes.get(id)!).filter(n => n));
        continue;
      }

      if (path.length >= maxDepth) {
        continue;
      }

      const neighbors = this.adjacencyList.get(currentId) || new Set();
      for (const neighborId of neighbors) {
        if (!visited.has(neighborId)) {
          const newVisited = new Set(visited);
          newVisited.add(neighborId);
          queue.push({ path: [...path, neighborId], visited: newVisited });
        }
      }
    }

    return paths;
  }

  /**
   * Get subgraph around a node
   */
  getSubgraph(nodeId: string, depth: number = 2): { nodes: GraphNode[]; edges: GraphEdge[] } {
    const visitedNodes = new Set<string>();
    const resultEdges: GraphEdge[] = [];
    const queue: Array<{ id: string; currentDepth: number }> = [{ id: nodeId, currentDepth: 0 }];

    while (queue.length > 0) {
      const { id, currentDepth } = queue.shift()!;
      
      if (visitedNodes.has(id) || currentDepth > depth) {
        continue;
      }
      
      visitedNodes.add(id);

      if (currentDepth < depth) {
        const neighbors = this.getNeighbors(id);
        for (const neighbor of neighbors) {
          if (!visitedNodes.has(neighbor.id)) {
            queue.push({ id: neighbor.id, currentDepth: currentDepth + 1 });
            
            // Add edges
            const edges = this.getEdgesBetween(id, neighbor.id);
            resultEdges.push(...edges);
          }
        }
      }
    }

    const resultNodes = Array.from(visitedNodes)
      .map(id => this.nodes.get(id))
      .filter((n): n is GraphNode => n !== undefined);

    return { nodes: resultNodes, edges: resultEdges };
  }

  /**
   * Clear the graph
   */
  clear(): void {
    this.nodes.clear();
    this.edges.clear();
    this.adjacencyList.clear();
    this.reverseAdjacencyList.clear();
  }

  /**
   * Get graph statistics
   */
  getStats(): { nodeCount: number; edgeCount: number } {
    return {
      nodeCount: this.nodes.size,
      edgeCount: this.edges.size
    };
  }
}

/**
 * Graph RAG - Combines graph traversal with vector similarity
 */
export class GraphRAG {
  private graphStore: GraphStore;
  private embedFn?: (text: string) => Promise<number[]>;

  constructor(config: { embedFn?: (text: string) => Promise<number[]> } = {}) {
    this.graphStore = new GraphStore();
    this.embedFn = config.embedFn;
  }

  /**
   * Add a document as a node
   */
  async addDocument(doc: { id: string; content: string; type?: string; metadata?: Record<string, any> }): Promise<void> {
    const embedding = this.embedFn ? await this.embedFn(doc.content) : undefined;
    
    this.graphStore.addNode({
      id: doc.id,
      type: doc.type || 'document',
      content: doc.content,
      metadata: doc.metadata,
      embedding
    });
  }

  /**
   * Add a relationship between documents
   */
  addRelationship(sourceId: string, targetId: string, type: string, weight?: number): void {
    this.graphStore.addEdge({
      id: `${sourceId}-${type}-${targetId}`,
      source: sourceId,
      target: targetId,
      type,
      weight
    });
  }

  /**
   * Query the graph with a natural language query
   */
  async query(query: string, config: GraphRAGConfig = {}): Promise<GraphQueryResult> {
    const { maxDepth = 2, maxNodes = 10, minScore = 0, includeEdges = true } = config;

    // Get all nodes and score them
    const allNodes = this.graphStore.getAllNodes();
    
    let scoredNodes: Array<{ node: GraphNode; score: number }>;

    if (this.embedFn) {
      // Use embedding similarity
      const queryEmbedding = await this.embedFn(query);
      scoredNodes = allNodes
        .filter(n => n.embedding)
        .map(node => ({
          node,
          score: this.cosineSimilarity(queryEmbedding, node.embedding!)
        }));
    } else {
      // Use keyword matching
      const queryTerms = query.toLowerCase().split(/\s+/);
      scoredNodes = allNodes.map(node => {
        const content = node.content.toLowerCase();
        let score = 0;
        for (const term of queryTerms) {
          if (content.includes(term)) score += 1;
        }
        return { node, score: score / queryTerms.length };
      });
    }

    // Filter and sort by score
    scoredNodes = scoredNodes
      .filter(s => s.score >= minScore)
      .sort((a, b) => b.score - a.score);

    // Get top nodes and expand graph
    const topNodes = scoredNodes.slice(0, Math.min(3, maxNodes));
    const resultNodes: GraphNode[] = [];
    const resultEdges: GraphEdge[] = [];
    const seenNodeIds = new Set<string>();

    for (const { node } of topNodes) {
      const subgraph = this.graphStore.getSubgraph(node.id, maxDepth);
      
      for (const n of subgraph.nodes) {
        if (!seenNodeIds.has(n.id) && resultNodes.length < maxNodes) {
          seenNodeIds.add(n.id);
          resultNodes.push(n);
        }
      }

      if (includeEdges) {
        resultEdges.push(...subgraph.edges);
      }
    }

    // Find paths between top nodes
    const paths: GraphNode[][] = [];
    if (topNodes.length >= 2) {
      for (let i = 0; i < topNodes.length - 1; i++) {
        const foundPaths = this.graphStore.findPaths(
          topNodes[i].node.id,
          topNodes[i + 1].node.id,
          maxDepth
        );
        paths.push(...foundPaths.slice(0, 3));
      }
    }

    return {
      nodes: resultNodes,
      edges: resultEdges,
      paths,
      score: topNodes.length > 0 ? topNodes[0].score : 0
    };
  }

  /**
   * Get context string from query results
   */
  getContext(result: GraphQueryResult): string {
    const nodeContents = result.nodes.map(n => n.content);
    return nodeContents.join('\n\n---\n\n');
  }

  /**
   * Get the underlying graph store
   */
  getGraphStore(): GraphStore {
    return this.graphStore;
  }

  private cosineSimilarity(a: number[], b: number[]): number {
    const dot = a.reduce((sum, x, i) => sum + x * b[i], 0);
    const normA = Math.sqrt(a.reduce((sum, x) => sum + x * x, 0));
    const normB = Math.sqrt(b.reduce((sum, x) => sum + x * x, 0));
    return dot / (normA * normB);
  }
}

// Factory function
export function createGraphRAG(config?: { embedFn?: (text: string) => Promise<number[]> }): GraphRAG {
  return new GraphRAG(config);
}
