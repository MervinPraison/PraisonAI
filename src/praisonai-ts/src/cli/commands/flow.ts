/**
 * CLI command: flow
 * Workflow flow visualization
 */

import { FlowDisplay, createFlowDisplay, renderWorkflow } from '../features/flow-display';

export async function execute(args: string[], options: Record<string, unknown>): Promise<void> {
  const subcommand = args[0] || 'help';
  const isJson = Boolean(options.output === 'json' || options.json);

  switch (subcommand) {
    case 'show':
      await handleShow(args.slice(1), options, isJson);
      break;
    case 'dot':
      await handleDot(args.slice(1), options, isJson);
      break;
    case 'help':
    default:
      showHelp(isJson);
  }
}

async function handleShow(args: string[], options: Record<string, unknown>, isJson: boolean): Promise<void> {
  const stepsStr = args[0] || options.steps as string;
  
  let steps: Array<{ name: string; type?: string }> = [];
  
  if (stepsStr) {
    try {
      steps = JSON.parse(stepsStr);
    } catch {
      // Parse simple format: "step1,step2,step3"
      steps = stepsStr.split(',').map(s => {
        const [name, type] = s.split(':');
        return { name: name.trim(), type: type?.trim() };
      });
    }
  } else {
    // Default example
    steps = [
      { name: 'Input', type: 'start' },
      { name: 'Process', type: 'agent' },
      { name: 'Validate', type: 'condition' },
      { name: 'Output', type: 'end' }
    ];
  }

  const display = createFlowDisplay({
    showStatus: Boolean(options.status),
    compact: Boolean(options.compact)
  });
  
  display.fromTasks(steps);

  if (isJson) {
    const graph = display.getGraph();
    console.log(JSON.stringify({
      success: true,
      nodes: Array.from(graph.nodes.values()),
      edges: graph.edges
    }, null, 2));
  } else {
    if (options.boxes) {
      console.log(display.renderBoxes());
    } else {
      console.log(display.render());
    }
  }
}

async function handleDot(args: string[], options: Record<string, unknown>, isJson: boolean): Promise<void> {
  const stepsStr = args[0] || options.steps as string;
  
  let steps: Array<{ name: string; type?: string }> = [];
  
  if (stepsStr) {
    try {
      steps = JSON.parse(stepsStr);
    } catch {
      steps = stepsStr.split(',').map(s => {
        const [name, type] = s.split(':');
        return { name: name.trim(), type: type?.trim() };
      });
    }
  } else {
    steps = [
      { name: 'Start', type: 'start' },
      { name: 'Agent', type: 'agent' },
      { name: 'End', type: 'end' }
    ];
  }

  const display = createFlowDisplay();
  display.fromTasks(steps);
  const dot = display.toDot();

  if (isJson) {
    console.log(JSON.stringify({ success: true, dot }));
  } else {
    console.log(dot);
  }
}

function showHelp(isJson: boolean): void {
  const help = {
    command: 'flow',
    description: 'Workflow flow visualization',
    subcommands: {
      show: 'Display workflow as text tree or boxes',
      dot: 'Export workflow as DOT format (for Graphviz)'
    },
    flags: {
      '--steps': 'Steps as JSON or "name:type,name:type"',
      '--status': 'Show status indicators',
      '--compact': 'Compact display mode',
      '--boxes': 'Display as ASCII boxes',
      '--json': 'Output in JSON format'
    },
    examples: [
      'praisonai-ts flow show "Input,Process,Output"',
      'praisonai-ts flow show "Start:start,Agent:agent,End:end"',
      'praisonai-ts flow show --boxes',
      'praisonai-ts flow dot "Step1,Step2,Step3" > workflow.dot'
    ]
  };

  if (isJson) {
    console.log(JSON.stringify(help, null, 2));
  } else {
    console.log('Flow - Workflow visualization\n');
    console.log('Subcommands:');
    for (const [cmd, desc] of Object.entries(help.subcommands)) {
      console.log(`  ${cmd.padEnd(12)} ${desc}`);
    }
    console.log('\nFlags:');
    for (const [flag, desc] of Object.entries(help.flags)) {
      console.log(`  ${flag.padEnd(12)} ${desc}`);
    }
    console.log('\nExamples:');
    for (const ex of help.examples) {
      console.log(`  ${ex}`);
    }
  }
}
