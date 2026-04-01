<p align="center">
  <img src="../../logo.png" alt="Orbit" width="500" />
</p>

<p align="center">
  <strong>Python-natives Multi-Agenten-Orchestrierungsframework</strong>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README_zh-CN.md">简体中文</a> · <a href="README_zh-TW.md">繁體中文</a> · <a href="README_ja.md">日本語</a> · <a href="README_ko.md">한국어</a> · <a href="README_de.md">Deutsch</a> · <a href="README_fr.md">Français</a> · <a href="README_es.md">Español</a> · <a href="README_it.md">Italiano</a> · <a href="README_pt.md">Português</a> · <a href="README_ru.md">Русский</a> · <a href="README_tr.md">Türkçe</a> · <a href="README_vi.md">Tiếng Việt</a>
</p>

---

## Was ist Orbit?

Orbit ist ein Python-natives Multi-Agenten-Orchestrierungsframework. Es bietet ein komplettes Toolkit zum Erstellen, Koordinieren und Verwalten von KI-Agenten-Workflows mit 30+ spezialisierten Agentenrollen, 35+ wiederverwendbaren Skills und einer Runtime-Engine für Teamkoordination.

## Funktionen

- **30 Agentenrollen** — Spezialisierte Agenten für jede Aufgabe: `$architect`, `$executor`, `$debugger`, `$code-reviewer`, `$planner` u.v.m.
- **35+ Skills** — Wiederverwendbare Workflow-Skills: `$plan`, `$team`, `$autopilot`, `$ralph`, `$deep-interview`, `$doctor`
- **Runtime-Engine** — Event-Sourcing-Runtime mit Berechtigungsverwaltung, Dispatch und Mailbox-Koordination
- **Team-Orchestrierung** — tmux-basierte Multi-Agenten-Koordination mit rollenbasiertem Routing
- **Sparkshell** — KI-gestützte Befehlsausführung und Ausgabezusammenfassung
- **Explorer** — Sichere Codebase-Erkundung mit erlaubten Befehlen
- **HUD** — Echtzeit-Agentenstatus-Anzeige
- **Pipeline** — Konfigurierbare mehrstufige Ausführungspipeline
- **Autoresearch** — Automatisierte Forschungsaufträge mit Evaluierungsverträgen

## Schnellstart

```bash
pip install orbit
orbit summary
orbit doctor
orbit agents
orbit skills
orbit ask "review security" --role architect
orbit setup
```

## Agenten

| Kategorie | Agenten |
|-----------|---------|
| **Build** | explore, analyst, planner, architect, debugger, executor, team-executor, verifier |
| **Review** | style-reviewer, quality-reviewer, api-reviewer, security-reviewer, performance-reviewer, code-reviewer |
| **Domain** | dependency-expert, test-engineer, quality-strategist, build-fixer, designer, writer, qa-tester, git-master, code-simplifier, researcher |
| **Produkt** | product-manager, ux-researcher, information-architect, product-analyst |
| **Koordination** | critic, vision |

## Lizenz

MIT
