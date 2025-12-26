/**
 * N8N Integration - Webhook triggers and workflow export for n8n
 */

export interface N8NConfig {
  baseUrl?: string;
  apiKey?: string;
  webhookPath?: string;
}

export interface N8NWebhookPayload {
  event: string;
  data: Record<string, any>;
  timestamp: string;
  source: string;
}

export interface N8NWorkflowNode {
  id: string;
  name: string;
  type: string;
  position: [number, number];
  parameters: Record<string, any>;
  credentials?: Record<string, any>;
}

export interface N8NWorkflowConnection {
  node: string;
  type: string;
  index: number;
}

export interface N8NWorkflow {
  name: string;
  nodes: N8NWorkflowNode[];
  connections: Record<string, { main: N8NWorkflowConnection[][] }>;
  settings?: Record<string, any>;
}

/**
 * N8N Integration class
 */
export class N8NIntegration {
  private config: N8NConfig;

  constructor(config: N8NConfig = {}) {
    this.config = {
      baseUrl: config.baseUrl || process.env.N8N_BASE_URL || 'http://localhost:5678',
      apiKey: config.apiKey || process.env.N8N_API_KEY,
      webhookPath: config.webhookPath || '/webhook',
      ...config
    };
  }

  /**
   * Trigger a webhook
   */
  async triggerWebhook(
    webhookId: string,
    payload: Record<string, any>
  ): Promise<{ success: boolean; response?: any; error?: string }> {
    const url = `${this.config.baseUrl}${this.config.webhookPath}/${webhookId}`;

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(this.config.apiKey ? { 'X-N8N-API-KEY': this.config.apiKey } : {})
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const error = await response.text();
        return { success: false, error: `HTTP ${response.status}: ${error}` };
      }

      const data = await response.json().catch(() => ({}));
      return { success: true, response: data };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  }

  /**
   * Create a webhook payload for agent events
   */
  createAgentEventPayload(
    event: string,
    agentId: string,
    data: Record<string, any>
  ): N8NWebhookPayload {
    return {
      event,
      data: {
        agentId,
        ...data
      },
      timestamp: new Date().toISOString(),
      source: 'praisonai'
    };
  }

  /**
   * Export PraisonAI workflow to n8n format
   */
  exportWorkflow(
    name: string,
    steps: Array<{
      name: string;
      type: 'agent' | 'tool' | 'condition';
      config?: Record<string, any>;
    }>
  ): N8NWorkflow {
    const nodes: N8NWorkflowNode[] = [];
    const connections: Record<string, { main: N8NWorkflowConnection[][] }> = {};

    // Add trigger node
    nodes.push({
      id: 'trigger',
      name: 'Webhook Trigger',
      type: 'n8n-nodes-base.webhook',
      position: [250, 300],
      parameters: {
        httpMethod: 'POST',
        path: name.toLowerCase().replace(/\s+/g, '-'),
        responseMode: 'onReceived'
      }
    });

    let prevNodeId = 'trigger';
    let yPosition = 300;

    for (let i = 0; i < steps.length; i++) {
      const step = steps[i];
      const nodeId = `node_${i}`;
      yPosition += 150;

      // Map step type to n8n node type
      const nodeType = this.mapStepTypeToN8N(step.type);
      
      nodes.push({
        id: nodeId,
        name: step.name,
        type: nodeType,
        position: [250, yPosition],
        parameters: this.mapStepParameters(step)
      });

      // Add connection from previous node
      if (!connections[prevNodeId]) {
        connections[prevNodeId] = { main: [[]] };
      }
      connections[prevNodeId].main[0].push({
        node: nodeId,
        type: 'main',
        index: 0
      });

      prevNodeId = nodeId;
    }

    // Add response node
    const responseNodeId = 'response';
    nodes.push({
      id: responseNodeId,
      name: 'Response',
      type: 'n8n-nodes-base.respondToWebhook',
      position: [250, yPosition + 150],
      parameters: {
        respondWith: 'json',
        responseBody: '={{ $json }}'
      }
    });

    connections[prevNodeId] = {
      main: [[{ node: responseNodeId, type: 'main', index: 0 }]]
    };

    return {
      name,
      nodes,
      connections,
      settings: {
        executionOrder: 'v1'
      }
    };
  }

  /**
   * Map PraisonAI step type to n8n node type
   */
  private mapStepTypeToN8N(type: string): string {
    const mapping: Record<string, string> = {
      agent: 'n8n-nodes-base.httpRequest',
      tool: 'n8n-nodes-base.function',
      condition: 'n8n-nodes-base.if'
    };
    return mapping[type] || 'n8n-nodes-base.noOp';
  }

  /**
   * Map step parameters to n8n format
   */
  private mapStepParameters(step: { type: string; config?: Record<string, any> }): Record<string, any> {
    switch (step.type) {
      case 'agent':
        return {
          method: 'POST',
          url: '={{ $env.PRAISONAI_API_URL }}/agent/execute',
          sendBody: true,
          bodyParameters: {
            parameters: [
              { name: 'input', value: '={{ $json.input }}' }
            ]
          },
          ...step.config
        };
      case 'tool':
        return {
          functionCode: `
// Tool execution
const input = $input.all();
// Add your tool logic here
return input;
          `.trim(),
          ...step.config
        };
      case 'condition':
        return {
          conditions: {
            boolean: [
              {
                value1: '={{ $json.success }}',
                value2: true
              }
            ]
          },
          ...step.config
        };
      default:
        return step.config || {};
    }
  }

  /**
   * Generate n8n workflow JSON string
   */
  exportWorkflowJSON(
    name: string,
    steps: Array<{ name: string; type: 'agent' | 'tool' | 'condition'; config?: Record<string, any> }>
  ): string {
    const workflow = this.exportWorkflow(name, steps);
    return JSON.stringify(workflow, null, 2);
  }

  /**
   * Import n8n workflow and convert to PraisonAI format
   */
  importWorkflow(n8nWorkflow: N8NWorkflow): Array<{
    name: string;
    type: string;
    config: Record<string, any>;
  }> {
    const steps: Array<{ name: string; type: string; config: Record<string, any> }> = [];

    // Skip trigger and response nodes
    const workflowNodes = n8nWorkflow.nodes.filter(
      n => !n.type.includes('webhook') && !n.type.includes('respondToWebhook')
    );

    for (const node of workflowNodes) {
      steps.push({
        name: node.name,
        type: this.mapN8NTypeToStep(node.type),
        config: node.parameters
      });
    }

    return steps;
  }

  /**
   * Map n8n node type to PraisonAI step type
   */
  private mapN8NTypeToStep(n8nType: string): string {
    if (n8nType.includes('httpRequest')) return 'agent';
    if (n8nType.includes('function') || n8nType.includes('code')) return 'tool';
    if (n8nType.includes('if') || n8nType.includes('switch')) return 'condition';
    return 'tool';
  }

  /**
   * Create a webhook listener (for local development)
   */
  async createWebhookListener(
    port: number,
    handler: (payload: N8NWebhookPayload) => Promise<any>
  ): Promise<{ close: () => void }> {
    const http = await import('http');

    const server = http.createServer(async (req, res) => {
      if (req.method !== 'POST') {
        res.writeHead(405);
        res.end('Method not allowed');
        return;
      }

      let body = '';
      req.on('data', chunk => { body += chunk; });
      req.on('end', async () => {
        try {
          const payload = JSON.parse(body) as N8NWebhookPayload;
          const result = await handler(payload);
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify(result));
        } catch (error: any) {
          res.writeHead(500);
          res.end(JSON.stringify({ error: error.message }));
        }
      });
    });

    server.listen(port);
    console.log(`N8N webhook listener started on port ${port}`);

    return {
      close: () => server.close()
    };
  }
}

/**
 * Create an n8n integration instance
 */
export function createN8NIntegration(config?: N8NConfig): N8NIntegration {
  return new N8NIntegration(config);
}

/**
 * Quick function to trigger an n8n webhook
 */
export async function triggerN8NWebhook(
  webhookId: string,
  payload: Record<string, any>,
  config?: N8NConfig
): Promise<{ success: boolean; response?: any; error?: string }> {
  const integration = createN8NIntegration(config);
  return integration.triggerWebhook(webhookId, payload);
}
