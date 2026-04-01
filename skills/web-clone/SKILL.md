---
name: web-clone
description: URL-driven website cloning with visual + functional verification
---

# Web Clone

Clone a target website from its URL, replicating both visual appearance and core interactive functionality.

## When to Use

- User provides a live URL and requests site replication
- Both visual and functional matching are required
- Reference site is accessible and unprotected

## When NOT to Use

- Screenshot-only tasks (no functional replication needed)
- Design modifications (user wants changes, not a clone)
- Authenticated content behind login
- Multi-page deep crawling (v1 is single-page only)
- Third-party widget replication

## Prerequisites

Playwright MCP server is required. Discover available browser tools via `ToolSearch("browser")` or `ToolSearch("playwright")`.

## Five-Pass Process

### Pass 1: Extract

1. Navigate to target URL
2. Capture accessibility snapshot
3. Take full-page baseline screenshot
4. Extract DOM with computed styles
5. Catalog interactive elements (buttons, links, forms, animations)

Context budget: keep combined extraction under ~60KB.

### Pass 2: Build Plan

1. Analyze extraction results to identify page regions
2. Map components to implementation plan
3. Create interaction map
4. Extract design tokens (colors, fonts, spacing)
5. Define file structure

### Pass 3: Generate Clone

1. Scaffold project structure
2. Implement clone component-by-component
3. Apply extracted computed styles
4. Wire interactions (navigation, forms, hover states)
5. Ensure responsive behavior

### Pass 4: Verify

1. Serve clone locally
2. Run visual verification with `$visual-verdict` (target score >= 85)
3. Verify structural landmarks (header, nav, main, footer)
4. Spot-check 2-3 interactive elements

Composite verdict includes: visual score, functional test results, structural landmark presence, and prioritized fixes.

### Pass 5: Iterate

1. Fix highest-impact issues based on composite verdict feedback
2. Re-verify
3. Loop until passing thresholds or max 5 iterations reached

## Success Criteria

- Visual score >= 85 via `$visual-verdict`
- Zero functional failures on tested interactions
- All major HTML landmarks present (header, nav, main, footer)

## Constraints

- Single-page scope only (v1 limitation)
- No backend API or authentication replication
- External images use placeholders
- Legal compliance: only clone owned or permitted sites

## Token Efficiency

- Prefer accessibility snapshots over screenshots for structural analysis
- Apply context budgets (<=60KB combined extraction)
- Use targeted extraction rather than full DOM dumps
