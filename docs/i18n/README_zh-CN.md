<p align="center">
  <img src="../../logo.png" alt="Orbit" width="500" />
</p>

<p align="center">
  <strong>Python 原生多智能体编排框架</strong>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README_zh-CN.md">简体中文</a> · <a href="README_zh-TW.md">繁體中文</a> · <a href="README_ja.md">日本語</a> · <a href="README_ko.md">한국어</a> · <a href="README_de.md">Deutsch</a> · <a href="README_fr.md">Français</a> · <a href="README_es.md">Español</a> · <a href="README_it.md">Italiano</a> · <a href="README_pt.md">Português</a> · <a href="README_ru.md">Русский</a> · <a href="README_tr.md">Türkçe</a> · <a href="README_vi.md">Tiếng Việt</a>
</p>

---

## 什么是 Orbit？

Orbit 是一个 Python 原生的多智能体编排框架。它提供了一套完整的工具包，用于构建、协调和管理 AI 智能体工作流，拥有 30+ 专业智能体角色、35+ 可复用技能，以及用于团队协作的运行时引擎。

## 特性

- **30 个智能体角色** — 每项任务都有专业智能体：`$architect`、`$executor`、`$debugger`、`$code-reviewer`、`$planner` 等
- **35+ 技能** — 可复用的工作流技能：`$plan`、`$team`、`$autopilot`、`$ralph`、`$deep-interview`、`$doctor`
- **运行时引擎** — 事件溯源的运行时，具有权限管理、调度和邮箱协调功能
- **团队编排** — 基于 tmux 的多智能体协调和角色路由
- **Sparkshell** — AI 驱动的命令执行和输出摘要
- **Explorer** — 安全的代码库探索，带有命令白名单
- **HUD** — 实时智能体状态显示面板
- **Pipeline** — 可配置的多阶段执行管线
- **Autoresearch** — 带评估合约的自动化研究任务

## 快速开始

```bash
pip install orbit
orbit summary
orbit doctor
orbit agents
orbit skills
orbit ask "review security" --role architect
orbit setup
```

## 智能体

Orbit 包含 30 个智能体定义，分为 5 个类别：

| 类别 | 智能体 |
|------|--------|
| **构建** | explore, analyst, planner, architect, debugger, executor, team-executor, verifier |
| **审查** | style-reviewer, quality-reviewer, api-reviewer, security-reviewer, performance-reviewer, code-reviewer |
| **领域** | dependency-expert, test-engineer, quality-strategist, build-fixer, designer, writer, qa-tester, git-master, code-simplifier, researcher |
| **产品** | product-manager, ux-researcher, information-architect, product-analyst |
| **协调** | critic, vision |

## 技能

35+ 技能按类别组织：

| 类别 | 技能 |
|------|------|
| **执行** | autopilot, ralph, ultrawork, team |
| **规划** | plan, ralplan, deep-interview |
| **快捷** | analyze, deepsearch, tdd, build-fix, code-review, security-review, visual-verdict, web-clone |
| **实用** | cancel, doctor, help, note, trace, skill, hud, omx-setup, configure-notifications |

## 许可证

MIT
