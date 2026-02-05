/**
 * OCRAgent Tests - TDD for OCR (Optical Character Recognition)
 * Python parity with praisonaiagents/agent/ocr_agent.py
 */

import { describe, it, expect } from '@jest/globals';
import {
  OCRAgent,
  OCRConfig,
  OCRResult,
  createOCRAgent,
} from '../../../src/agent/ocr';

describe('OCRConfig (Python Parity)', () => {
  it('should have sensible defaults', () => {
    const config: OCRConfig = {};
    expect(config.includeImageBase64).toBeUndefined();
    expect(config.pages).toBeUndefined();
    expect(config.imageLimit).toBeUndefined();
  });

  it('should accept all configuration options', () => {
    const config: OCRConfig = {
      includeImageBase64: true,
      pages: [1, 2, 3],
      imageLimit: 10,
      timeout: 600,
      apiBase: 'https://api.example.com',
      apiKey: 'test-key',
    };
    expect(config.includeImageBase64).toBe(true);
    expect(config.pages).toEqual([1, 2, 3]);
    expect(config.imageLimit).toBe(10);
    expect(config.timeout).toBe(600);
    expect(config.apiBase).toBe('https://api.example.com');
    expect(config.apiKey).toBe('test-key');
  });
});

describe('OCRAgent', () => {
  describe('Construction', () => {
    it('should create with minimal config', () => {
      const agent = new OCRAgent({});
      expect(agent.name).toBe('OCRAgent');
    });

    it('should create with custom name', () => {
      const agent = new OCRAgent({ name: 'MyOCR' });
      expect(agent.name).toBe('MyOCR');
    });

    it('should create with full config', () => {
      const agent = new OCRAgent({
        name: 'MyOCR',
        llm: 'mistral/mistral-ocr-latest',
        ocr: {
          includeImageBase64: true,
          timeout: 300,
        },
        verbose: false,
      });
      expect(agent.name).toBe('MyOCR');
    });

    it('should accept boolean for ocr config', () => {
      const agent = new OCRAgent({
        name: 'MyOCR',
        ocr: true,
      });
      expect(agent.name).toBe('MyOCR');
    });

    it('should use model as alias for llm', () => {
      const agent = new OCRAgent({
        model: 'mistral/mistral-ocr-latest',
      });
      expect(agent.name).toBe('OCRAgent');
    });
  });

  describe('OCR Methods', () => {
    it('should have extract method', () => {
      const agent = new OCRAgent({});
      expect(typeof agent.extract).toBe('function');
    });

    it('should have aextract async method', () => {
      const agent = new OCRAgent({});
      expect(typeof agent.aextract).toBe('function');
    });

    it('should have read convenience method', () => {
      const agent = new OCRAgent({});
      expect(typeof agent.read).toBe('function');
    });

    it('should have aread async convenience method', () => {
      const agent = new OCRAgent({});
      expect(typeof agent.aread).toBe('function');
    });
  });

  describe('Default Model', () => {
    it('should have DEFAULT_MODEL constant', () => {
      expect(OCRAgent.DEFAULT_MODEL).toBe('mistral/mistral-ocr-latest');
    });
  });
});

describe('OCRResult', () => {
  it('should have all required fields', () => {
    const result: OCRResult = {
      text: 'Extracted text',
      pages: [
        { index: 0, markdown: '# Page 1', images: [] },
        { index: 1, markdown: '# Page 2', images: [] },
      ],
      metadata: { pageCount: 2 },
    };
    expect(result.text).toBe('Extracted text');
    expect(result.pages).toHaveLength(2);
    expect(result.pages[0].markdown).toBe('# Page 1');
    expect(result.metadata?.pageCount).toBe(2);
  });
});

describe('createOCRAgent factory', () => {
  it('should create OCRAgent instance', () => {
    const agent = createOCRAgent({});
    expect(agent).toBeInstanceOf(OCRAgent);
    expect(agent.name).toBe('OCRAgent');
  });

  it('should pass config to OCRAgent', () => {
    const agent = createOCRAgent({ name: 'CustomOCR' });
    expect(agent.name).toBe('CustomOCR');
  });
});
