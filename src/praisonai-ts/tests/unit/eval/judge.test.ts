/**
 * Judge (LLM-as-Judge) Unit Tests
 * 
 * TDD: Tests written first to define expected behavior
 */

import { describe, it, expect, jest, beforeEach } from '@jest/globals';

import {
  Judge,
  JudgeConfig,
  JudgeCriteriaConfig,
  JudgeResult,
  AccuracyJudge,
  CriteriaJudge,
  RecipeJudge,
  addJudge,
  getJudge,
  listJudges,
  removeJudge,
  addOptimizationRule,
  getOptimizationRule,
  listOptimizationRules,
  removeOptimizationRule,
  parseJudgeResponse,
} from '../../../src/eval/judge';

describe('Judge (LLM-as-Judge)', () => {
  describe('JudgeConfig', () => {
    it('should have sensible defaults', () => {
      const config: JudgeConfig = {};
      expect(config.model).toBeUndefined(); // Will use default
      expect(config.temperature ?? 0.1).toBe(0.1);
      expect(config.maxTokens ?? 500).toBe(500);
      expect(config.threshold ?? 7.0).toBe(7.0);
    });

    it('should allow custom configuration', () => {
      const config: JudgeConfig = {
        model: 'gpt-4o',
        temperature: 0.0,
        maxTokens: 1000,
        threshold: 8.0,
        criteria: 'Response is helpful',
      };
      expect(config.model).toBe('gpt-4o');
      expect(config.threshold).toBe(8.0);
    });
  });

  describe('JudgeCriteriaConfig', () => {
    it('should support domain-agnostic evaluation', () => {
      const config: JudgeCriteriaConfig = {
        name: 'water_flow',
        description: 'Evaluate water flow optimization',
        promptTemplate: 'Is the water flow optimal? Output: {output}',
        scoringDimensions: ['flow_rate', 'pressure', 'efficiency'],
        threshold: 7.0,
      };
      expect(config.name).toBe('water_flow');
      expect(config.scoringDimensions).toHaveLength(3);
    });
  });

  describe('JudgeResult', () => {
    it('should have all required fields', () => {
      const result: JudgeResult = {
        score: 8.5,
        passed: true,
        reasoning: 'Output matches expected',
        output: 'test output',
        suggestions: ['Consider adding more detail'],
        timestamp: Date.now(),
      };
      expect(result.score).toBe(8.5);
      expect(result.passed).toBe(true);
      expect(result.suggestions).toHaveLength(1);
    });

    it('should support optional fields', () => {
      const result: JudgeResult = {
        score: 6.0,
        passed: false,
        reasoning: 'Missing key information',
        output: 'test',
        expected: 'expected output',
        criteria: 'Be helpful',
        suggestions: [],
        timestamp: Date.now(),
        metadata: { iteration: 1 },
      };
      expect(result.expected).toBe('expected output');
      expect(result.criteria).toBe('Be helpful');
    });
  });

  describe('parseJudgeResponse', () => {
    it('should parse SCORE/REASONING/SUGGESTIONS format', () => {
      const response = `SCORE: 8.5
REASONING: The output is accurate and complete
SUGGESTIONS:
- Add more examples
- Include error handling`;

      const result = parseJudgeResponse(response, 'test output', 'expected', null, 7.0);
      expect(result.score).toBe(8.5);
      expect(result.passed).toBe(true);
      expect(result.reasoning).toBe('The output is accurate and complete');
      expect(result.suggestions).toHaveLength(2);
    });

    it('should handle missing suggestions', () => {
      const response = `SCORE: 9
REASONING: Perfect match
SUGGESTIONS: None`;

      const result = parseJudgeResponse(response, 'test', null, null, 7.0);
      expect(result.score).toBe(9);
      expect(result.suggestions).toHaveLength(0);
    });

    it('should clamp scores to 1-10 range', () => {
      const response = `SCORE: 15
REASONING: Invalid score`;

      const result = parseJudgeResponse(response, 'test', null, null, 7.0);
      expect(result.score).toBe(10);
    });

    it('should handle malformed response', () => {
      const response = 'This is not a valid response format';

      const result = parseJudgeResponse(response, 'test', null, null, 7.0);
      expect(result.score).toBe(5.0); // Default
      expect(result.reasoning).toBe('Unable to parse response');
    });
  });

  describe('Judge class', () => {
    let judge: Judge;

    beforeEach(() => {
      judge = new Judge();
    });

    it('should instantiate with defaults', () => {
      expect(judge).toBeInstanceOf(Judge);
      expect(judge.threshold).toBe(7.0);
    });

    it('should accept custom config', () => {
      const customJudge = new Judge({
        model: 'gpt-4o',
        threshold: 8.0,
        criteria: 'Be concise',
      });
      expect(customJudge.threshold).toBe(8.0);
      expect(customJudge.criteria).toBe('Be concise');
    });

    it('should accept JudgeConfig object', () => {
      const config: JudgeConfig = {
        model: 'gpt-4o-mini',
        threshold: 6.0,
      };
      const configJudge = new Judge({ config });
      expect(configJudge.threshold).toBe(6.0);
    });

    it('should accept JudgeCriteriaConfig for domain-agnostic evaluation', () => {
      const criteriaConfig: JudgeCriteriaConfig = {
        name: 'test_domain',
        description: 'Test evaluation',
        promptTemplate: 'Evaluate: {output}',
        scoringDimensions: ['quality'],
        threshold: 8.0,
      };
      const domainJudge = new Judge({ criteriaConfig });
      expect(domainJudge.threshold).toBe(8.0);
    });
  });

  describe('AccuracyJudge', () => {
    it('should be a subclass of Judge', () => {
      const judge = new AccuracyJudge();
      expect(judge).toBeInstanceOf(Judge);
      expect(judge).toBeInstanceOf(AccuracyJudge);
    });
  });

  describe('CriteriaJudge', () => {
    it('should be a subclass of Judge', () => {
      const judge = new CriteriaJudge();
      expect(judge).toBeInstanceOf(Judge);
      expect(judge).toBeInstanceOf(CriteriaJudge);
    });
  });

  describe('RecipeJudge', () => {
    it('should be a subclass of Judge', () => {
      const judge = new RecipeJudge();
      expect(judge).toBeInstanceOf(Judge);
      expect(judge).toBeInstanceOf(RecipeJudge);
    });

    it('should support mode parameter', () => {
      const judge = new RecipeJudge({ mode: 'memory' });
      expect(judge.mode).toBe('memory');
    });
  });

  describe('Judge Registry', () => {
    beforeEach(() => {
      // Clear any custom judges
      const judges = listJudges();
      judges.forEach(name => {
        if (!['accuracy', 'criteria', 'recipe'].includes(name)) {
          removeJudge(name);
        }
      });
    });

    it('should have built-in judges registered', () => {
      const judges = listJudges();
      expect(judges).toContain('accuracy');
      expect(judges).toContain('criteria');
      expect(judges).toContain('recipe');
    });

    it('should register custom judge with addJudge', () => {
      class CustomJudge extends Judge {
        customMethod() { return 'custom'; }
      }
      
      addJudge('custom', CustomJudge);
      expect(listJudges()).toContain('custom');
    });

    it('should retrieve judge with getJudge', () => {
      const JudgeClass = getJudge('accuracy');
      expect(JudgeClass).toBe(AccuracyJudge);
    });

    it('should return undefined for unknown judge', () => {
      const JudgeClass = getJudge('nonexistent');
      expect(JudgeClass).toBeUndefined();
    });

    it('should remove judge with removeJudge', () => {
      class TempJudge extends Judge {}
      addJudge('temp', TempJudge);
      expect(listJudges()).toContain('temp');
      
      const removed = removeJudge('temp');
      expect(removed).toBe(true);
      expect(listJudges()).not.toContain('temp');
    });

    it('should return false when removing nonexistent judge', () => {
      const removed = removeJudge('nonexistent');
      expect(removed).toBe(false);
    });
  });

  describe('Optimization Rule Registry', () => {
    beforeEach(() => {
      // Clear custom rules
      const rules = listOptimizationRules();
      rules.forEach(name => removeOptimizationRule(name));
    });

    it('should register optimization rule', () => {
      class WaterLeakRule {
        name = 'water_leak';
        pattern = /(leak|overflow)/;
        severity = 'critical';
        getFix() { return 'Check for leaks'; }
      }
      
      addOptimizationRule('water_leak', WaterLeakRule);
      expect(listOptimizationRules()).toContain('water_leak');
    });

    it('should retrieve optimization rule', () => {
      class TestRule {
        name = 'test';
      }
      addOptimizationRule('test', TestRule);
      
      const RuleClass = getOptimizationRule('test');
      expect(RuleClass).toBe(TestRule);
    });

    it('should remove optimization rule', () => {
      class TempRule {}
      addOptimizationRule('temp', TempRule);
      
      const removed = removeOptimizationRule('temp');
      expect(removed).toBe(true);
      expect(listOptimizationRules()).not.toContain('temp');
    });
  });
});

describe('Judge Integration', () => {
  it('should handle empty output gracefully', async () => {
    const judge = new Judge();
    const result = await judge.run({
      output: '',
    });

    expect(result.score).toBe(0);
    expect(result.passed).toBe(false);
    expect(result.reasoning).toContain('No output provided');
  });

  it('should build accuracy prompt correctly', () => {
    const judge = new Judge();
    // Access protected method via any cast for testing
    const prompt = (judge as any).buildPrompt('actual output', 'expected output', null, 'test input');
    
    expect(prompt).toContain('expected output');
    expect(prompt).toContain('actual output');
    expect(prompt).toContain('test input');
  });

  it('should build criteria prompt correctly', () => {
    const judge = new Judge({ criteria: 'Be helpful' });
    const prompt = (judge as any).buildPrompt('test output', null, null, '');
    
    expect(prompt).toContain('Be helpful');
    expect(prompt).toContain('test output');
  });

  it('should use custom criteria config prompt template', () => {
    const judge = new Judge({
      criteriaConfig: {
        name: 'custom',
        description: 'Custom evaluation',
        promptTemplate: 'Custom template: {output} with input: {input}',
        scoringDimensions: ['quality'],
        threshold: 8.0,
      },
    });
    const prompt = (judge as any).buildPrompt('my output', null, null, 'my input');
    
    expect(prompt).toContain('Custom template: my output with input: my input');
  });
});
