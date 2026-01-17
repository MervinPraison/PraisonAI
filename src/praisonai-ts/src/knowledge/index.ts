export interface Knowledge {
  id: string;
  type: string;
  content: any;
  metadata: Record<string, any>;
}

export interface KnowledgeBase {
  addKnowledge(knowledge: Knowledge): void;
  getKnowledge(id: string): Knowledge | undefined;
  searchKnowledge(query: string): Knowledge[];
  updateKnowledge(id: string, knowledge: Partial<Knowledge>): boolean;
  deleteKnowledge(id: string): boolean;
}

export class BaseKnowledgeBase implements KnowledgeBase {
  private knowledge: Map<string, Knowledge>;

  constructor() {
    this.knowledge = new Map();
  }

  addKnowledge(knowledge: Knowledge): void {
    this.knowledge.set(knowledge.id, knowledge);
  }

  getKnowledge(id: string): Knowledge | undefined {
    return this.knowledge.get(id);
  }

  searchKnowledge(query: string): Knowledge[] {
    // Basic implementation - should be enhanced with proper search logic
    return Array.from(this.knowledge.values()).filter(k =>
      JSON.stringify(k).toLowerCase().includes(query.toLowerCase())
    );
  }

  updateKnowledge(id: string, update: Partial<Knowledge>): boolean {
    const existing = this.knowledge.get(id);
    if (!existing) return false;

    this.knowledge.set(id, { ...existing, ...update });
    return true;
  }

  deleteKnowledge(id: string): boolean {
    return this.knowledge.delete(id);
  }
}

// Export Reranker
export * from './reranker';

// Export Graph RAG
export * from './graph-rag';

// Export Chunking
export * from './chunking';

// Export ChonkieJS Adapter (optional dependency)
export {
  ChonkieAdapter,
  createChonkieAdapter,
  hasChonkie,
  type ChonkieConfig,
  type ChonkieChunk,
  type ChonkieStrategy
} from './chonkie-adapter';

// Export Query Engine
export {
  QueryEngine,
  createQueryEngine,
  createSimpleQueryEngine,
  type QueryResult,
  type QueryOptions,
  type QueryEngineConfig,
  type EmbedderFn,
  type VectorStoreInterface
} from './query-engine';

// Export Document Readers
export {
  TextReader,
  MarkdownReader,
  HTMLReader,
  CodeReader,
  PDFReader,
  createReader,
  getReaderForPath,
  readDocument,
  type ParsedDocument,
  type Reader
} from './readers';

// Export RAG Pipeline
export {
  RAGPipeline,
  createRAGPipeline,
  createSimpleRAGPipeline,
  MemoryVectorStore,
  type RAGDocument,
  type RAGChunk,
  type RAGResult,
  type RAGContext,
  type RAGPipelineConfig,
  type RAGEmbedder,
  type RAGVectorStore,
  type RAGChunker,
  type RAGReranker
} from './rag-pipeline';
