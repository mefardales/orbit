---
name: ultraqa
description: QA cycling workflow - test, verify, fix, repeat until goal met
---

<Purpose>
UltraQA is an autonomous QA cycling workflow that iterates through test/build/lint/typecheck verification cycles until all goals are met or stopping conditions trigger.
</Purpose>

<Use_When>
- User wants automated QA cycling ("run QA", "fix all tests", "make everything pass")
- After implementation, need to verify and fix until clean
- Multiple QA goals need to pass simultaneously (tests, build, lint, typecheck)
</Use_When>

<Do_Not_Use_When>
- Single test run without fix iteration -- just run the test command directly
- Exploratory testing -- use manual testing instead
- Performance testing -- use specialized benchmarking tools
</Do_Not_Use_When>

<Execution_Policy>
- Run up to 5 QA cycles maximum
- Each cycle: execute verification commands, check for success, diagnose failures, apply fixes
- Stop when all goals pass or max cycles reached
- Use architect agent for failure diagnosis
- Default to concise, evidence-dense progress reporting
</Execution_Policy>

<Steps>

### Goal Parsing

Parse the user's QA goals into concrete verification commands:

| Goal Type | Verification Command |
|-----------|---------------------|
| test | Project test runner (npm test, pytest, etc.) |
| build | Project build command (npm run build, etc.) |
| lint | Project linter (eslint, ruff, etc.) |
| typecheck | Type checker (tsc --noEmit, mypy, etc.) |

### QA Cycle (repeat up to 5 times)

1. **Execute** all verification commands
2. **Check results** -- if all pass, stop with success
3. **Diagnose failures** via architect agent analysis
4. **Apply fixes** for identified issues
5. **Re-execute** verification commands
6. **Check again** -- if all pass, stop; otherwise continue cycle

### Stopping Conditions

- All goals pass verification
- Max 5 cycles reached
- User cancels via `$cancel`
- Same failure persists 3+ consecutive cycles (escalate to user)

</Steps>

<Tool_Usage>
- Use `run_in_background: true` for test/build commands over ~30 seconds
- Use `ask_codex` with `agent_role: "architect"` for failure diagnosis
- Use `omx_state` MCP tools for ultraqa lifecycle state
</Tool_Usage>

## State Management

- **On start**: `state_write({mode: "ultraqa", active: true, cycle: 1})`
- **On each cycle**: `state_write({mode: "ultraqa", cycle: <current>})`
- **On completion**: `state_write({mode: "ultraqa", active: false})`

<Final_Checklist>
- [ ] All QA goals pass
- [ ] No regressions introduced
- [ ] Build passes
- [ ] Tests pass
- [ ] State cleaned up on completion
</Final_Checklist>
