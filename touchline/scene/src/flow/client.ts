import { decideFromSample, mockExplanation, type DecideRequest, type ExplainRequest } from "./mock";
import type { AgentExplanation, DecideFromTracking } from "./types";

/**
 * Decision and explanation calls the page is allowed to make.
 * This build returns the in-repo stub. Foundry and the agent service stay behind
 * the same two methods when those clients exist. No key is read here.
 */
export interface DecisionFlowClient {
  decide(request: DecideRequest): Promise<DecideFromTracking>;
  explain(request: ExplainRequest): Promise<AgentExplanation>;
}

export function createMockClient(delayMs = 420): DecisionFlowClient {
  return {
    async decide(request) {
      await wait(delayMs);
      return decideFromSample(request);
    },
    explain(request) {
      return Promise.resolve(mockExplanation(request));
    },
  };
}

function wait(ms: number): Promise<void> {
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
