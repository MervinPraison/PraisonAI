/**
 * Tests for ApprovalCallback and Planning constants (Python parity)
 */

import {
  ApprovalCallback,
  createApprovalCallback,
  READ_ONLY_TOOLS,
  RESTRICTED_TOOLS,
  RESEARCH_TOOLS,
  Plan,
  PlanStep,
} from '../../../src/planning';

describe('Planning Constants (Python Parity)', () => {
  describe('READ_ONLY_TOOLS', () => {
    it('should contain read-only tools', () => {
      expect(READ_ONLY_TOOLS).toContain('read_file');
      expect(READ_ONLY_TOOLS).toContain('search_codebase');
      expect(READ_ONLY_TOOLS).toContain('web_search');
      expect(READ_ONLY_TOOLS).toContain('grep_search');
    });

    it('should have 13 tools', () => {
      expect(READ_ONLY_TOOLS.length).toBe(13);
    });

    it('should not contain write tools', () => {
      expect(READ_ONLY_TOOLS).not.toContain('write_file');
      expect(READ_ONLY_TOOLS).not.toContain('delete_file');
    });
  });

  describe('RESTRICTED_TOOLS', () => {
    it('should contain dangerous tools', () => {
      expect(RESTRICTED_TOOLS).toContain('write_file');
      expect(RESTRICTED_TOOLS).toContain('delete_file');
      expect(RESTRICTED_TOOLS).toContain('execute_command');
      expect(RESTRICTED_TOOLS).toContain('git_push');
    });

    it('should have 17 tools', () => {
      expect(RESTRICTED_TOOLS.length).toBe(17);
    });

    it('should not contain read tools', () => {
      expect(RESTRICTED_TOOLS).not.toContain('read_file');
      expect(RESTRICTED_TOOLS).not.toContain('search_codebase');
    });
  });

  describe('RESEARCH_TOOLS', () => {
    it('should contain research tools', () => {
      expect(RESEARCH_TOOLS).toContain('web_search');
      expect(RESEARCH_TOOLS).toContain('tavily_search');
      expect(RESEARCH_TOOLS).toContain('read_file');
    });

    it('should have 13 tools', () => {
      expect(RESEARCH_TOOLS.length).toBe(13);
    });
  });
});

describe('ApprovalCallback (Python Parity)', () => {
  describe('constructor', () => {
    it('should create with defaults', () => {
      const callback = new ApprovalCallback();
      expect(callback).toBeInstanceOf(ApprovalCallback);
    });

    it('should create with autoApprove', () => {
      const callback = new ApprovalCallback({ autoApprove: true });
      const plan = new Plan({ name: 'Test Plan' });
      expect(callback.call(plan)).toBe(true);
    });
  });

  describe('call', () => {
    it('should return false by default', () => {
      const callback = new ApprovalCallback();
      const plan = new Plan({ name: 'Test Plan' });
      expect(callback.call(plan)).toBe(false);
    });

    it('should auto-approve when configured', () => {
      const callback = new ApprovalCallback({ autoApprove: true });
      const plan = new Plan({ name: 'Test Plan' });
      expect(callback.call(plan)).toBe(true);
    });

    it('should use custom approve function', () => {
      const callback = new ApprovalCallback({
        approveFn: (plan) => plan.steps.length <= 3,
      });
      
      const smallPlan = new Plan({ name: 'Small Plan' });
      smallPlan.addStep(new PlanStep({ description: 'Step 1' }));
      expect(callback.call(smallPlan)).toBe(true);
      
      const largePlan = new Plan({ name: 'Large Plan' });
      for (let i = 0; i < 5; i++) {
        largePlan.addStep(new PlanStep({ description: `Step ${i}` }));
      }
      expect(callback.call(largePlan)).toBe(false);
    });

    it('should call onReject when rejected', () => {
      let rejected = false;
      const callback = new ApprovalCallback({
        approveFn: () => false,
        onReject: () => { rejected = true; },
      });
      
      const plan = new Plan({ name: 'Test Plan' });
      callback.call(plan);
      expect(rejected).toBe(true);
    });
  });

  describe('asyncCall', () => {
    it('should auto-approve when configured', async () => {
      const callback = new ApprovalCallback({ autoApprove: true });
      const plan = new Plan({ name: 'Test Plan' });
      expect(await callback.asyncCall(plan)).toBe(true);
    });

    it('should handle async approve function', async () => {
      const callback = new ApprovalCallback({
        approveFn: async (plan) => {
          await new Promise(resolve => setTimeout(resolve, 10));
          return plan.steps.length <= 3;
        },
      });
      
      const plan = new Plan({ name: 'Test Plan' });
      plan.addStep(new PlanStep({ description: 'Step 1' }));
      expect(await callback.asyncCall(plan)).toBe(true);
    });
  });

  describe('static helpers', () => {
    it('alwaysApprove should return true', () => {
      const plan = new Plan({ name: 'Test Plan' });
      expect(ApprovalCallback.alwaysApprove(plan)).toBe(true);
    });

    it('alwaysReject should return false', () => {
      const plan = new Plan({ name: 'Test Plan' });
      expect(ApprovalCallback.alwaysReject(plan)).toBe(false);
    });

    it('approveIfSmall should check step count', () => {
      const checker = ApprovalCallback.approveIfSmall(3);
      
      const smallPlan = new Plan({ name: 'Small' });
      smallPlan.addStep(new PlanStep({ description: 'Step 1' }));
      expect(checker(smallPlan)).toBe(true);
      
      const largePlan = new Plan({ name: 'Large' });
      for (let i = 0; i < 5; i++) {
        largePlan.addStep(new PlanStep({ description: `Step ${i}` }));
      }
      expect(checker(largePlan)).toBe(false);
    });

    it('approveIfNoDangerousTools should check tools', () => {
      const safePlan = new Plan({ name: 'Safe' });
      safePlan.addStep(new PlanStep({ 
        description: 'Read file',
        metadata: { tools: ['read_file'] }
      }));
      expect(ApprovalCallback.approveIfNoDangerousTools(safePlan)).toBe(true);
      
      const dangerousPlan = new Plan({ name: 'Dangerous' });
      dangerousPlan.addStep(new PlanStep({ 
        description: 'Delete file',
        metadata: { tools: ['delete_file'] }
      }));
      expect(ApprovalCallback.approveIfNoDangerousTools(dangerousPlan)).toBe(false);
    });
  });

  describe('createApprovalCallback factory', () => {
    it('should create ApprovalCallback', () => {
      const callback = createApprovalCallback({ autoApprove: true });
      expect(callback).toBeInstanceOf(ApprovalCallback);
    });
  });
});
