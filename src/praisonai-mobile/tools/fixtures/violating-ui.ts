// FIXTURE — deliberately violates the agent-framework seam.
// Only engines/src/praisonai-ts may import "praisonai". A ui/ file may not.
import { Agent } from "praisonai";

export const bad = () => new Agent({ instructions: "no" });
