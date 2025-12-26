/**
 * Autonomy Modes - Control automatic execution behavior
 */

export type AutonomyMode = 'suggest' | 'auto_edit' | 'full_auto';

export type ActionType = 
  | 'file_read'
  | 'file_write'
  | 'file_delete'
  | 'shell_command'
  | 'network_request'
  | 'git_operation'
  | 'install_package';

export interface ApprovalPolicy {
  action: ActionType;
  requiresApproval: boolean;
  autoApprovePatterns?: string[];
  autoDenyPatterns?: string[];
}

export interface AutonomyConfig {
  mode: AutonomyMode;
  policies?: ApprovalPolicy[];
  rememberDecisions?: boolean;
  maxAutoActions?: number;
}

export interface ActionRequest {
  type: ActionType;
  description: string;
  target?: string;
  details?: Record<string, any>;
}

export interface ActionDecision {
  approved: boolean;
  reason?: string;
  remembered?: boolean;
}

/**
 * Default policies for each mode
 */
export const MODE_POLICIES: Record<AutonomyMode, ApprovalPolicy[]> = {
  suggest: [
    { action: 'file_read', requiresApproval: false },
    { action: 'file_write', requiresApproval: true },
    { action: 'file_delete', requiresApproval: true },
    { action: 'shell_command', requiresApproval: true },
    { action: 'network_request', requiresApproval: true },
    { action: 'git_operation', requiresApproval: true },
    { action: 'install_package', requiresApproval: true }
  ],
  auto_edit: [
    { action: 'file_read', requiresApproval: false },
    { action: 'file_write', requiresApproval: false },
    { action: 'file_delete', requiresApproval: true },
    { action: 'shell_command', requiresApproval: true },
    { action: 'network_request', requiresApproval: false },
    { action: 'git_operation', requiresApproval: true },
    { action: 'install_package', requiresApproval: true }
  ],
  full_auto: [
    { action: 'file_read', requiresApproval: false },
    { action: 'file_write', requiresApproval: false },
    { action: 'file_delete', requiresApproval: false },
    { action: 'shell_command', requiresApproval: false },
    { action: 'network_request', requiresApproval: false },
    { action: 'git_operation', requiresApproval: false },
    { action: 'install_package', requiresApproval: true }
  ]
};

/**
 * Autonomy Manager class
 */
export class AutonomyManager {
  private config: AutonomyConfig;
  private rememberedDecisions: Map<string, boolean> = new Map();
  private actionCount: number = 0;
  private promptCallback?: (request: ActionRequest) => Promise<boolean>;

  constructor(config: Partial<AutonomyConfig> = {}) {
    this.config = {
      mode: 'suggest',
      rememberDecisions: true,
      maxAutoActions: 100,
      ...config
    };
  }

  /**
   * Set the prompt callback for user approval
   */
  setPromptCallback(callback: (request: ActionRequest) => Promise<boolean>): void {
    this.promptCallback = callback;
  }

  /**
   * Request approval for an action
   */
  async requestApproval(request: ActionRequest): Promise<ActionDecision> {
    // Check if we've exceeded max auto actions
    if (this.config.maxAutoActions && this.actionCount >= this.config.maxAutoActions) {
      return {
        approved: false,
        reason: 'Maximum auto actions exceeded'
      };
    }

    // Check remembered decisions
    const decisionKey = this.getDecisionKey(request);
    if (this.config.rememberDecisions && this.rememberedDecisions.has(decisionKey)) {
      const remembered = this.rememberedDecisions.get(decisionKey)!;
      if (remembered) this.actionCount++;
      return {
        approved: remembered,
        reason: 'Remembered decision',
        remembered: true
      };
    }

    // Get policy for this action type
    const policy = this.getPolicy(request.type);

    // Check auto-approve patterns
    if (policy.autoApprovePatterns && request.target) {
      for (const pattern of policy.autoApprovePatterns) {
        if (this.matchPattern(request.target, pattern)) {
          this.actionCount++;
          return { approved: true, reason: `Matched auto-approve pattern: ${pattern}` };
        }
      }
    }

    // Check auto-deny patterns
    if (policy.autoDenyPatterns && request.target) {
      for (const pattern of policy.autoDenyPatterns) {
        if (this.matchPattern(request.target, pattern)) {
          return { approved: false, reason: `Matched auto-deny pattern: ${pattern}` };
        }
      }
    }

    // If no approval required, auto-approve
    if (!policy.requiresApproval) {
      this.actionCount++;
      return { approved: true, reason: 'No approval required' };
    }

    // Prompt user for approval
    if (this.promptCallback) {
      const approved = await this.promptCallback(request);
      
      // Remember decision if enabled
      if (this.config.rememberDecisions) {
        this.rememberedDecisions.set(decisionKey, approved);
      }

      if (approved) this.actionCount++;
      return { approved, reason: 'User decision' };
    }

    // No prompt callback, deny by default
    return { approved: false, reason: 'No approval mechanism available' };
  }

  /**
   * Get policy for an action type
   */
  private getPolicy(actionType: ActionType): ApprovalPolicy {
    // Check custom policies first
    if (this.config.policies) {
      const custom = this.config.policies.find(p => p.action === actionType);
      if (custom) return custom;
    }

    // Fall back to mode defaults
    const modePolicy = MODE_POLICIES[this.config.mode].find(p => p.action === actionType);
    return modePolicy || { action: actionType, requiresApproval: true };
  }

  /**
   * Generate decision key for remembering
   */
  private getDecisionKey(request: ActionRequest): string {
    return `${request.type}:${request.target || 'default'}`;
  }

  /**
   * Match a target against a pattern
   */
  private matchPattern(target: string, pattern: string): boolean {
    // Simple glob-like matching
    const regex = new RegExp(
      '^' + pattern.replace(/\*/g, '.*').replace(/\?/g, '.') + '$'
    );
    return regex.test(target);
  }

  /**
   * Get current mode
   */
  getMode(): AutonomyMode {
    return this.config.mode;
  }

  /**
   * Set mode
   */
  setMode(mode: AutonomyMode): void {
    this.config.mode = mode;
  }

  /**
   * Add custom policy
   */
  addPolicy(policy: ApprovalPolicy): void {
    if (!this.config.policies) {
      this.config.policies = [];
    }
    // Remove existing policy for this action
    this.config.policies = this.config.policies.filter(p => p.action !== policy.action);
    this.config.policies.push(policy);
  }

  /**
   * Clear remembered decisions
   */
  clearRemembered(): void {
    this.rememberedDecisions.clear();
  }

  /**
   * Reset action count
   */
  resetActionCount(): void {
    this.actionCount = 0;
  }

  /**
   * Get action count
   */
  getActionCount(): number {
    return this.actionCount;
  }

  /**
   * Get summary of current settings
   */
  getSummary(): string {
    const lines = [
      `Autonomy Mode: ${this.config.mode}`,
      `Actions taken: ${this.actionCount}/${this.config.maxAutoActions || 'unlimited'}`,
      `Remembered decisions: ${this.rememberedDecisions.size}`,
      '',
      'Current policies:'
    ];

    const policies = MODE_POLICIES[this.config.mode];
    for (const policy of policies) {
      const status = policy.requiresApproval ? '⚠️ requires approval' : '✓ auto-approved';
      lines.push(`  ${policy.action}: ${status}`);
    }

    return lines.join('\n');
  }
}

/**
 * Create an autonomy manager
 */
export function createAutonomyManager(config?: Partial<AutonomyConfig>): AutonomyManager {
  return new AutonomyManager(config);
}

/**
 * Simple approval prompt for CLI
 */
export async function cliApprovalPrompt(request: ActionRequest): Promise<boolean> {
  const readline = await import('readline');
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });

  return new Promise((resolve) => {
    const message = `\n⚠️  Action requires approval:\n  Type: ${request.type}\n  ${request.description}\n  Target: ${request.target || 'N/A'}\n\nApprove? (y/n): `;
    
    rl.question(message, (answer) => {
      rl.close();
      resolve(answer.toLowerCase() === 'y' || answer.toLowerCase() === 'yes');
    });
  });
}
