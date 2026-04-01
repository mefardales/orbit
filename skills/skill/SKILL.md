---
name: skill
description: Manage local skills - list, add, remove, search, edit, setup wizard
argument-hint: "<command> [args]"
---

# Skill Management

Meta-skill for managing pyclaude skills through CLI-like commands.

## Commands

### `/skill list`

Display all local skills organized by scope (user and project). Shows name, description, triggers, quality score, and usage count in table format.

### `/skill add [name]`

Interactive wizard for creating new skills. Collects:
- Name (kebab-case)
- Description
- Triggers (comma-separated)
- Argument hints
- Scope (user or project)

Creates the skill directory and SKILL.md file with YAML frontmatter.

### `/skill remove <name>`

Safely delete a skill after confirmation. Shows what will be removed before proceeding.

### `/skill edit <name>`

Modify existing skill metadata (description, triggers, hints) or full content through an interactive interface.

### `/skill search <query>`

Find skills by matching against names, descriptions, triggers, and content. Results ranked by relevance.

### `/skill info <name>`

Display complete skill details including YAML frontmatter and full markdown content.

### `/skill sync`

Compare user-level and project-level skills, offering options to:
- Copy user skills to project
- Copy project skills to user
- View differences between scopes

### `/skill setup`

Three-step initialization wizard:
1. Directory creation (ensure skill directories exist)
2. Skill inventory scanning
3. Quick-actions menu

### `/skill scan`

Quick scan of both user and project skill directories. Lighter than full setup.

## Skill Structure

Skills use YAML frontmatter with metadata fields:

```yaml
---
name: my-skill
description: What this skill does
triggers:
  - keyword1
  - keyword2
argument-hint: "<required> [optional]"
---
```

Storage locations:
- User-level: `~/.codex/skills/<name>/SKILL.md`
- Project-level: `.codex/skills/<name>/SKILL.md`

## Skill Templates

### Error Solution
```yaml
---
name: fix-<error-type>
description: Fix for <specific error> in <context>
---
# Problem: <error message>
# Solution: <specific fix>
# Files: <affected files>
```

### Workflow
```yaml
---
name: <workflow-name>
description: Steps for <process>
---
# Steps
1. ...
2. ...
```

### Code Pattern
```yaml
---
name: <pattern-name>
description: Pattern for <use case>
---
# Pattern: <name>
# When: <trigger condition>
# Implementation: <code>
```

## Design Principles

Good skills are:
- **Non-Googleable**: Context-specific to your codebase
- **Actionable with precision**: Reference actual files and errors
- **Hard-won knowledge**: Capture solutions discovered through debugging
- **Not generic**: Avoid general programming concepts available in documentation

## Safety

- Confirmation prompts before destructive operations (remove)
- Validation of skill naming conventions (kebab-case)
- Scope awareness (user vs project level)
