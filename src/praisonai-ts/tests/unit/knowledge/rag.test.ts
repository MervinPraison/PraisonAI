/**
 * Knowledge Base (RAG) Unit Tests
 */

import { describe, it, expect, beforeEach } from '@jest/globals';
import { KnowledgeBase, createKnowledgeBase } from '../../../src/knowledge/rag';

describe('KnowledgeBase', () => {
  let kb: KnowledgeBase;

  beforeEach(() => {
    kb = createKnowledgeBase();
  });

  describe('Document Operations', () => {
    it('should add document', async () => {
      const doc = await kb.add({ id: 'doc1', content: 'Hello world' });
      expect(doc.id).toBe('doc1');
      expect(doc.content).toBe('Hello world');
    });

    it('should get document by id', async () => {
      await kb.add({ id: 'doc1', content: 'Test content' });
      const doc = kb.get('doc1');
      expect(doc?.content).toBe('Test content');
    });

    it('should delete document', async () => {
      await kb.add({ id: 'doc1', content: 'Test' });
      expect(kb.delete('doc1')).toBe(true);
      expect(kb.get('doc1')).toBeUndefined();
    });

    it('should add batch of documents', async () => {
      const docs = await kb.addBatch([
        { id: 'doc1', content: 'First' },
        { id: 'doc2', content: 'Second' }
      ]);
      expect(docs.length).toBe(2);
      expect(kb.size).toBe(2);
    });

    it('should list all documents', async () => {
      await kb.add({ id: 'doc1', content: 'First' });
      await kb.add({ id: 'doc2', content: 'Second' });
      const docs = kb.list();
      expect(docs.length).toBe(2);
    });

    it('should clear all documents', async () => {
      await kb.add({ id: 'doc1', content: 'Test' });
      kb.clear();
      expect(kb.size).toBe(0);
    });
  });

  describe('Text Search', () => {
    beforeEach(async () => {
      await kb.add({ id: 'doc1', content: 'The quick brown fox jumps over the lazy dog' });
      await kb.add({ id: 'doc2', content: 'A fast red fox runs through the forest' });
      await kb.add({ id: 'doc3', content: 'The cat sleeps on the mat' });
    });

    it('should search by text', async () => {
      const results = await kb.search('fox');
      expect(results.length).toBeGreaterThan(0);
      expect(results[0].document.content).toContain('fox');
    });

    it('should limit search results', async () => {
      const results = await kb.search('the', 1);
      expect(results.length).toBe(1);
    });

    it('should return empty for no match', async () => {
      const results = await kb.search('elephant');
      expect(results.length).toBe(0);
    });
  });

  describe('Context Building', () => {
    it('should build context from results', async () => {
      await kb.add({ id: 'doc1', content: 'First document' });
      await kb.add({ id: 'doc2', content: 'Second document' });
      const results = await kb.search('document');
      const context = kb.buildContext(results);
      expect(context).toContain('[1]');
      expect(context).toContain('document');
    });

    it('should return empty string for no results', () => {
      const context = kb.buildContext([]);
      expect(context).toBe('');
    });
  });

  describe('Metadata', () => {
    it('should store document metadata', async () => {
      await kb.add({ 
        id: 'doc1', 
        content: 'Test', 
        metadata: { author: 'John', category: 'test' } 
      });
      const doc = kb.get('doc1');
      expect(doc?.metadata?.author).toBe('John');
    });
  });
});
