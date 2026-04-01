<p align="center">
  <img src="../../logo.png" alt="Orbit" width="500" />
</p>

<p align="center">
  <strong>Framework di orchestrazione multi-agente nativo Python</strong>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README_zh-CN.md">简体中文</a> · <a href="README_zh-TW.md">繁體中文</a> · <a href="README_ja.md">日本語</a> · <a href="README_ko.md">한국어</a> · <a href="README_de.md">Deutsch</a> · <a href="README_fr.md">Français</a> · <a href="README_es.md">Español</a> · <a href="README_it.md">Italiano</a> · <a href="README_pt.md">Português</a> · <a href="README_ru.md">Русский</a> · <a href="README_tr.md">Türkçe</a> · <a href="README_vi.md">Tiếng Việt</a>
</p>

---

## Cos'e Orbit?

Orbit e un framework di orchestrazione multi-agente nativo Python. Fornisce un toolkit completo per costruire, coordinare e gestire workflow di agenti IA con 30+ ruoli agente specializzati, 35+ competenze riutilizzabili e un motore runtime per il coordinamento del team.

## Funzionalita

- **30 ruoli agente** — Agenti specializzati per ogni attivita: `$architect`, `$executor`, `$debugger`, `$code-reviewer`, `$planner` e altri
- **35+ competenze** — Competenze workflow riutilizzabili: `$plan`, `$team`, `$autopilot`, `$ralph`, `$deep-interview`, `$doctor`
- **Motore runtime** — Runtime event-sourced con gestione autorizzazioni, dispatch e coordinamento mailbox
- **Orchestrazione team** — Coordinamento multi-agente basato su tmux con routing basato sui ruoli
- **Sparkshell** — Esecuzione comandi con riepilogo output alimentato da IA
- **Explorer** — Esplorazione sicura del codebase con comandi autorizzati
- **HUD** — Dashboard stato agenti in tempo reale
- **Pipeline** — Pipeline di esecuzione multi-stadio configurabile
- **Autoresearch** — Missioni di ricerca automatizzate con contratti di valutazione

## Avvio rapido

```bash
pip install orbit
orbit summary
orbit doctor
orbit agents
orbit skills
orbit ask "review security" --role architect
orbit setup
```

## Agenti

| Categoria | Agenti |
|-----------|--------|
| **Build** | explore, analyst, planner, architect, debugger, executor, team-executor, verifier |
| **Review** | style-reviewer, quality-reviewer, api-reviewer, security-reviewer, performance-reviewer, code-reviewer |
| **Dominio** | dependency-expert, test-engineer, quality-strategist, build-fixer, designer, writer, qa-tester, git-master, code-simplifier, researcher |
| **Prodotto** | product-manager, ux-researcher, information-architect, product-analyst |
| **Coordinamento** | critic, vision |

## Licenza

MIT
