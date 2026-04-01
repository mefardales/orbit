---
name: trace
description: Show agent flow trace timeline and summary
---

# Agent Flow Trace

Display agent execution flow information through timeline visualization and aggregate statistics.

## MCP Tools

### `trace_timeline`

Chronological event visualization for agent execution flow.

**Parameters:**
- `filter` -- Focus on specific event types: hooks, skills, agents, keywords, tools, modes
- `last` -- Limit number of results returned

### `trace_summary`

Aggregate statistics for the current session:
- Hook fire counts
- Keywords detected
- Skills activated
- Mode transitions
- Tool performance metrics

## Output Format

Present timeline data first, followed by summary information.

### Key Analysis Areas

1. **Mode transitions** -- How execution modes changed during the session
2. **Bottlenecks** -- Slow tools or agents that impact performance
3. **Flow patterns** -- Chains connecting keywords -> skills -> agents

## Usage

```
$trace
$trace --filter skills
$trace --last 20
```
