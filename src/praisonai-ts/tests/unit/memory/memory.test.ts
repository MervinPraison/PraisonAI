import { BaseMemoryStore, Memory } from '../../../src/memory';

describe('BaseMemoryStore', () => {
  let memoryStore: BaseMemoryStore;

  beforeEach(() => {
    memoryStore = new BaseMemoryStore();
  });

  describe('memory operations', () => {
    const testMemory: Memory = {
      id: 'test-1',
      content: 'Test memory content',
      timestamp: new Date(),
      metadata: { type: 'test' }
    };

    it('should add and retrieve memory', () => {
      memoryStore.add(testMemory);
      const retrieved = memoryStore.get(testMemory.id);
      expect(retrieved).toEqual(testMemory);
    });

    it('should update memory', () => {
      memoryStore.add(testMemory);
      const update = {
        content: 'Updated content',
        metadata: { type: 'updated' }
      };
      
      const updated = memoryStore.update(testMemory.id, update);
      expect(updated).toBe(true);
      
      const retrieved = memoryStore.get(testMemory.id);
      expect(retrieved?.content).toBe('Updated content');
      expect(retrieved?.metadata.type).toBe('updated');
    });

    it('should delete memory', () => {
      memoryStore.add(testMemory);
      const deleted = memoryStore.delete(testMemory.id);
      expect(deleted).toBe(true);
      expect(memoryStore.get(testMemory.id)).toBeUndefined();
    });

    it('should search memories', () => {
      const memories: Memory[] = [
        {
          id: 'test-1',
          content: 'First memory',
          timestamp: new Date(),
          metadata: { type: 'test' }
        },
        {
          id: 'test-2',
          content: 'Second memory',
          timestamp: new Date(),
          metadata: { type: 'test' }
        }
      ];

      memories.forEach(m => memoryStore.add(m));
      const results = memoryStore.search('First');
      expect(results).toHaveLength(1);
      expect(results[0].content).toBe('First memory');
    });

    it('should clear all memories', () => {
      memoryStore.add(testMemory);
      memoryStore.clear();
      expect(memoryStore.get(testMemory.id)).toBeUndefined();
    });

    it('should handle non-existent memory operations', () => {
      expect(memoryStore.get('non-existent')).toBeUndefined();
      expect(memoryStore.update('non-existent', { content: 'test' })).toBe(false);
      expect(memoryStore.delete('non-existent')).toBe(false);
    });
  });
});
