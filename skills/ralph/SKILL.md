---
name: ralph
description: Self-referential loop until task completion with architect verification
---

<Purpose>
Ralph is the persistence and verification wrapper around ultrawork. It guarantees task completion through iterative work cycles paired with mandatory architect verification, session persistence, and automatic retry logic.
</Purpose>

<Use_When>
- Task requires guaranteed completion with verification
- User says "don't stop", "must complete", "keep going until done"
- Task needs architect sign-off before completion
- Work requires persistence across interruptions
- Multi-step implementation that must be verified end-to-end
</Use_When>

<Do_Not_Use_When>
- Exploratory work or investigation -- use `explore` or `analyze` instead
- Quick single fixes with obvious scope -- delegate directly to executor
- User wants full autonomous pipeline -- use `autopilot` instead
- Simple questions that can be answered directly
</Do_Not_Use_When>

<Why_This_Exists>
Complex tasks often fail silently -- code compiles but doesn't work, tests pass but miss edge cases, implementations drift from requirements. Ralph enforces a verification loop where an architect agent independently validates completion against the original requirements, catching issues that the implementer missed.
</Why_This_Exists>

<Execution_Policy>
- Never reduce scope to claim completion -- if the task is too large, break it into phases
- Run actual tests/builds and read output -- never assume or use "should work" language
- Fresh verification on every iteration -- never reuse stale results
- Minimum STANDARD tier for architect verification
- Default to concise, evidence-dense progress and completion reporting
- Treat newer user task updates as local overrides for the active workflow branch
- If correctness depends on additional inspection, retrieval, execution, or verification, keep using tools until grounded
- Continue through clear, low-risk, reversible next steps automatically; ask only when materially branching or destructive
</Execution_Policy>

<Steps>

### Phase 1: Pre-Context Intake

1. Derive a task slug from the request
2. Reuse the latest relevant snapshot in `.omx/context/{slug}-*.md` when available
3. If none exists, create `.omx/context/{slug}-{timestamp}.md` (UTC `YYYYMMDDTHHMMSSZ`) with:
   - task statement, desired outcome, known facts/evidence, constraints, unknowns, likely codebase touchpoints
4. If ambiguity remains high, gather brownfield facts first via explore agent

### Phase 2: Parallel Delegation (via ultrawork)

1. Read `docs/shared/agent-tiers.md` for tier selection
2. Classify tasks by independence
3. Fire all independent tasks simultaneously at appropriate tiers:
   - Simple lookups/definitions: LOW tier
   - Standard implementation: STANDARD tier
   - Complex analysis/refactoring: THOROUGH tier
4. Use `run_in_background: true` for operations over ~30 seconds

### Phase 3: Fresh Verification

1. Run actual test suites, builds, typechecks
2. Read and analyze output -- never assume results
3. Architect verification at minimum STANDARD tier
4. If verification fails, loop back to Phase 2 with feedback

### Phase 4: Deslop Pass

1. Run `orbit:ai-slop-cleaner` on changed files post-verification
2. Clean up AI-generated artifacts (filler comments, unnecessary verbosity)

### Phase 5: Regression Re-verification

1. Confirm all tests still pass after cleanup
2. If regression found, fix and re-verify

### Iteration Loop

Repeat Phases 2-5 until:
- All acceptance criteria met AND architect approves, OR
- Max iterations reached (configurable, default 10)
- User cancels via `$cancel`

</Steps>

<Tool_Usage>
- Use ultrawork for parallel delegation (see ultrawork skill)
- Use `omx_state` MCP tools for ralph lifecycle state
- Use `ask_codex` with `agent_role: "architect"` for verification
- Use `run_in_background: true` for builds, installs, test suites
- Before first MCP tool use, call `ToolSearch("mcp")` to discover deferred MCP tools
</Tool_Usage>

## State Management

Use `omx_state` MCP tools for ralph lifecycle state.

- **On start**: `state_write({mode: "ralph", active: true, reinforcement_count: 1, current_phase: "intake"})`
- **On each iteration**: `state_write({mode: "ralph", reinforcement_count: <current>, current_phase: "<phase>"})`
- **On completion**: `state_write({mode: "ralph", active: false, current_phase: "complete"})`
- **On cancellation**: run `$cancel` (which should call `state_clear(mode="ralph")`)

## PRD Mode

When a PRD exists at `.omx/plans/prd-{slug}.md` (created via `$ralph-init`):
- Use PRD acceptance criteria as the definition of done
- Track progress in `.omx/state/{scope}/ralph-progress.json`
- Each iteration checks remaining criteria
- Complete when all criteria pass architect verification

<Escalation_And_Stop_Conditions>
- If a task fails repeatedly (3+ times on same issue), escalate to user
- If scope is unclear after intake, redirect to `$plan` for proper scoping
- If max iterations reached without completion, report status and remaining items
- Never silently reduce scope -- always report what was not completed
</Escalation_And_Stop_Conditions>

<Final_Checklist>
- [ ] All acceptance criteria met
- [ ] Architect verification passed
- [ ] All tests pass
- [ ] Build/typecheck passes
- [ ] Deslop pass completed
- [ ] Regression re-verification passed
- [ ] State cleaned up on completion
</Final_Checklist>
