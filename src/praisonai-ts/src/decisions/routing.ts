import type { QuestionSpec, SystemOneResult } from './system-one';
import { getChoice, systemOne } from './system-one';

function hasOwnRoute(routes: Record<string, RouteTarget>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(routes, key);
}

export interface AgentLike {
  start(prompt: string): Promise<unknown> | unknown;
}

export type RouteTarget = AgentLike | string | ((decision: SystemOneResult) => unknown);

export interface DecisionRoutePlan {
  routeQuestion?: string;
  decisionModel?: string;
  apiBase?: string;
  stateKey?: string;
  questions: Record<string, QuestionSpec>;
  routes: Record<string, RouteTarget>;
  fallbackRoute?: string;
  minConfidence?: number;
}

export function defaultTicketTriageQuestions(): Record<string, QuestionSpec> {
  return {
    team: {
      type: 'choice',
      instructions: 'Which team should handle this ticket?',
      criteria: {
        billing: 'Payments and refunds',
        technical: 'Bugs and integrations',
        other: 'None of the above',
      },
    },
    refund: { type: 'noul', instructions: 'Does the customer explicitly ask for a refund?' },
    urgency: {
      type: 'score',
      instructions: 'How urgent is this ticket?',
      criteria: ['Routine', 'Soon', 'Urgent'],
    },
  };
}

export async function triagedStart(
  prompt: string,
  plan: DecisionRoutePlan,
  createAgent?: (model: string) => AgentLike,
): Promise<{ decision: SystemOneResult; route: string; response: unknown }> {
  const stateKey = plan.stateKey ?? 'message';
  const routeQuestion = plan.routeQuestion ?? 'team';
  const decision = await systemOne({ [stateKey]: prompt }, plan.questions, {
    model: plan.decisionModel,
    apiBase: plan.apiBase,
  });
  let route = getChoice(decision, routeQuestion);
  const conf = decision.answers[routeQuestion]?.confidence;
  if (plan.minConfidence != null && (conf == null || conf < plan.minConfidence)) {
    route = plan.fallbackRoute ?? route;
  }
  if (!route || !hasOwnRoute(plan.routes, route)) {
    route = plan.fallbackRoute ?? route;
  }
  if (!route || !hasOwnRoute(plan.routes, route)) {
    throw new Error(`No route for ${routeQuestion}=${String(route)}`);
  }
  const target = plan.routes[route];
  let response: unknown;
  if (typeof target === 'string') {
    if (!createAgent) {
      throw new Error('createAgent required when route target is a model string');
    }
    response = await createAgent(target).start(prompt);
  } else if (typeof target === 'function') {
    response = await target(decision);
  } else {
    response = await target.start(prompt);
  }
  return { decision, route, response };
}
