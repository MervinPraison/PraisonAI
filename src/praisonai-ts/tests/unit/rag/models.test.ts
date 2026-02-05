/**
 * Tests for RAG Models (Python parity)
 */

import {
  RetrievalStrategy,
  createCitation,
  formatCitation,
  createContextPack,
  hasCitations,
  formatContextPackForPrompt,
  createRAGResult,
  formatAnswerWithCitations,
  createRAGConfig,
  DEFAULT_RAG_TEMPLATE,
  RetrievalPolicy,
  CitationsMode,
  createRetrievalConfig,
  createSimpleRetrievalConfig,
  createSmartRetrievalConfig,
  RAG,
  createRAG,
} from '../../../src/rag';

describe('RAG Models (Python Parity)', () => {
  describe('RetrievalStrategy', () => {
    it('should have all strategy types', () => {
      expect(RetrievalStrategy.BASIC).toBe('basic');
      expect(RetrievalStrategy.FUSION).toBe('fusion');
      expect(RetrievalStrategy.HYBRID).toBe('hybrid');
    });
  });

  describe('Citation', () => {
    it('should create with required fields', () => {
      const citation = createCitation({
        id: '[1]',
        source: 'doc.pdf',
        text: 'Sample text',
      });
      expect(citation.id).toBe('[1]');
      expect(citation.source).toBe('doc.pdf');
      expect(citation.score).toBe(0);
    });

    it('should format citation correctly', () => {
      const citation = createCitation({
        id: '[1]',
        source: 'doc.pdf',
        text: 'This is a sample text that is short',
      });
      const formatted = formatCitation(citation);
      expect(formatted).toContain('[1]');
      expect(formatted).toContain('doc.pdf');
    });

    it('should truncate long text in format', () => {
      const longText = 'A'.repeat(150);
      const citation = createCitation({
        id: '[1]',
        source: 'doc.pdf',
        text: longText,
      });
      const formatted = formatCitation(citation);
      expect(formatted).toContain('...');
    });
  });

  describe('ContextPack', () => {
    it('should create with defaults', () => {
      const pack = createContextPack();
      expect(pack.context).toBe('');
      expect(pack.citations).toEqual([]);
      expect(pack.query).toBe('');
    });

    it('should check for citations', () => {
      const emptyPack = createContextPack();
      expect(hasCitations(emptyPack)).toBe(false);

      const packWithCitations = createContextPack({
        citations: [createCitation({ id: '[1]', source: 'doc.pdf', text: 'text' })],
      });
      expect(hasCitations(packWithCitations)).toBe(true);
    });

    it('should format for prompt with sources', () => {
      const pack = createContextPack({
        context: 'Main context',
        citations: [createCitation({ id: '[1]', source: 'doc.pdf', text: 'text' })],
      });
      const formatted = formatContextPackForPrompt(pack, true);
      expect(formatted).toContain('Main context');
      expect(formatted).toContain('Sources:');
      expect(formatted).toContain('[1]');
    });

    it('should format without sources when disabled', () => {
      const pack = createContextPack({
        context: 'Main context',
        citations: [createCitation({ id: '[1]', source: 'doc.pdf', text: 'text' })],
      });
      const formatted = formatContextPackForPrompt(pack, false);
      expect(formatted).toBe('Main context');
      expect(formatted).not.toContain('Sources:');
    });
  });

  describe('RAGResult', () => {
    it('should create with defaults', () => {
      const result = createRAGResult();
      expect(result.answer).toBe('');
      expect(result.citations).toEqual([]);
    });

    it('should format answer with citations', () => {
      const result = createRAGResult({
        answer: 'The answer is 42.',
        citations: [createCitation({ id: '[1]', source: 'doc.pdf', text: 'text' })],
      });
      const formatted = formatAnswerWithCitations(result);
      expect(formatted).toContain('The answer is 42.');
      expect(formatted).toContain('Sources:');
    });
  });

  describe('RAGConfig', () => {
    it('should create with defaults', () => {
      const config = createRAGConfig();
      expect(config.topK).toBe(5);
      expect(config.minScore).toBe(0);
      expect(config.includeCitations).toBe(true);
      expect(config.retrievalStrategy).toBe('basic');
    });

    it('should have default template', () => {
      expect(DEFAULT_RAG_TEMPLATE).toContain('{context}');
      expect(DEFAULT_RAG_TEMPLATE).toContain('{question}');
    });
  });

  describe('RetrievalPolicy', () => {
    it('should have all policy types', () => {
      expect(RetrievalPolicy.ALWAYS).toBe('always');
      expect(RetrievalPolicy.ON_DEMAND).toBe('on_demand');
      expect(RetrievalPolicy.SMART).toBe('smart');
      expect(RetrievalPolicy.NEVER).toBe('never');
    });
  });

  describe('CitationsMode', () => {
    it('should have all mode types', () => {
      expect(CitationsMode.NONE).toBe('none');
      expect(CitationsMode.INLINE).toBe('inline');
      expect(CitationsMode.FOOTNOTES).toBe('footnotes');
      expect(CitationsMode.APPEND).toBe('append');
    });
  });

  describe('RetrievalConfig', () => {
    it('should create with defaults', () => {
      const config = createRetrievalConfig();
      expect(config.policy).toBe('smart');
      expect(config.topK).toBe(5);
      expect(config.citationsMode).toBe('inline');
    });

    it('should create simple config', () => {
      const config = createSimpleRetrievalConfig(10);
      expect(config.policy).toBe('always');
      expect(config.topK).toBe(10);
      expect(config.strategy).toBe('basic');
    });

    it('should create smart config', () => {
      const config = createSmartRetrievalConfig(15);
      expect(config.policy).toBe('smart');
      expect(config.topK).toBe(15);
      expect(config.rerank).toBe(true);
      expect(config.queryExpansion).toBe(true);
    });
  });

  describe('RAG class', () => {
    it('should create with factory function', () => {
      const rag = createRAG();
      expect(rag).toBeInstanceOf(RAG);
    });

    it('should get config', () => {
      const rag = createRAG({ config: { topK: 10 } });
      const config = rag.getConfig();
      expect(config.topK).toBe(10);
    });

    it('should query without knowledge base', async () => {
      const rag = createRAG();
      const result = await rag.query('test question');
      expect(result.answer).toBe('No knowledge base configured.');
    });

    it('should retrieve without knowledge base', async () => {
      const rag = createRAG();
      const pack = await rag.retrieve('test question');
      expect(pack.query).toBe('test question');
      expect(pack.context).toBe('');
    });
  });
});
