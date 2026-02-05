/**
 * Tests for LineRange and FileMatch (Python parity)
 */

import {
  LineRange,
  createLineRange,
  getLineCount,
  rangesOverlap,
  mergeRanges,
  FileMatch,
  createFileMatch,
  addLineRangeToFileMatch,
  getTotalLines,
} from '../../../src/cli/features/fast-context';

describe('LineRange (Python Parity)', () => {
  describe('createLineRange', () => {
    it('should create with required fields', () => {
      const range = createLineRange({ start: 10, end: 20 });
      expect(range.start).toBe(10);
      expect(range.end).toBe(20);
      expect(range.relevanceScore).toBe(1.0);
      expect(range.content).toBeUndefined();
    });

    it('should enforce minimum start of 1', () => {
      const range = createLineRange({ start: -5, end: 10 });
      expect(range.start).toBe(1);
    });

    it('should enforce end >= start', () => {
      const range = createLineRange({ start: 20, end: 10 });
      expect(range.end).toBe(20);
    });

    it('should accept optional content', () => {
      const range = createLineRange({ start: 1, end: 5, content: 'test content' });
      expect(range.content).toBe('test content');
    });

    it('should accept custom relevance score', () => {
      const range = createLineRange({ start: 1, end: 5, relevanceScore: 0.8 });
      expect(range.relevanceScore).toBe(0.8);
    });
  });

  describe('getLineCount', () => {
    it('should return correct line count', () => {
      const range = createLineRange({ start: 10, end: 20 });
      expect(getLineCount(range)).toBe(11);
    });

    it('should return 1 for single line', () => {
      const range = createLineRange({ start: 5, end: 5 });
      expect(getLineCount(range)).toBe(1);
    });
  });

  describe('rangesOverlap', () => {
    it('should detect overlapping ranges', () => {
      const a = createLineRange({ start: 10, end: 20 });
      const b = createLineRange({ start: 15, end: 25 });
      expect(rangesOverlap(a, b)).toBe(true);
    });

    it('should detect non-overlapping ranges', () => {
      const a = createLineRange({ start: 10, end: 20 });
      const b = createLineRange({ start: 25, end: 30 });
      expect(rangesOverlap(a, b)).toBe(false);
    });

    it('should detect adjacent ranges as overlapping', () => {
      const a = createLineRange({ start: 10, end: 20 });
      const b = createLineRange({ start: 20, end: 30 });
      expect(rangesOverlap(a, b)).toBe(true);
    });

    it('should detect contained ranges', () => {
      const a = createLineRange({ start: 10, end: 30 });
      const b = createLineRange({ start: 15, end: 25 });
      expect(rangesOverlap(a, b)).toBe(true);
    });
  });

  describe('mergeRanges', () => {
    it('should merge overlapping ranges', () => {
      const a = createLineRange({ start: 10, end: 20, relevanceScore: 0.8 });
      const b = createLineRange({ start: 15, end: 25, relevanceScore: 0.9 });
      const merged = mergeRanges(a, b);
      
      expect(merged.start).toBe(10);
      expect(merged.end).toBe(25);
      expect(merged.relevanceScore).toBe(0.9);
      expect(merged.content).toBeUndefined();
    });

    it('should throw for non-overlapping ranges', () => {
      const a = createLineRange({ start: 10, end: 20 });
      const b = createLineRange({ start: 25, end: 30 });
      expect(() => mergeRanges(a, b)).toThrow('Cannot merge non-overlapping ranges');
    });
  });
});

describe('FileMatch (Python Parity)', () => {
  describe('createFileMatch', () => {
    it('should create with required path', () => {
      const match = createFileMatch({ path: '/test/file.ts' });
      expect(match.path).toBe('/test/file.ts');
      expect(match.lineRanges).toEqual([]);
      expect(match.relevanceScore).toBe(1.0);
      expect(match.matchCount).toBe(0);
    });

    it('should accept optional fields', () => {
      const range = createLineRange({ start: 1, end: 10 });
      const match = createFileMatch({
        path: '/test/file.ts',
        lineRanges: [range],
        relevanceScore: 0.9,
        matchCount: 5,
      });
      
      expect(match.lineRanges.length).toBe(1);
      expect(match.relevanceScore).toBe(0.9);
      expect(match.matchCount).toBe(5);
    });
  });

  describe('addLineRangeToFileMatch', () => {
    it('should add non-overlapping range', () => {
      const match = createFileMatch({ path: '/test/file.ts' });
      const range = createLineRange({ start: 10, end: 20 });
      
      addLineRangeToFileMatch(match, range);
      
      expect(match.lineRanges.length).toBe(1);
      expect(match.lineRanges[0].start).toBe(10);
      expect(match.lineRanges[0].end).toBe(20);
    });

    it('should merge overlapping ranges', () => {
      const match = createFileMatch({ path: '/test/file.ts' });
      const range1 = createLineRange({ start: 10, end: 20 });
      const range2 = createLineRange({ start: 15, end: 25 });
      
      addLineRangeToFileMatch(match, range1);
      addLineRangeToFileMatch(match, range2);
      
      expect(match.lineRanges.length).toBe(1);
      expect(match.lineRanges[0].start).toBe(10);
      expect(match.lineRanges[0].end).toBe(25);
    });

    it('should keep non-overlapping ranges separate', () => {
      const match = createFileMatch({ path: '/test/file.ts' });
      const range1 = createLineRange({ start: 10, end: 20 });
      const range2 = createLineRange({ start: 30, end: 40 });
      
      addLineRangeToFileMatch(match, range1);
      addLineRangeToFileMatch(match, range2);
      
      expect(match.lineRanges.length).toBe(2);
    });

    it('should sort ranges by start', () => {
      const match = createFileMatch({ path: '/test/file.ts' });
      const range1 = createLineRange({ start: 30, end: 40 });
      const range2 = createLineRange({ start: 10, end: 20 });
      
      addLineRangeToFileMatch(match, range1);
      addLineRangeToFileMatch(match, range2);
      
      expect(match.lineRanges[0].start).toBe(10);
      expect(match.lineRanges[1].start).toBe(30);
    });
  });

  describe('getTotalLines', () => {
    it('should return 0 for empty match', () => {
      const match = createFileMatch({ path: '/test/file.ts' });
      expect(getTotalLines(match)).toBe(0);
    });

    it('should sum all line ranges', () => {
      const match = createFileMatch({ path: '/test/file.ts' });
      addLineRangeToFileMatch(match, createLineRange({ start: 1, end: 10 }));  // 10 lines
      addLineRangeToFileMatch(match, createLineRange({ start: 20, end: 25 })); // 6 lines
      
      expect(getTotalLines(match)).toBe(16);
    });
  });
});
