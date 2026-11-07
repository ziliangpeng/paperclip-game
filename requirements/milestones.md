# Milestone Planning

## 1. Complete Map Before Feature Implementation — CONFIRMED

Before implementation of game functionality begins, the following must first be developed:

1. A complete gameplay feature inventory based on the official HTML and game content;
2. A Milestone map from the initial game to the complete ending;
3. The playable increment, dependencies, and exit conditions for each Milestone;
4. Detailed Issues and dependency relationships for the current Milestone;
5. A testing and acceptance strategy for each Issue.

**The specific M1 gameplay boundaries have not yet been confirmed.** Previous discussion of an "early manufacturing—sales—automation loop" was only a candidate division and must not be misrecorded as a frozen M1.

## 2. How to Divide Milestones — CONFIRMED

- Divide Milestones into playable vertical capability increments, not horizontal layers such as "all backend complete" or "all frontend complete".
- Every Milestone is a genuine subset of the final complete game.
- Do not fill unimplemented gameplay with invented temporary economic rules.
- Each Milestone defines its Entry criteria, Exit criteria, dependencies, official feature coverage, and end-to-end scenarios.
- Full Clone may be declared only after all Milestones are complete and have passed acceptance.

## 3. Issue Planning Granularity — CONFIRMED

- Break the current Milestone into Issues that are sufficiently fine-grained for each to be completed by one independent PR.
- The next Milestone may retain only coarser task outlines.
- Keep later Milestones in the complete map for now and refine them after the preceding stage has been validated, avoiding large numbers of stale tasks.
- A GitHub Milestone represents a capability stage; an Issue represents one independently deliverable task; `Blocked by` / `Blocks` in the Issue body represent dependencies.
- Automated execution selects only Issues that are open and whose blockers are complete.

## 4. Common Acceptance for Each Stage

Every Milestone requires at least:

- Relevant rule and sequence tests;
- Verification of the corresponding server API and real-time behavior;
- Concurrency and snapshot tests commensurate with the risks;
- A genuinely playable path through the corresponding Web UI;
- An end-to-end scenario from the specified starting state to the Exit criteria;
- An updated coverage mapping between requirements and the official feature inventory;
- Completion of all dependency Issues and successful main-branch verification.

## 5. Current Status — OPEN

- [ ] The complete official gameplay feature inventory has not yet been established;
- [ ] The complete Milestone map has not yet been established;
- [ ] The precise M1 scope and Exit criteria have not yet been confirmed;
- [ ] Feature implementation Issues have not yet been created;
- [ ] Implementation of game functionality has not yet begun.
