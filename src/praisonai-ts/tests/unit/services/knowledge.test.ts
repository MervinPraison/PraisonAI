import { BaseKnowledgeBase, Knowledge } from '../../../src/knowledge';

describe('Knowledge Base', () => {
  let knowledgeBase: BaseKnowledgeBase;

  beforeEach(() => {
    knowledgeBase = new BaseKnowledgeBase();
  });

  describe('knowledge management', () => {
    it('should store and retrieve knowledge', () => {
      const knowledge: Knowledge = {
        id: 'test-knowledge',
        type: 'document',
        content: 'Test content',
        metadata: {
          type: 'test'
        }
      };

      knowledgeBase.addKnowledge(knowledge);
      const retrieved = knowledgeBase.getKnowledge(knowledge.id);
      expect(retrieved).toEqual(knowledge);
    });

    it('should update knowledge', () => {
      const knowledge: Knowledge = {
        id: 'test-knowledge',
        type: 'document',
        content: 'Original content',
        metadata: {
          type: 'test'
        }
      };

      knowledgeBase.addKnowledge(knowledge);

      const updated = knowledgeBase.updateKnowledge(knowledge.id, { content: 'Updated content' });
      expect(updated).toBe(true);
      
      const retrieved = knowledgeBase.getKnowledge(knowledge.id);
      expect(retrieved?.content).toBe('Updated content');
    });

    it('should delete knowledge', () => {
      const knowledge: Knowledge = {
        id: 'test-knowledge',
        type: 'document',
        content: 'Test content',
        metadata: {
          type: 'test'
        }
      };

      knowledgeBase.addKnowledge(knowledge);
      const deleted = knowledgeBase.deleteKnowledge(knowledge.id);
      expect(deleted).toBe(true);
      
      const retrieved = knowledgeBase.getKnowledge(knowledge.id);
      expect(retrieved).toBeUndefined();
    });
  });

  describe('knowledge search', () => {
    it('should search knowledge by content', () => {
      const items: Knowledge[] = [
        {
          id: 'knowledge1',
          type: 'document',
          content: 'First piece of knowledge',
          metadata: { type: 'test' }
        },
        {
          id: 'knowledge2',
          type: 'document',
          content: 'Second piece of knowledge',
          metadata: { type: 'test' }
        }
      ];

      items.forEach(k => knowledgeBase.addKnowledge(k));
      const results = knowledgeBase.searchKnowledge('First');
      expect(results.length).toBe(1);
      expect(results[0].id).toBe('knowledge1');
    });
  });

  describe('error handling', () => {
    it('should handle non-existent knowledge', () => {
      const result = knowledgeBase.getKnowledge('non-existent');
      expect(result).toBeUndefined();
    });

    it('should handle update on non-existent', () => {
      const result = knowledgeBase.updateKnowledge('non-existent', { content: 'test' });
      expect(result).toBe(false);
    });

    it('should handle batch operations', () => {
      const items: Knowledge[] = [
        {
          id: 'batch1',
          type: 'document',
          content: 'Batch item 1',
          metadata: { type: 'test' }
        },
        {
          id: 'batch2',
          type: 'document',
          content: 'Batch item 2',
          metadata: { type: 'test' }
        }
      ];

      items.forEach(item => knowledgeBase.addKnowledge(item));
      const retrieved = items.map(item => knowledgeBase.getKnowledge(item.id));

      expect(retrieved.map(r => r?.id)).toEqual(['batch1', 'batch2']);
    });
  });
});
