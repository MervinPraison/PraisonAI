import { describe, expect, it } from '@jest/globals';
import { GraphStore } from '../../../src/knowledge/graph-rag';

function graph(): GraphStore {
  const store = new GraphStore();
  for (const id of ['a', 'b', 'c', 'd']) store.addNode({ id, type: 'document', content: id });
  return store;
}

describe('GraphStore edge replacement', () => {
  it.each([
    ['a', 'c'], ['c', 'b'], ['c', 'd'], ['a', 'a'],
  ])('removes obsolete adjacency when an edge moves to %s -> %s', (source, target) => {
    const store = graph();
    store.addEdge({ id: 'edge', source: 'a', target: 'b', type: 'link' });
    store.addEdge({ id: 'edge', source, target, type: 'link' });
    expect(store.getNeighbors('a', 'outgoing').map(n => n.id)).not.toContain('b');
    expect(store.getNeighbors('b', 'incoming').map(n => n.id)).not.toContain('a');
    expect(store.getEdgesBetween('a', 'b')).toEqual([]);
    expect(store.findPaths('a', 'b')).toEqual([]);
    expect(store.getNeighbors(source, 'outgoing').map(n => n.id)).toContain(target);
    expect(store.getNeighbors(target, 'incoming').map(n => n.id)).toContain(source);
    expect(store.getStats().edgeCount).toBe(1);
  });

  it('retains adjacency backed by a parallel edge', () => {
    const store = graph();
    store.addEdge({ id: 'one', source: 'a', target: 'b', type: 'one' });
    store.addEdge({ id: 'two', source: 'a', target: 'b', type: 'two' });
    store.addEdge({ id: 'one', source: 'c', target: 'd', type: 'one' });
    expect(store.getNeighbors('a', 'outgoing').map(n => n.id)).toEqual(['b']);
    expect(store.getNeighbors('b', 'incoming').map(n => n.id)).toEqual(['a']);
    expect(store.getEdgesBetween('a', 'b').map(e => e.id)).toEqual(['two']);
    store.addEdge({ id: 'two', source: 'c', target: 'd', type: 'two' });
    expect(store.getNeighbors('a', 'outgoing')).toEqual([]);
    expect(store.getNeighbors('b', 'incoming')).toEqual([]);
    expect(store.getStats().edgeCount).toBe(2);
  });

  it('preserves neighbors when only edge metadata changes', () => {
    const store = graph();
    store.addEdge({ id: 'edge', source: 'a', target: 'b', type: 'link', weight: 1 });
    store.addEdge({ id: 'edge', source: 'a', target: 'b', type: 'link', weight: 2 });
    expect(store.getNeighbors('a', 'outgoing').map(n => n.id)).toEqual(['b']);
    expect(store.getEdgesBetween('a', 'b')[0].weight).toBe(2);
  });
});
