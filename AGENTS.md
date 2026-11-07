# AGENTS.md

This file defines the Issue, implementation, review, and merge workflow for paperclip-game. `requirements/` is the sole versioned source of truth for product and engineering requirements. This file does not duplicate game rules or the full test matrix.

## Language policy

All artifacts committed to or publicly submitted through this repository MUST be in English. This includes README files, `requirements/`, `AGENTS.md`, templates, source code and comments, commit messages, Issues and their comments, PR bodies and comments, and public review records. Private user conversations remain separate and are not repository artifacts. This convention is mandatory for every future agent.

## 1. Work authorization and unit of delivery

1. All implementation work must start from a GitHub Issue that is **open and whose blockers are all closed**. Before starting, read the requirements linked from the Issue and their status. Chat comments, verbal requests, TODOs in code, and vague task lists do not authorize implementation.
2. An Agent claims only one Issue at a time, and each Issue corresponds to exactly one independently testable PR. Do not split one Issue into a sequence of implementation PRs or bundle multiple Issues into one PR.
3. The Worker creates a narrowly scoped `issue-<N>-<short-scope>` branch from the latest `main`, opens one PR, and uses exactly one `Refs #N` in the PR body. Do not use auto-closing keywords such as `Closes`, `Fixes`, or `Resolves`. The controller explicitly closes the Issue only after main-branch verification passes.
4. Direct pushes to `main` are forbidden; fixes and reverts must also go through a PR. An implementation Agent must not merge its own PR on the basis of self-approval.
5. No drive-by fixes. Record out-of-scope problems in a separate Issue; do not include them in the current PR.

## 2. Milestones, dependencies, and Issue content

- Use **GitHub Milestones** to represent delivery stages and portable dependency markers in the Issue body to represent Issue relationships:
  - `Blocked by: #123`
  - `Blocks: #456`
- For multiple dependencies, repeat the same kind of marker on separate lines. Write `None` when there are none. Both automation selecting work and the pre-merge check must verify that every Issue referenced by `Blocked by` is closed.
- Issues for the current Milestone must be detailed enough for each to be delivered by one independent PR. Only the next Milestone may retain coarse task outlines. Keep later stages in the Milestone map and refine them after earlier stages produce new information; do not create a large backlog of detailed Issues that will become stale.
- Every actionable Issue must contain **Objective, Specification references, Scope, Non-goals, Dependencies, Acceptance criteria, Required tests / evidence**, and, where applicable, **Risk flags**. Use `.github/ISSUE_TEMPLATE/task.md`.
- Issues reference requirement files, sections, and stable invariants. They must not create an alternative set of game rules or duplicate the full test matrix. See `requirements/README.md` for the meanings of `CONFIRMED`, `PROPOSED`, and `OPEN`.
- If requirements conflict, or ambiguity in product behavior would affect implementation, label the Issue `needs-decision` and stop the related work. The requirements resolver must update `requirements/` through the requirements confirmation process before the work is unblocked. Implementation Agents must not invent rules.
- Agents may choose purely mechanical implementation details when this neither expands Scope nor changes product behavior, but tests must demonstrate the chosen behavior.

## 3. Implementation, tests, and evidence

- Select the necessary tests according to `requirements/testing.md` and the Issue's risks. Tests must cover the Acceptance criteria and realistic failure modes. Do not target a magic coverage percentage or mechanically require every PR to run the full test matrix.
- Each PR must list the commands actually executed, their results, and evidence corresponding to the Acceptance criteria. Do not merely claim that something "should work" or paste results that were not actually produced.
- Validate UI semantics, state, and real playable paths according to `requirements/testing.md`. Visual fidelity is best effort; screenshots may support observation, but pixel-perfect screenshots are not a merge gate.
- Never delete or weaken tests, lint, CI, required checks, security controls, or merge controls to make an implementation pass. Changes to test/CI/merge infrastructure are high-risk and require independent review. Where they also fall into a two-reviewer category below, the two-reviewer requirement applies.

## 4. Independent Agent review

This workflow has no human per-PR code review gate. Quality is ensured by executable acceptance tests, CI, **fresh-context independent reviewer Agents**, and an independent merge controller.

- An ordinary change requires approval from at least **1 independent reviewer**.
- Changes to core simulation, economy/game rules, concurrency, persistence, CI, or merge workflow require at least **2 independent reviewers**. One must perform an adversarial correctness review, actively seeking execution paths that violate invariants. The adversarial reviewer may be one of these two people; a third reviewer is not required.
- A reviewer must be independent of the implementation Agent and use fresh context. The implementation Agent's own work cannot serve as a required independent approval, and the Agent cannot be the sole reviewer of its own PR.
- Reviewers give a clear conclusion, describe what they checked, and report findings for the current PR HEAD. After new commits, they must recheck affected conclusions and evidence.

## 5. Blocking and non-blocking findings

Every **blocking finding** must provide all of the following:

1. The violated Issue Acceptance criterion or the exact requirements file, section, and invariant;
2. The exact code location, such as file and line number or an equivalent locator;
3. A reproducible command or test, or a demonstrable execution path with its actual incorrect result.

Only demonstrated problems may block a merge. Blocker types include:

- An unmet Acceptance criterion;
- An unauthorized change to game behavior or requirements;
- Loss of server authority over state;
- A real race, lost update, or double execution;
- Invalid or incorrect recovery;
- Tests or evidence required by the Issue are missing;
- A regression concealed by weakening tests or quality gates;
- A demonstrated data, security, or main-branch risk.

The following are **non-blocking**: taste or naming preferences, equally valid alternatives, unmeasured optimizations, speculative abstractions or multi-instance preparation beyond current requirements, unrelated refactoring, elegance-only comments, and unverified theoretical concerns. Such comments must be explicitly labeled non-blocking and cannot prevent a merge. Record worthwhile follow-up work in a separate Issue instead of delaying the current delivery with endless polish.

## 6. Merge controller and completion criteria

The independent merge controller mechanically verifies the following before merging:

- [ ] The PR links exactly one Issue, which is still open;
- [ ] Every Issue referenced by `Blocked by` is closed;
- [ ] The changes do not exceed the Issue Scope and contain no unapproved requirements deviations;
- [ ] All required CI checks pass;
- [ ] Every Acceptance criterion has the required evidence;
- [ ] The required number and types of independent approvals for the risk level are present, with reviews tied to the current HEAD;
- [ ] No blocking findings remain unresolved;
- [ ] The latest changes have been rechecked, and test and review evidence is not tied to an old commit;
- [ ] Required checks pass on the merge result based on the latest `main` at that time.

The later merge-controller implementation must use a **merge queue or an equivalent serialization mechanism**. Before merging, it must update/rebase the PR onto the latest `main` and rerun required checks on that exact merge result, preventing parallel PRs from passing against old bases and then creating semantic races.

The orchestrating controller must capture and store reviewer output, bound to the PR and HEAD SHA. Self-declared approvals in PR comments, copied and pasted review text, and forged comments cannot substitute for review records validated by the controller.

After merging through the queue, the controller must run the specified `main` post-merge verification. Only after it passes does the controller explicitly close the corresponding Issue and mark it complete for dependency resolution. The Issue remains open during verification, and any premature automatic closure must be reopened. If `main` breaks, pause new feature merges, keep or reopen the associated Issue, and fix or revert through a PR linked to a regression Issue. Agents must prioritize regressions, main breakage, and other blockers over claiming new Issues.

## 7. Public-repository hygiene

Manage this repository as a **PUBLIC repository**: even while it remains Private for pre-publication cleanup, treat all committed files, git history, Issues, PRs/comments, CI logs, screenshots, fixtures, and CI artifacts as information that will become public.

- Never read or copy credentials, tokens, `.env` contents, SSH keys, cookies, personal information, absolute home paths/user names, private hostnames, or other private material into repository content or public logs. Use repo-relative paths and obviously fake example data. Test fixtures must not contain real personal data.
- Workers must not expose secrets or private information in test output, browser screenshots, error dumps, or debug logs.
- Before pushing or merging, inspect the **complete diff, relevant history, and generated files, logs, screenshots, fixtures, and CI artifacts that will become public**; do not inspect only the final file tree.
- If a secret or private datum is detected, stop publishing/merging immediately and escalate to the appropriate human process. Deleting it in a later commit does not erase it from public history. History rewrites, incident handling, and key rotation must follow the appropriate human security process.
- The repository owner has explicitly allowed their own Git author/committer name and email address to remain public in commit metadata; this metadata does not require cleanup or rewriting. This exception does not extend to anyone else's personal information and never permits credentials, private files, or private project content.

Workers, reviewers, and their automation receive only the minimum privileges required for their tasks. They must not receive unnecessary secrets, admin credentials, or permission to write directly to `main`.
