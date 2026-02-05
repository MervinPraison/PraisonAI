/**
 * Tests for Context Models (Python parity)
 */

import {
  ContextSegment,
  OptimizerStrategy,
  createContextLedger,
  getLedgerTotal,
  createBudgetAllocation,
  getUsableBudget,
  getHistoryBudget,
  createMonitorConfig,
  createContextConfig,
  createRecipeContextConfig,
  createOptimizationResult,
  getReductionPercent,
  createContextSnapshot,
  createManagerConfig,
} from '../../../src/context';

describe('Context Models (Python Parity)', () => {
  describe('ContextSegment', () => {
    it('should have all segment types', () => {
      expect(ContextSegment.SYSTEM_PROMPT).toBe('system_prompt');
      expect(ContextSegment.RULES).toBe('rules');
      expect(ContextSegment.SKILLS).toBe('skills');
      expect(ContextSegment.MEMORY).toBe('memory');
      expect(ContextSegment.TOOLS_SCHEMA).toBe('tools_schema');
      expect(ContextSegment.HISTORY).toBe('history');
      expect(ContextSegment.TOOL_OUTPUTS).toBe('tool_outputs');
      expect(ContextSegment.BUFFER).toBe('buffer');
    });
  });

  describe('OptimizerStrategy', () => {
    it('should have all strategy types', () => {
      expect(OptimizerStrategy.TRUNCATE).toBe('truncate');
      expect(OptimizerStrategy.SLIDING_WINDOW).toBe('sliding_window');
      expect(OptimizerStrategy.SUMMARIZE).toBe('summarize');
      expect(OptimizerStrategy.PRUNE_TOOLS).toBe('prune_tools');
      expect(OptimizerStrategy.NON_DESTRUCTIVE).toBe('non_destructive');
      expect(OptimizerStrategy.SMART).toBe('smart');
    });
  });

  describe('ContextLedger', () => {
    it('should create with defaults', () => {
      const ledger = createContextLedger();
      expect(ledger.systemPrompt).toBe(0);
      expect(ledger.history).toBe(0);
      expect(ledger.turnCount).toBe(0);
    });

    it('should create with partial values', () => {
      const ledger = createContextLedger({ systemPrompt: 100, history: 500 });
      expect(ledger.systemPrompt).toBe(100);
      expect(ledger.history).toBe(500);
    });

    it('should calculate total correctly', () => {
      const ledger = createContextLedger({
        systemPrompt: 100,
        rules: 50,
        skills: 50,
        memory: 100,
        toolsSchema: 200,
        history: 500,
        toolOutputs: 300,
        buffer: 50,
      });
      expect(getLedgerTotal(ledger)).toBe(1350);
    });
  });

  describe('BudgetAllocation', () => {
    it('should create with defaults', () => {
      const budget = createBudgetAllocation();
      expect(budget.modelLimit).toBe(128000);
      expect(budget.outputReserve).toBe(8000);
    });

    it('should calculate usable budget', () => {
      const budget = createBudgetAllocation({ modelLimit: 100000, outputReserve: 10000 });
      expect(getUsableBudget(budget)).toBe(90000);
    });

    it('should calculate history budget dynamically', () => {
      const budget = createBudgetAllocation({
        modelLimit: 128000,
        outputReserve: 8000,
        systemPrompt: 2000,
        rules: 500,
        skills: 500,
        memory: 1000,
        toolsSchema: 2000,
        history: -1,
        toolOutputs: 20000,
        buffer: 1000,
      });
      // Usable = 128000 - 8000 = 120000
      // Fixed = 2000 + 500 + 500 + 1000 + 2000 + 20000 + 1000 = 27000
      // History = 120000 - 27000 = 93000
      expect(getHistoryBudget(budget)).toBe(93000);
    });
  });

  describe('MonitorConfig', () => {
    it('should create with defaults', () => {
      const config = createMonitorConfig();
      expect(config.enabled).toBe(false);
      expect(config.path).toBe('./context.txt');
      expect(config.format).toBe('human');
    });
  });

  describe('ContextConfig', () => {
    it('should create with defaults', () => {
      const config = createContextConfig();
      expect(config.autoCompact).toBe(true);
      expect(config.compactThreshold).toBe(0.8);
      expect(config.strategy).toBe('smart');
    });

    it('should create recipe config', () => {
      const config = createRecipeContextConfig();
      expect(config.compactThreshold).toBe(0.7);
      expect(config.toolOutputMax).toBe(2000);
      expect(config.keepRecentTurns).toBe(3);
    });
  });

  describe('OptimizationResult', () => {
    it('should create with defaults', () => {
      const result = createOptimizationResult();
      expect(result.originalTokens).toBe(0);
      expect(result.tokensSaved).toBe(0);
    });

    it('should calculate reduction percent', () => {
      const result = createOptimizationResult({
        originalTokens: 1000,
        tokensSaved: 200,
      });
      expect(getReductionPercent(result)).toBe(20);
    });

    it('should handle zero original tokens', () => {
      const result = createOptimizationResult({ originalTokens: 0 });
      expect(getReductionPercent(result)).toBe(0);
    });
  });

  describe('ContextSnapshot', () => {
    it('should create with defaults', () => {
      const snapshot = createContextSnapshot();
      expect(snapshot.timestamp).toBe('');
      expect(snapshot.warnings).toEqual([]);
    });
  });

  describe('ManagerConfig', () => {
    it('should create with defaults', () => {
      const config = createManagerConfig();
      expect(config.modelLimit).toBe(128000);
      expect(config.strategy).toBe('smart');
    });
  });
});
