// FIXTURE — a file in no declared layer.
// Must be reported as ungoverned rather than silently allowed: the day someone
// adds a new top-level directory, the rule must notice instead of passing.
export const orphan = true;
