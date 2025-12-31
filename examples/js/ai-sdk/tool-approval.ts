/**
 * Tool Approval Example (AI SDK v6 Parity)
 * 
 * Demonstrates human-in-the-loop tool approval using needsApproval.
 * 
 * Run: npx ts-node tool-approval.ts
 * Required: OPENAI_API_KEY
 */

import { 
  Agent,
  withApproval,
  getApprovalManager,
  createDangerousPatternChecker,
} from '../../../src/praisonai-ts/src';

async function main() {
  console.log('=== Tool Approval Example ===\n');

  // Set up approval handler
  const manager = getApprovalManager();
  manager.onApprovalRequest(async (request) => {
    console.log(`\n🔐 APPROVAL REQUESTED`);
    console.log(`   Tool: ${request.toolName}`);
    console.log(`   Input: ${JSON.stringify(request.input)}`);
    console.log(`   Reason: ${request.reason || 'No reason provided'}`);
    
    // Auto-approve for demo (in production, prompt user)
    console.log(`   ✅ Auto-approved for demo\n`);
    return true;
  });

  // Create a tool that always requires approval
  const deleteFile = withApproval({
    name: 'deleteFile',
    description: 'Delete a file from the filesystem',
    needsApproval: true, // Always require approval
    execute: async (input: { path: string }) => {
      console.log(`   Executing: Would delete ${input.path}`);
      return { success: true, deleted: input.path };
    },
  });

  // Create a tool with conditional approval (dangerous patterns only)
  const runCommand = withApproval({
    name: 'runCommand',
    description: 'Run a shell command',
    needsApproval: createDangerousPatternChecker(),
    execute: async (input: { command: string }) => {
      console.log(`   Executing: ${input.command}`);
      return { output: 'command executed' };
    },
  });

  // Test the tools
  console.log('1. Testing deleteFile (always requires approval):');
  const result1 = await deleteFile({ path: '/tmp/test.txt' });
  console.log('   Result:', result1);

  console.log('\n2. Testing runCommand with safe command (no approval needed):');
  const result2 = await runCommand({ command: 'ls -la' });
  console.log('   Result:', result2);

  console.log('\n3. Testing runCommand with dangerous command (requires approval):');
  const result3 = await runCommand({ command: 'rm -rf /tmp/test' });
  console.log('   Result:', result3);

  console.log('\n✅ Tool approval demo completed!');
}

main().catch(console.error);
