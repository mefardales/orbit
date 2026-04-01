---
name: visual-verdict
description: Structured visual QA verdict for screenshot-to-reference comparisons
---

# Visual Verdict

Compare generated UI screenshots against reference images and return a strict JSON verdict driving edit iterations.

## When to Use

- Visual fidelity requirements exist (layout, spacing, typography, component styling)
- You have a generated screenshot and at least one reference image
- Deterministic pass/fail guidance is needed before continuing edits

## Input Parameters

- `reference_images[]` -- one or more image paths
- `generated_screenshot` -- current output image
- Optional: `category_hint` -- UI category/style (e.g., `hackernews`, `sns-feed`, `dashboard`)

## Output JSON Structure

```json
{
  "score": 0,
  "verdict": "revise",
  "category_match": false,
  "differences": ["..."],
  "suggestions": ["..."],
  "reasoning": "short explanation"
}
```

### Rules

- `score`: integer 0-100
- `verdict`: `pass`, `revise`, or `fail`
- `category_match`: true when style matches intended UI category
- `differences[]`: concrete visual mismatches
- `suggestions[]`: actionable edits tied to differences
- `reasoning`: 1-2 sentence summary

## Threshold and Loop

Target pass threshold is **90+**. Below 90, continue editing and rerun before further code edits.

Persist verdict in `.omx/state/{scope}/ralph-progress.json` with numeric (`score`, threshold) and qualitative signals (`reasoning`, `suggestions`, `next_actions`).

## Debug Strategy

Use pixel-level diff tools as secondary diagnosis aids to localize hotspots, converting findings into concrete `differences[]` and `suggestions[]` updates.

## Usage

```
$visual-verdict --reference ref.png --screenshot current.png
$visual-verdict --reference ref1.png ref2.png --screenshot output.png --category dashboard
```
