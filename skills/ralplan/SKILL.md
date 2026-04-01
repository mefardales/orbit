---
name: ralplan
description: Alias for $plan --consensus
---

# Ralplan (Consensus Planning Alias)

Ralplan is a shorthand alias for `$plan --consensus`. It triggers iterative planning with Planner, Architect, and Critic agents until consensus is reached, with **RALPLAN-DR structured deliberation** (short mode by default, deliberate mode for high-risk work).

## Usage

```
$ralplan "task description"
```

## Flags

- `--interactive`: Enables user prompts at key decision points (draft review in step 2 and final approval in step 6). Without this flag the workflow runs fully automated and outputs the final plan without asking for confirmation.
- `--deliberate`: Forces deliberate mode for high-risk work. Adds pre-mortem (3 scenarios) and expanded test planning (unit/integration/e2e/observability).

## Behavior

This skill invokes the Plan skill in consensus mode:

```
$plan --consensus <arguments>
$plan --consensus --interactive <arguments>
```

The consensus workflow:
1. **Planner** creates initial plan and a compact **RALPLAN-DR summary** before review:
   - Principles (3-5)
   - Decision Drivers (top 3)
   - Viable Options (>=2) with bounded pros/cons
   - If only one viable option remains, explicit invalidation rationale for alternatives
   - Deliberate mode only: pre-mortem (3 scenarios) + expanded test plan (unit/integration/e2e/observability)
2. **User feedback** *(--interactive only)*: Present draft plan plus Principles / Drivers / Options summary before review. Otherwise, automatically proceed.
3. **Architect** reviews for architectural soundness -- must provide strongest steelman antithesis, at least one real tradeoff tension, and synthesis. **Await completion before step 4.**
4. **Critic** evaluates against quality criteria -- run only after step 3 completes. Must enforce principle-option consistency, fair alternatives, risk mitigation clarity, testable acceptance criteria, and concrete verification steps.
5. **Re-review loop** (max 5 iterations): Any non-APPROVE Critic verdict runs full closed loop back through Planner -> Architect -> Critic until approval or max iterations.
6. On Critic approval *(--interactive only)*: Present plan with approval options. Final plan must include ADR section. Otherwise, output the final plan and stop.
7. *(--interactive only)* On approval: invoke `$ralph` for sequential execution or `$team` for parallel team execution -- never implement directly.

> **Important:** Steps 3 and 4 MUST run sequentially. Do NOT issue both agent calls in the same parallel batch.

Follow the Plan skill's full documentation for consensus mode details.

## Pre-context Intake

Before consensus planning or execution handoff, ensure a grounded context snapshot exists:

1. Derive a task slug from the request.
2. Reuse the latest relevant snapshot in `.omx/context/{slug}-*.md` when available.
3. If none exists, create `.omx/context/{slug}-{timestamp}.md` with task statement, desired outcome, known facts, constraints, unknowns, and likely codebase touchpoints.
4. If ambiguity remains high, gather brownfield facts first via explore agent.

## Pre-Execution Gate

Execution modes (ralph, autopilot, team, ultrawork) require well-specified prompts. The ralplan gate intercepts underspecified execution requests and redirects them through consensus planning.

**Passes the gate** (specific enough for direct execution):
- `ralph fix the null check in src/hooks/bridge.ts:326`
- `autopilot implement issue #42`
- `team add validation to function processKeywordDetector`

**Gated -- redirected to ralplan** (needs scoping first):
- `ralph fix this`
- `autopilot build the app`
- `team improve performance`

**Bypass the gate**:
- `force: ralph refactor the auth module`
- `! autopilot optimize everything`

The gate auto-passes when it detects any concrete signal: file path, issue/PR number, camelCase/PascalCase/snake_case symbol, test runner, numbered steps, acceptance criteria, error reference, code block, or escape prefix.
