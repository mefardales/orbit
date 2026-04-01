<p align="center">
  <img src="../../logo.png" alt="Orbit" width="500" />
</p>

<p align="center">
  <strong>Python-нативный фреймворк мульти-агентной оркестрации</strong>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README_zh-CN.md">简体中文</a> · <a href="README_zh-TW.md">繁體中文</a> · <a href="README_ja.md">日本語</a> · <a href="README_ko.md">한국어</a> · <a href="README_de.md">Deutsch</a> · <a href="README_fr.md">Français</a> · <a href="README_es.md">Español</a> · <a href="README_it.md">Italiano</a> · <a href="README_pt.md">Português</a> · <a href="README_ru.md">Русский</a> · <a href="README_tr.md">Türkçe</a> · <a href="README_vi.md">Tiếng Việt</a>
</p>

---

## Что такое Orbit?

Orbit — это Python-нативный фреймворк мульти-агентной оркестрации. Он предоставляет полный набор инструментов для создания, координации и управления рабочими процессами ИИ-агентов с 30+ специализированными ролями агентов, 35+ переиспользуемыми навыками и движком выполнения для командной координации.

## Возможности

- **30 ролей агентов** — Специализированные агенты для каждой задачи: `$architect`, `$executor`, `$debugger`, `$code-reviewer`, `$planner` и другие
- **35+ навыков** — Переиспользуемые навыки рабочих процессов: `$plan`, `$team`, `$autopilot`, `$ralph`, `$deep-interview`, `$doctor`
- **Движок выполнения** — Runtime на основе event-sourcing с управлением полномочиями, диспетчеризацией и координацией через почтовые ящики
- **Командная оркестрация** — Мульти-агентная координация на базе tmux с маршрутизацией по ролям
- **Sparkshell** — Выполнение команд с ИИ-суммаризацией вывода
- **Explorer** — Безопасное исследование кодовой базы с разрешёнными командами
- **HUD** — Панель состояния агентов в реальном времени
- **Pipeline** — Настраиваемый многоэтапный конвейер выполнения
- **Autoresearch** — Автоматизированные исследовательские миссии с контрактами оценки

## Быстрый старт

```bash
pip install orbit
orbit summary
orbit doctor
orbit agents
orbit skills
orbit ask "review security" --role architect
orbit setup
```

## Агенты

| Категория | Агенты |
|-----------|--------|
| **Сборка** | explore, analyst, planner, architect, debugger, executor, team-executor, verifier |
| **Ревью** | style-reviewer, quality-reviewer, api-reviewer, security-reviewer, performance-reviewer, code-reviewer |
| **Домен** | dependency-expert, test-engineer, quality-strategist, build-fixer, designer, writer, qa-tester, git-master, code-simplifier, researcher |
| **Продукт** | product-manager, ux-researcher, information-architect, product-analyst |
| **Координация** | critic, vision |

## Лицензия

MIT
