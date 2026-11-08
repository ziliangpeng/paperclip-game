# Requirements

This directory is the **sole versioned source of truth for the product and engineering requirements of paperclip-game**. Chat records, Issue comments, and Agent memories cannot replace the explicit requirements here.

## Status Conventions

- **CONFIRMED**: Confirmed by the user; implementation Agents must not change it without authorization.
- **PROPOSED**: The currently recommended design. If it does not conflict with the requirements, it may be implemented in the corresponding Issue; if implementation reveals costs or behavioral differences, this document must be updated and appropriate confirmation obtained first.
- **OPEN**: Matters that remain unspecified and affect product behavior or acceptance. Implementation work that depends on them must remain blocked until they are resolved.

Purely internal implementation details do not require item-by-item product discussion, but the choices and verification methods must be made explicit in the relevant Issue. `PROPOSED` must never be represented as `CONFIRMED`.

## Document Index

| Document | Scope |
|---|---|
| [Product](./product.md) | Product goals, gameplay and UI fidelity boundaries, and client roles |
| [Runtime](./runtime.md) | Real-time simulation, concurrency, instance boundaries, technology stack, and persistence |
| [Clients and API](./clients.md) | Default addressing, Commands, GameView, SSE, and browser boundaries |
| [Testing](./testing.md) | Layered testing, scenario acceptance, and evidence requirements |
| [Milestones](./milestones.md) | Milestone process, linking to the complete 15-stage candidate and its review/merge status |
| [Complete Game Execution Plan](./execution-plan.md) | Full M1-M15 playable map, detailed M1 tasks, coarse future outlines, DAG, scenarios, and exact source ownership |
| [Execution-plan data](./data/execution-plan.json) | Structured inventory binding, owners, task DAG, aliases, bindings, scenarios, and invariants |
| [Execution-plan validator](../scripts/validate_execution_plan.py) | Standard-library structural, reference, DAG, hygiene, and negative self-test CLI |
| [Planning CI workflow](../.github/workflows/validate-plan.yml) | Read-only Linux inventory/plan validation and negative guards; no game-build claim |
| [Gameplay feature inventory](./gameplay-inventory.md) | Reference snapshot, coverage conventions, complete-game structure, and classification boundaries |
| [Actions and state](./gameplay-actions.md) | Controls, resources, action semantics, information feedback, and excluded legacy controls |
| [Projects](./gameplay-projects.md) | All official projects in source-array order, with costs, triggers, effects, and dependencies |
| [Progression](./gameplay-progression.md) | Economy, computation, phase transitions, autonomous production, universal goals, and reset paths |
| [Combat and endgame](./gameplay-combat-endgame.md) | Probe state, live combat, optional Driftwar, narrative endings, prestige, and teardown |

## Changes and Conflicts

1. See `AGENTS.md` in the repository root for the project-level Agent development process; this directory does not duplicate the full development rules.
2. Issues may only reference requirements; an Issue body must not create another set of conflicting game rules.
3. If implementation reveals an internal contradiction in the requirements or product ambiguity, stop the related work, mark it `needs-decision`, and update the requirements after resolution before continuing.
4. The official HTML is the primary reference for the original game design; the server real-time model and state management approach explicitly recorded for this project take precedence over the original browser implementation.
5. Requirement changes are recorded through Issues and PRs. Implementation PRs must not include unapproved requirement changes incidentally.

## Document Status

The official gameplay feature inventory is complete. Issue #4 now has a complete-draft 15-Milestone execution plan and machine-readable task/coverage map linked above. The candidate remains **PROPOSED / PENDING REVIEW** until its required independent source and engineering reviews, mandatory Opus review, normal merge, and main verification finish. Its planning workflow has no Actions result before the first real push.

M1 task records are detailed candidates, M2 contains only coarse work packages, and M3-M15 remain mapped outlines. No native implementation Issues have been created and **implementation of game functionality has not yet been authorized**. The inventory/planning CLIs check structure and evidence links only; they do not execute a game, prove gameplay semantics, or replace independent review.
