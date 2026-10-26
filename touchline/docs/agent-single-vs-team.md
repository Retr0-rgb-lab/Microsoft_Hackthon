# Single reviewer vs the four-role team

Recorded on `PL26-W01-BHA-MUN` (synthetic, NextPlay League 2026/27) against Azure AI
Foundry `gpt-4.1-mini`. Reproduce with:

```sh
cd touchline
python3 -m decision.agents --match PL26-W01-BHA-MUN --decision <decision_id> \
  --question "<question>"
```

The command prints the single reviewer's text and the team's answer side by side.

## What is actually being compared

- **Single reviewer** — `decision.engine.review` over the engine analysis. One voice,
  no second reader, no citations. It is deterministic and free.
- **Team** — `coordinator → attack → defense → audit`, sharing one evidence registry.
  The audit role reads the other two and states `accept` or `reject`; a rejection sends
  the coordinator back to rewrite once.

Both see the same frozen snapshot. Neither sees future tracking, the actual outcome, or
the selected action.

## The three cases

| Case | Decision | Question | Team verdict | Requests | Cited evidence |
| --- | --- | --- | --- | --- | --- |
| A — contested pass | `d000001` | Why not pass to the striker? | accept | 10 | 11 |
| B — shot over pass | `d000029` | Why shoot instead of passing? | accept | 10 | 42 |
| C — backward pass | `d000003` | Why pass backward instead of forward under pressure? | accept | 10 | 12 |

The contract fixture for case C (`tests/fixtures/contracts/case-c/`) asks the backward-pass question above. An earlier note on this row said “why carry”; that wording is retired.

All three runs completed with four roles and an `accept` verdict. The recorded
`evidence_ids` names resolve against the same candidate set the interface shows.

## The difference, one per case

**A. The single reviewer cannot answer the question that was asked.**

Single reviewer, verbatim:

> Among evaluated passes, H08 has the highest model value. A10 is the critical defender
> along that route. This compares modelled options, not what would certainly happen.
> Even the highest-ranked pass has negative estimated gain; **holding, carrying and
> shooting have not been evaluated**.

The question was about the pass to the striker. The reviewer answers by naming a
different pass and then states it cannot evaluate carrying or shooting.

The team answers the question that was put to it:

> Passing to the striker is risky mainly because the passing lane is heavily contested
> by a close defender, increasing interception chances despite the striker's good
> arrival at the ball. Other passes, such as to teammate H08, offer safer lanes with
> better balance between opportunity and risk.

It cites `pass:H09:lane`, `pass:H09:receiver`, `pass:H09:offside` and `pass:H09:rollout`
for the option in question, so each claim is traceable.

**B. The single reviewer's coverage stops before the action that was taken.**

For `d000029` the actual action was a shot. The single reviewer again reports only the
best pass and closes with the same sentence about shooting not being evaluated. The team
answers the shot-versus-pass trade-off directly, and the defense role has simulated the
passing alternative, so the comparison is not one-sided.

**C. The team names what it does not know, per claim.**

The team's caveats for `d000003` include the hand-defined utility model, feasibility
being heuristic rather than a probability, and body orientation and preferred foot being
unknown. The single reviewer states its limitations once, globally.

## What this does not prove

These are three recorded cases on one synthetic match, not a benchmark. The team is not
shown to be more accurate: no ground truth exists for a counterfactual action. What the
runs do show is narrower and checkable:

1. The team answers the question that was asked; the single reviewer answers a fixed
   template about passes.
2. Every number in the team's answer traces to a named evidence id; the single reviewer
   offers none.
3. A wrong or unsupported claim has a path to rejection inside the run — the audit role —
   and a rewrite, neither of which a single reviewer can supply for its own prose.

## One more thing the run exposes

The team occasionally answers before all three specialists have run. That is now handled
by pushing the coordinator back into the loop (`decision/agents.py`,
`answer_too_early`), not by failing the run. Before that fix, an early answer failed the
whole run and only the computed baseline came back.

The team also quoted a model internal once ("value gain around 0.059"). The prompt now
forbids quoting scores, and `decision/contract.py` detects it anyway: a response that
quotes one is marked `partial` with a stated reason rather than passing as a probability.
