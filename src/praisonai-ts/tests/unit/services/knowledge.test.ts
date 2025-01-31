import { KnowledgeBase } from '../../../src/knowledge/knowledge';

describe('Knowledge Base', () => {
  let knowledgeBase: KnowledgeBase;

  beforeEach(() => {
    knowledgeBase = new KnowledgeBase();
  });

  describe('knowledge management', () => {
    it('should store and retrieve knowledge', async () => {
      const knowledge = {
        id: 'test-knowledge',
        content: 'Test content',
        metadata: {
          type: 'test'
        }
      };

      await knowledgeBase.store(knowledge);
      const retrieved = await knowledgeBase.retrieve(knowledge.id);
      expect(retrieved).toEqual(knowledge);
    });

    it('should update knowledge', async () => {
      const knowledge = {
        id: 'test-knowledge',
        content: 'Original content',
        metadata: {
          type: 'test'
        }
      };

      await knowledgeBase.store(knowledge);

      const updatedContent = 'Updated content';
      await knowledgeBase.update(knowledge.id, updatedContent);
      
      const retrieved = await knowledgeBase.retrieve(knowledge.id);
      expect(retrieved.content).toBe(updatedContent);
    });

    it('should delete knowledge', async () => {
      const knowledge = {
        id: 'test-knowledge',
        content: 'Test content',
        metadata: {
          type: 'test'
        }
      };

      await knowledgeBase.store(knowledge);
      await knowledgeBase.delete(knowledge.id);
      
      const retrieved = await knowledgeBase.retrieve(knowledge.id);
      expect(retrieved).toBeNull();
    });
  });

  describe('knowledge search', () => {
    it('should search knowledge by content', async () => {
      const knowledge = [
        {
          id: 'knowledge1',
          content: 'First piece of knowledge',
          metadata: { type: 'test' }
        },
        {
          id: 'knowledge2',
          content: 'Second piece of knowledge',
          metadata: { type: 'test' }
        }
      ];

      await Promise.all(knowledge.map(k => knowledgeBase.store(k)));
      const results = await knowledgeBase.search('First');
      expect(results.length).toBe(1);
      expect(results[0].id).toBe('knowledge1');
    });
  });

  describe('error handling', () => {
    it('should handle non-existent knowledge', async () => {
      const result = await knowledgeBase.retrieve('non-existent');
      expect(result).toBeNull();
    });

    it('should handle update errors', async () => {
      await expect(
        knowledgeBase.update('non-existent', 'test')
      ).rejects.toThrow();
    });

    it('should handle batch operations', async () => {
      const items = [
        {
          id: 'batch1',
          content: 'Batch item 1',
          metadata: { type: 'test' }
        },
        {
          id: 'batch2',
          content: 'Batch item 2',
          metadata: { type: 'test' }
        }
      ];

      await knowledgeBase.storeBatch(items);
      const retrieved = await Promise.all(
        items.map(item => knowledgeBase.retrieve(item.id))
      );

      expect(retrieved.map(r => r?.id)).toEqual(['batch1', 'batch2']);
    });
  });
});
