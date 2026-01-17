/**
 * Enhanced Flow Display - Visualization options for workflows
 * 
 * Provides multiple output formats and interactive modes.
 */

/**
 * Display format
 */
export type DisplayFormat = 'text' | 'markdown' | 'json' | 'tree' | 'mermaid';

/**
 * Flow step representation
 */
export interface FlowStep {
    id: string;
    name: string;
    status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
    duration?: number;
    input?: any;
    output?: any;
    error?: string;
    children?: FlowStep[];
}

/**
 * Display options
 */
export interface FlowDisplayOptions {
    format?: DisplayFormat;
    showInput?: boolean;
    showOutput?: boolean;
    showDuration?: boolean;
    maxDepth?: number;
    colorize?: boolean;
}

/**
 * FlowDisplay - Workflow visualization
 */
export class FlowDisplay {
    private options: Required<FlowDisplayOptions>;

    constructor(options?: FlowDisplayOptions) {
        this.options = {
            format: options?.format ?? 'text',
            showInput: options?.showInput ?? false,
            showOutput: options?.showOutput ?? true,
            showDuration: options?.showDuration ?? true,
            maxDepth: options?.maxDepth ?? 10,
            colorize: options?.colorize ?? true,
        };
    }

    /**
     * Render flow
     */
    render(steps: FlowStep[]): string {
        switch (this.options.format) {
            case 'text':
                return this.renderText(steps);
            case 'markdown':
                return this.renderMarkdown(steps);
            case 'json':
                return this.renderJson(steps);
            case 'tree':
                return this.renderTree(steps);
            case 'mermaid':
                return this.renderMermaid(steps);
            default:
                return this.renderText(steps);
        }
    }

    /**
     * Render as plain text
     */
    private renderText(steps: FlowStep[], depth: number = 0): string {
        if (depth > this.options.maxDepth) return '';

        const lines: string[] = [];
        const indent = '  '.repeat(depth);

        for (const step of steps) {
            const status = this.getStatusIcon(step.status);
            const duration = this.options.showDuration && step.duration
                ? ` (${step.duration}ms)`
                : '';

            lines.push(`${indent}${status} ${step.name}${duration}`);

            if (step.error) {
                lines.push(`${indent}  ❌ Error: ${step.error}`);
            }

            if (this.options.showOutput && step.output) {
                const output = typeof step.output === 'string'
                    ? step.output.slice(0, 100)
                    : JSON.stringify(step.output).slice(0, 100);
                lines.push(`${indent}  → ${output}...`);
            }

            if (step.children) {
                lines.push(this.renderText(step.children, depth + 1));
            }
        }

        return lines.join('\n');
    }

    /**
     * Render as markdown
     */
    private renderMarkdown(steps: FlowStep[], depth: number = 0): string {
        if (depth > this.options.maxDepth) return '';

        const lines: string[] = [];
        const heading = '#'.repeat(Math.min(depth + 2, 6));

        for (const step of steps) {
            const status = this.getStatusIcon(step.status);
            const duration = this.options.showDuration && step.duration
                ? ` *(${step.duration}ms)*`
                : '';

            lines.push(`${heading} ${status} ${step.name}${duration}`);

            if (step.error) {
                lines.push(`> ❌ **Error:** ${step.error}`);
            }

            if (this.options.showOutput && step.output) {
                lines.push('```');
                lines.push(typeof step.output === 'string'
                    ? step.output.slice(0, 500)
                    : JSON.stringify(step.output, null, 2).slice(0, 500));
                lines.push('```');
            }

            if (step.children) {
                lines.push(this.renderMarkdown(step.children, depth + 1));
            }

            lines.push('');
        }

        return lines.join('\n');
    }

    /**
     * Render as JSON
     */
    private renderJson(steps: FlowStep[]): string {
        return JSON.stringify(steps, null, 2);
    }

    /**
     * Render as tree
     */
    private renderTree(steps: FlowStep[], prefix: string = ''): string {
        const lines: string[] = [];

        for (let i = 0; i < steps.length; i++) {
            const step = steps[i];
            const isLast = i === steps.length - 1;
            const connector = isLast ? '└── ' : '├── ';
            const status = this.getStatusIcon(step.status);

            lines.push(`${prefix}${connector}${status} ${step.name}`);

            if (step.children) {
                const childPrefix = prefix + (isLast ? '    ' : '│   ');
                lines.push(this.renderTree(step.children, childPrefix));
            }
        }

        return lines.join('\n');
    }

    /**
     * Render as Mermaid diagram
     */
    private renderMermaid(steps: FlowStep[]): string {
        const lines: string[] = ['```mermaid', 'graph TD'];
        let nodeId = 0;

        const renderStep = (step: FlowStep, parentId?: string): number => {
            const currentId = `node${nodeId++}`;
            const label = step.name.replace(/"/g, "'");

            // Choose shape based on status
            let shape: string;
            switch (step.status) {
                case 'completed':
                    shape = `${currentId}[✅ ${label}]`;
                    break;
                case 'failed':
                    shape = `${currentId}[❌ ${label}]`;
                    break;
                case 'running':
                    shape = `${currentId}((🔄 ${label}))`;
                    break;
                default:
                    shape = `${currentId}[${label}]`;
            }

            lines.push(`    ${shape}`);

            if (parentId) {
                lines.push(`    ${parentId} --> ${currentId}`);
            }

            if (step.children) {
                for (const child of step.children) {
                    renderStep(child, currentId);
                }
            }

            return nodeId;
        };

        for (const step of steps) {
            renderStep(step);
        }

        lines.push('```');
        return lines.join('\n');
    }

    /**
     * Get status icon
     */
    private getStatusIcon(status: FlowStep['status']): string {
        switch (status) {
            case 'completed': return '✅';
            case 'failed': return '❌';
            case 'running': return '🔄';
            case 'skipped': return '⏭️';
            case 'pending':
            default: return '⏳';
        }
    }

    /**
     * Print to console
     */
    print(steps: FlowStep[]): void {
        console.log(this.render(steps));
    }
}

/**
 * Create flow display
 */
export function createFlowDisplay(options?: FlowDisplayOptions): FlowDisplay {
    return new FlowDisplay(options);
}

/**
 * Quick render
 */
export function renderFlow(steps: FlowStep[], format: DisplayFormat = 'text'): string {
    return new FlowDisplay({ format }).render(steps);
}

// Default export  
export default FlowDisplay;
