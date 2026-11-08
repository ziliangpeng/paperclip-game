# Milestone Planning

## 1. Complete Map Before Feature Implementation — CONFIRMED

Before implementation of game functionality begins, the following must first be developed:

1. A complete gameplay feature inventory based on the official HTML and game content;
2. A Milestone map from the initial game to the complete ending;
3. The playable increment, dependencies, and exit conditions for each Milestone;
4. Detailed Issues and dependency relationships for the current Milestone;
5. A testing and acceptance strategy for each Issue.

The complete 15-Milestone candidate is in the [Complete Game Execution Plan](./execution-plan.md), with its structured owner map in [execution-plan.json](./data/execution-plan.json). It defines M1 as the real manual-production, sales/Funds, Wire/Price/Marketing, permanent $5 AutoClipper-reveal, and continuously producing first-automation vertical slice. This is a complete draft pending the required independent reviews, normal merge, and main-branch verification; it is not authorization to implement M1.

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

## 5. Document Status — PROPOSED / PENDING REVIEW

- [x] The complete official gameplay feature inventory is established in [the gameplay feature inventory](./gameplay-inventory.md).
- [x] A complete 15-Milestone vertical map, exact 274-feature owner table, source-binding traces, stable task DAG, and acceptance catalog are drafted in the [Complete Game Execution Plan](./execution-plan.md) and [structured execution plan](./data/execution-plan.json).
- [ ] Two fresh independent reviews, mandatory Opus major-plan review, first-push planning CI, normal merge, and post-merge main verification are still required. The candidate has no execution effect until those gates complete.
- [ ] Native GitHub Milestones and detailed M1 Issues have not been created. Only after the plan is effective will M1 use detailed one-Issue/one-PR tasks; M2 may retain its three coarse packages; M3-M15 remain mapped outlines rather than stale detailed Issues.
- [ ] No game functionality or M1 implementation has begun or been marked Done. Structural plan validation, when run, is not gameplay or semantic approval.

The [execution-plan validator](../scripts/validate_execution_plan.py) and [planning CI workflow](../.github/workflows/validate-plan.yml) define the required structural and negative-guard checks. Their candidate presence does not claim an Actions result before the first real push.
