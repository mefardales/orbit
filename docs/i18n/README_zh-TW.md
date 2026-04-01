<p align="center">
  <img src="../../logo.png" alt="Orbit" width="500" />
</p>

<p align="center">
  <strong>Python 原生多智能體編排框架</strong>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README_zh-CN.md">简体中文</a> · <a href="README_zh-TW.md">繁體中文</a> · <a href="README_ja.md">日本語</a> · <a href="README_ko.md">한국어</a> · <a href="README_de.md">Deutsch</a> · <a href="README_fr.md">Français</a> · <a href="README_es.md">Español</a> · <a href="README_it.md">Italiano</a> · <a href="README_pt.md">Português</a> · <a href="README_ru.md">Русский</a> · <a href="README_tr.md">Türkçe</a> · <a href="README_vi.md">Tiếng Việt</a>
</p>

---

## 什麼是 Orbit？

Orbit 是一個 Python 原生的多智能體編排框架。它提供了一套完整的工具包，用於構建、協調和管理 AI 智能體工作流，擁有 30+ 專業智能體角色、35+ 可複用技能，以及用於團隊協作的運行時引擎。

## 特性

- **30 個智能體角色** — 每項任務都有專業智能體：`$architect`、`$executor`、`$debugger`、`$code-reviewer`、`$planner` 等
- **35+ 技能** — 可複用的工作流技能：`$plan`、`$team`、`$autopilot`、`$ralph`、`$deep-interview`、`$doctor`
- **運行時引擎** — 事件溯源的運行時，具有權限管理、調度和郵箱協調功能
- **團隊編排** — 基於 tmux 的多智能體協調和角色路由
- **Sparkshell** — AI 驅動的命令執行和輸出摘要
- **Explorer** — 安全的程式碼庫探索，帶有命令白名單
- **HUD** — 即時智能體狀態顯示面板
- **Pipeline** — 可配置的多階段執行管線
- **Autoresearch** — 帶評估合約的自動化研究任務

## 快速開始

```bash
pip install orbit
orbit summary
orbit doctor
orbit agents
orbit skills
orbit ask "review security" --role architect
orbit setup
```

## 智能體

| 類別 | 智能體 |
|------|--------|
| **構建** | explore, analyst, planner, architect, debugger, executor, team-executor, verifier |
| **審查** | style-reviewer, quality-reviewer, api-reviewer, security-reviewer, performance-reviewer, code-reviewer |
| **領域** | dependency-expert, test-engineer, quality-strategist, build-fixer, designer, writer, qa-tester, git-master, code-simplifier, researcher |
| **產品** | product-manager, ux-researcher, information-architect, product-analyst |
| **協調** | critic, vision |

## 許可證

MIT
