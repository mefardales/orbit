<p align="center">
  <img src="logo.png" alt="Orbit" width="500" />
</p>


<p align="center">
  <strong>Python-native multi-agent orchestration framework</strong>
</p>

<p align="center">
  <a href="#features">Features</a> &middot;
  <a href="#quickstart">Quickstart</a> &middot;
  <a href="#agents">Agents</a> &middot;
  <a href="#skills">Skills</a> &middot;
  <a href="docs/index.html">Docs</a>
</p>

<p align="center">
  <a href="docs/i18n/README_zh-CN.md">简体中文</a> · <a href="docs/i18n/README_zh-TW.md">繁體中文</a> · <a href="docs/i18n/README_ja.md">日本語</a> · <a href="docs/i18n/README_ko.md">한국어</a> · <a href="docs/i18n/README_de.md">Deutsch</a> · <a href="docs/i18n/README_fr.md">Français</a> · <a href="docs/i18n/README_es.md">Español</a> · <a href="docs/i18n/README_it.md">Italiano</a> · <a href="docs/i18n/README_pt.md">Português</a> · <a href="docs/i18n/README_ru.md">Русский</a> · <a href="docs/i18n/README_tr.md">Türkçe</a> · <a href="docs/i18n/README_vi.md">Tiếng Việt</a>
</p>

---

## What is Orbit?

Orbit is a Python-first multi-agent orchestration framework. It provides a complete toolkit for building, coordinating, and managing AI agent workflows with 30+ specialized agent roles, 35+ reusable skills, and a runtime engine for team coordination.

## Features

- **30 Agent Roles** — Specialized agents for every task: `$architect`, `$executor`, `$debugger`, `$code-reviewer`, `$planner`, and more
- **35+ Skills** — Reusable workflow skills: `$plan`, `$team`, `$autopilot`, `$ralph`, `$deep-interview`, `$doctor`
- **Runtime Engine** — Event-sourced runtime with authority management, dispatch, and mailbox coordination
- **Team Orchestration** — Multi-agent coordination via tmux with role-based routing
- **Sparkshell** — Command execution with AI-powered output summarization
- **Explorer** — Safe codebase exploration with allowlisted commands
- **Configuration Audit** — Continuous workspace health monitoring
- **HUD** — Heads-up display with real-time agent status
- **Pipeline** — Configurable multi-stage execution pipeline
- **Autoresearch** — Automated research missions with evaluation contracts

## Quickstart

```bash
# Install
pip install orbit

# Run workspace summary
orbit summary

# Check environment health
orbit doctor

# List agents and skills
orbit agents
orbit skills

# Ask with a specific role
orbit ask "review security" --role architect

# Setup project
orbit setup

# Advanced flags
orbit ask "build auth" --madmax          # Maximum autonomy
orbit ask "optimize query" --high        # High reasoning effort
orbit ask "quick fix" --spark            # Fast model tier

# Uninstall from project
orbit uninstall --dry-run
```

## Agents

Orbit includes 30 agent definitions across 5 categories:

| Category | Agents |
|----------|--------|
| **Build** | explore, analyst, planner, architect, debugger, executor, team-executor, verifier |
| **Review** | style-reviewer, quality-reviewer, api-reviewer, security-reviewer, performance-reviewer, code-reviewer |
| **Domain** | dependency-expert, test-engineer, quality-strategist, build-fixer, designer, writer, qa-tester, git-master, code-simplifier, researcher |
| **Product** | product-manager, ux-researcher, information-architect, product-analyst |
| **Coordination** | critic, vision |

Each agent has a defined posture (frontier-orchestrator, deep-worker, fast-lane), model class, routing role, and tool access pattern.

## Skills

35+ skills organized by category:

| Category | Skills |
|----------|--------|
| **Execution** | autopilot, ralph, ultrawork, team |
| **Planning** | plan, ralplan, deep-interview |
| **Shortcut** | analyze, deepsearch, tdd, build-fix, code-review, security-review, visual-verdict, web-clone, ask-claude, ask-gemini |
| **Utility** | cancel, doctor, help, note, trace, skill, hud, omx-setup, configure-notifications |

## Architecture

```
src/
  agents/          — Agent definitions and native config generation
  autoresearch/    — Automated research missions with evaluator contracts
  catalog/         — Skill/agent catalog with manifest validation
  cli/             — CLI commands and entry points
  config/          — Configuration and model resolution
  explorer/        — Safe codebase exploration
  hud/             — Heads-up display rendering
  modes/           — Runtime mode state management
  mux/             — Terminal multiplexer abstraction (tmux)
  notifications/   — Multi-platform notification system
  openclaw/        — External gateway integration
  pipeline/        — Multi-stage execution pipeline
  planning/        — Planning artifacts and PRD management
  ralph/           — Persistence loop with verification
  ralplan/         — Consensus-based planning runtime
  runtime_core/    — Event-sourced runtime engine core
  runtime_engine/  — Runtime CLI entry point
  sparkshell/      — Command execution with AI summarization
  state_manager/   — State directory and session management
  subagents/       — Subagent lifecycle tracking
  utils_core/      — Shared utilities (paths, JSON, platform)
  verification/    — Completion verification
  visual/          — Visual verdict rendering

prompts/           — 33 agent prompt definitions
skills/            — 35+ skill definitions (SKILL.md)
missions/          — 13 research mission templates
docs/              — Documentation site
playground/        — Demo experiments
```

## License

MIT
