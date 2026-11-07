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
| [Milestones](./milestones.md) | How the complete Milestone map is developed and the current planning status |

## Changes and Conflicts

1. See `AGENTS.md` in the repository root for the project-level Agent development process; this directory does not duplicate the full development rules.
2. Issues may only reference requirements; an Issue body must not create another set of conflicting game rules.
3. If implementation reveals an internal contradiction in the requirements or product ambiguity, stop the related work, mark it `needs-decision`, and update the requirements after resolution before continuing.
4. The official HTML is the primary reference for the original game design; the server real-time model and state management approach explicitly recorded for this project take precedence over the original browser implementation.
5. Requirement changes are recorded through Issues and PRs. Implementation PRs must not include unapproved requirement changes incidentally.

## Current Stage

Only documentation and development process initialization are complete at present. The complete gameplay feature inventory, Milestone map, and actionable Issues are not all complete, and **implementation of game functionality has not yet been authorized**.
