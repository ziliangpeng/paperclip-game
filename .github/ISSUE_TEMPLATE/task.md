---
name: Implementation task
about: A task delivered by one independently testable PR
title: "[Task] "
labels: ""
assignees: ""
---

<!-- Select a GitHub Milestone after creation. An Agent claims only one Issue at a time; see the root AGENTS.md for implementation rules. -->

## Objective

<!-- State the verifiable outcome to deliver in one or two sentences. -->

## Specification references

- `requirements/<file>.md` §`<section>` — <!-- Relevant status and invariants; reference them instead of restating an alternative set of rules. -->

## Scope

- <!-- The deliverable scope included in this Issue. -->

## Non-goals

- <!-- Explicitly excluded work that requires a separate Issue. -->

## Dependencies

Blocked by: None
Blocks: None

<!-- When dependencies exist, replace None with #123. For multiple dependencies, repeat the same marker on separate lines. -->

## Acceptance criteria

- [ ] <!-- An independently verifiable outcome traceable to requirements. -->

## Required tests / evidence

<!-- Select risk-appropriate validation according to requirements/testing.md; do not duplicate the full test matrix. -->
- Tests / commands:
- Expected results / artifacts:

## Risk flags

- [ ] Core simulation / economy / game rules
- [ ] Concurrency / persistence / recovery
- [ ] Test / CI / merge infrastructure
- [ ] Security / data / main-branch risk
- [ ] None of the above

<!-- Conflicting requirements or product ambiguity: label the Issue needs-decision, stop implementation, and resolve the requirements first. -->
