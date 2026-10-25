import { ACTION_ORDER, topAction, type Decision } from "./decisions";

export type DecisionPanel = {
  show(decision: Decision | null): void;
};

function requireElement<T extends Element>(root: ParentNode, selector: string): T {
  const found = root.querySelector<T>(selector);
  if (!found) throw new Error(`decision panel markup missing: ${selector}`);
  return found;
}

/** The four-way distribution, drawn as bars beside the pitch. */
export function createDecisionPanel(root: HTMLElement): DecisionPanel {
  const bars = requireElement<HTMLElement>(root, "#decision-bars");
  const idEl = requireElement<HTMLElement>(root, "#decision-id");
  const footEl = requireElement<HTMLElement>(root, "#decision-foot");

  const rows = new Map<
    string,
    { row: HTMLLIElement; fill: HTMLElement; value: HTMLElement }
  >();
  for (const action of ACTION_ORDER) {
    const row = document.createElement("li");
    row.className = "bar-row";
    const label = document.createElement("span");
    label.className = "bar-label";
    label.textContent = action;
    const track = document.createElement("span");
    track.className = "bar-track";
    const fill = document.createElement("span");
    fill.className = "bar-fill";
    track.appendChild(fill);
    const value = document.createElement("span");
    value.className = "bar-value";
    row.append(label, track, value);
    bars.appendChild(row);
    rows.set(action, { row, fill, value });
  }

  let currentId: string | null = null;

  return {
    show(decision: Decision | null): void {
      if (!decision) {
        root.hidden = true;
        currentId = null;
        return;
      }
      root.hidden = false;
      if (decision.event_id !== currentId) {
        currentId = decision.event_id;
        idEl.textContent = decision.event_id;
        const best = topAction(decision.probabilities);
        for (const [action, row] of rows) {
          row.row.classList.toggle("top", action === best);
        }
      }
      for (const action of ACTION_ORDER) {
        const row = rows.get(action);
        if (!row) continue;
        const probability = decision.probabilities[action] ?? 0;
        row.fill.style.width = `${Math.max(0, Math.min(1, probability)) * 100}%`;
        row.value.textContent = `${Math.round(probability * 100)}%`;
      }
      const completion = decision.completion as Record<string, unknown>;
      const score = completion.primary_pass;
      footEl.textContent =
        typeof score === "number"
          ? `completion ${score.toFixed(3)} · pitch control × xT`
          : "";
    },
  };
}
