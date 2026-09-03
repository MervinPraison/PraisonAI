/**
 * `when` condition evaluation for Task routing.
 *
 * Port of Python `praisonaiagents.conditions.evaluator.evaluate_condition`:
 * `{{var}}` placeholders are substituted from the routing context, then the
 * expression is read as a numeric comparison, a string equality, a
 * contains check, or a truthy check. Errors evaluate to false (fail-safe).
 *
 *   evaluateWhen('{{score}} > 80', { score: 90 })                 // true
 *   evaluateWhen('{{status}} == approved', { status: 'approved' }) // true
 *   evaluateWhen('error in {{previous_output}}', { previous_output: 'An error' }) // true
 *   evaluateWhen('{{flag}}', { flag: 'yes' })                     // true
 */

function nestedValue(path: string, scope: Record<string, unknown>): unknown {
  let value: unknown = scope;
  for (const part of path.split('.')) {
    if (value && typeof value === 'object') value = (value as Record<string, unknown>)[part];
    else return undefined;
  }
  return value;
}

function render(value: unknown): string {
  if (value === undefined || value === null) return '';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

const FALSY = new Set(['', 'false', '0', 'none', 'null', 'no', 'off', 'undefined']);

/** Evaluate a Task `when` expression against `context`. */
export function evaluateWhen(condition: string, context: Record<string, unknown>): boolean {
  let substituted = condition;
  const previous = context.previous_output;
  if (previous !== undefined && previous !== null) {
    substituted = substituted.split('{{previous_output}}').join(String(previous));
  }
  substituted = substituted.replace(/\{\{([^}]+)\}\}/g, (_match, name: string) => {
    const key = name.trim();
    if (key === 'previous_output') return '';
    return render(key.includes('.') ? nestedValue(key, context) : context[key]);
  });

  const templateHasComparison = /(>=|<=|==|!=|>|<)/.test(condition);
  const expr = substituted.trim();
  try {
    if (templateHasComparison) {
      // A missing left operand (the variable was absent) never satisfies a comparison.
      if (/^[<>=]/.test(expr)) return false;

      const numeric = expr.match(/^(-?\d+(?:\.\d+)?)\s*(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?)$/);
      if (numeric) {
        const left = parseFloat(numeric[1]);
        const right = parseFloat(numeric[3]);
        switch (numeric[2]) {
          case '>': return left > right;
          case '>=': return left >= right;
          case '<': return left < right;
          case '<=': return left <= right;
          case '==': return left === right;
          case '!=': return left !== right;
        }
      }
      const stringEq = expr.match(/^(.+?)\s*(==|!=)\s*(.+)$/);
      if (stringEq) {
        const left = stringEq[1].trim().replace(/^["']|["']$/g, '');
        const right = stringEq[3].trim().replace(/^["']|["']$/g, '');
        return stringEq[2] === '==' ? left === right : left !== right;
      }
      return false;
    }

    // "needle in haystack"
    const inMatch = expr.match(/^(.+?)\s+in\s+(.+)$/i);
    if (inMatch) return inMatch[2].toLowerCase().includes(inMatch[1].trim().toLowerCase());
    // "haystack contains needle"
    const containsMatch = expr.match(/^(.+?)\s+contains\s+(.+)$/i);
    if (containsMatch) return containsMatch[1].toLowerCase().includes(containsMatch[2].trim().toLowerCase());

    // Truthy check on the substituted value.
    return !FALSY.has(expr.toLowerCase());
  } catch {
    return false;
  }
}
